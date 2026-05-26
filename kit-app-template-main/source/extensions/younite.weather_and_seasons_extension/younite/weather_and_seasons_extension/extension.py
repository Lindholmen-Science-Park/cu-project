import os

import omni.ext


_VALID_SEASONS = ("summer", "spring", "fall", "autumn", "winter")

_SEASON_TO_TEXTURE = {
    "summer": "summer",
    "spring": "spring",
    "fall": "fall",
    "autumn": "fall",
    "winter": "winter",
}

_SEASONAL_TEXTURES_DIR = os.path.join("Assets", "SeasonalTextures")

_TEXTURE_FILES = {
    "spring": "Maple_Red_Field_Color_dark_spring.png",
    "fall": "Maple_Red_Field_Color_dark_fall.png",
    "winter": "Maple_Red_Field_Color_dark_winter.png",
}

_TREE_SHADER_SUFFIX = (
    "VEG_10500_Traed_genericTree/_materials/Tree_material/Image_Texture"
)

_SETTLE_FRAMES = 15

# ── snow-cover textures for natural terrain (winter only) ──────────
_FROST_TEXTURES_DIR = os.path.join("Assets", "SeasonalTextures", "Frost")

_SNOW_NATURAL_MATERIALS: dict[str, str] = {
    "mat_Graes":        "Graes_winter_snow.jpg",
    "mat_Grus":         "Grus_winter_snow.jpg",
    "mat_Sand":         "Sand_winter_snow.jpg",
    "mat_Slaatter":     "Slaatter_winter_snow.jpg",
    "mat_Skog":         "Skog_winter_snow.jpg",
    "mat_aaker":        "aaker_winter_snow.jpg",
    "mat_Jord":         "Jord_winter_snow.jpg",
    "mat_Berg":         "Berg_winter_snow.jpg",
    "mat_Kaerr":        "Kaerr_winter_snow.jpg",
    "mat_Buskage":      "Buskage_winter_snow.jpg",
    "mat_Bollplan":     "Bollplan_winter_snow.jpg",
    "mat_Fallskyddsmatta": "Fallskyddsmatta_winter_snow.jpg",
    "mat_Gummi":        "Gummi_winter_snow.jpg",
}

_TERRAIN_SHADER_NAMES = ("usduvtexture1", "Image_Texture")

_SNOW_BASE_NAMES: set[str] = set(_SNOW_NATURAL_MATERIALS.keys())


class SeasonsExtension(omni.ext.IExt):
    """Swaps tree leaf texture and terrain materials for seasonal variants
    via session-layer overrides."""

    def on_startup(self, ext_id: str):
        self._subs = []
        self._shader_paths: list[str] | None = None
        self._seasonal_dir: str | None = None
        self._frost_dir: str | None = None
        self._terrain_shader_paths: list[tuple[str, str]] | None = None
        self._terrain_original_textures: dict[str, str] = {}
        self._current_season = "summer"

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()

            try:
                kit_app.register_event_alias(
                    carb.events.type_from_string("seasonChangeRequest"),
                    "seasonChangeRequest",
                )
            except Exception:
                pass

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.weather_and_seasons_extension/seasonChangeRequest",
                    event_name="seasonChangeRequest",
                    on_event=self._on_season_change,
                    order=0,
                )
            )

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.weather_and_seasons_extension/viewTypeChanged",
                    event_name="younite.camera.viewTypeChanged",
                    on_event=self._on_view_type_changed,
                    order=0,
                )
            )

            from younite.messaging_core_extension.message_utils import (
                register_outbound_events,
            )
            register_outbound_events([
                "seasonStatus",
                "seasonChangeStarted",
                "seasonChangeCompleted",
            ])

            print("[seasons] extension started")
        except Exception as exc:
            print(f"[seasons] startup error: {exc}")

    def on_shutdown(self):
        self._subs.clear()
        self._shader_paths = None
        self._seasonal_dir = None
        self._frost_dir = None
        self._terrain_shader_paths = None
        self._terrain_original_textures = {}

        from . import fallen_leaves_service, ground_litter_service
        from .snow_service import stop_snow
        from .rain_service import stop_rain
        from .wet_ground_service import invalidate_cache as _wg_invalidate
        fallen_leaves_service.stop_fallen_leaves()
        ground_litter_service.stop()
        fallen_leaves_service.invalidate_cache()
        _wg_invalidate()
        stop_snow()
        stop_rain()

        print("[seasons] extension shut down")

    # ------------------------------------------------------------------

    def _on_season_change(self, event):
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
                dispatch_to_events2,
            )

            raw = getattr(event, "payload", None)
            if raw is None and isinstance(event, dict):
                raw = event
            payload = normalize_event_payload(raw or {})
            season = str(payload.get("season", "")).lower()
            if season not in _VALID_SEASONS:
                print(f"[seasons] unknown season '{season}', ignoring")
                return

            import asyncio
            asyncio.ensure_future(self._apply_season_async(season))
        except Exception as exc:
            print(f"[seasons] error handling season change: {exc}")
            try:
                dispatch_to_events2("seasonChangeCompleted", {})
            except Exception:
                pass

    # ------------------------------------------------------------------

    _PRECIPITATION_SETTLE_FRAMES = 10

    def _on_view_type_changed(self, event):
        """Toggle 3D precipitation particles when switching between
        bird-eye (overlay only) and first-person (3D particles)."""
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            raw = getattr(event, "payload", None)
            if raw is None and isinstance(event, dict):
                raw = event
            payload = normalize_event_payload(raw or {})
            view_type = str(payload.get("viewType", ""))

            if view_type == "birdEye":
                from .rain_service import stop_rain
                from .snow_service import stop_snow
                stop_rain()
                stop_snow()
            elif view_type == "firstPerson":
                import asyncio
                asyncio.ensure_future(self._deferred_start_precipitation())
        except Exception as exc:
            print(f"[seasons] error handling view type change: {exc}")

    async def _deferred_start_precipitation(self):
        """Wait a few frames for the camera/teleport to settle, then start
        3D precipitation if still desired.  Avoids reading stale camera
        forward direction during a teleport transition."""
        try:
            import omni.kit.app as kit_app
            app = kit_app.get_app()
            for _ in range(self._PRECIPITATION_SETTLE_FRAMES):
                await app.next_update_async()

            from .sky_service import get_desired_precipitation, _is_bird_eye
            if _is_bird_eye():
                return

            from .rain_service import start_rain
            from .snow_service import start_snow

            desired_rain, desired_snow = get_desired_precipitation()
            if desired_snow > 0:
                start_snow(desired_snow)
            elif desired_rain > 0:
                start_rain(desired_rain)
        except Exception as exc:
            print(f"[seasons] error starting deferred precipitation: {exc}")

    # ------------------------------------------------------------------

    async def _apply_season_async(self, season: str):
        """Batched, async season swap with frame gap for Hydra to settle."""
        from younite.messaging_core_extension.message_utils import dispatch_to_events2
        import omni.usd
        import omni.kit.app as kit_app
        from pxr import Usd, Sdf

        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                print("[seasons] no stage available")
                return

            if self._shader_paths is None:
                self._discover_tree_shaders(stage)
            if self._terrain_shader_paths is None:
                self._discover_terrain_shaders(stage)

            if not self._shader_paths:
                print("[seasons] no tree shaders found in stage")
                return

            texture_season = _SEASON_TO_TEXTURE[season]
            tex_path = None

            if texture_season != "summer":
                tex_path = self._resolve_texture_path(stage, texture_season)
                if not tex_path:
                    print(f"[seasons] texture missing for '{texture_season}' — keeping current appearance")
                    return

            snow_map = self._resolve_snow_textures(stage) if texture_season == "winter" else {}

            from .wet_ground_service import set_wet
            set_wet("season", texture_season == "winter", stage=stage)

            dispatch_to_events2("seasonChangeStarted", {"season": season})
            app = kit_app.get_app()

            session_layer = stage.GetSessionLayer()

            with Sdf.ChangeBlock():
                with Usd.EditContext(stage, session_layer):
                    for prim_path in self._shader_paths:
                        prim = stage.GetPrimAtPath(prim_path)
                        if not prim:
                            continue
                        attr = prim.GetAttribute("inputs:file")
                        if not attr:
                            continue
                        if texture_season == "summer":
                            attr.Clear()
                        else:
                            attr.Set(Sdf.AssetPath(tex_path))

                    self._apply_snow_terrain(
                        stage, texture_season, snow_map,
                    )

            if texture_season == "summer":
                print(f"[seasons] applied summer (cleared overrides on {len(self._shader_paths)} shaders)")
            else:
                print(f"[seasons] applied {texture_season} texture on {len(self._shader_paths)} shaders")

            for _ in range(_SETTLE_FRAMES):
                await app.next_update_async()

            self._update_fallen_leaves(texture_season)

            self._current_season = season
            dispatch_to_events2("seasonStatus", {"season": season})
        except Exception as exc:
            print(f"[seasons] error during season swap: {exc}")
        finally:
            dispatch_to_events2("seasonChangeCompleted", {"season": season})

    # ------------------------------------------------------------------

    def _update_fallen_leaves(self, texture_season: str):
        """Start or stop fallen leaves and ground litter based on season."""
        from . import fallen_leaves_service, ground_litter_service

        if texture_season == "fall":
            ground_litter_service.start(self._shader_paths)
            fallen_leaves_service.start_fallen_leaves(self._shader_paths)
        else:
            fallen_leaves_service.stop_fallen_leaves()
            ground_litter_service.stop()

    def _discover_tree_shaders(self, stage):
        """Scan the composed stage for all tree Image_Texture shader prims."""
        from pxr import Usd

        self._shader_paths = []
        for prim in stage.Traverse():
            path = str(prim.GetPath())
            if path.endswith(_TREE_SHADER_SUFFIX):
                self._shader_paths.append(path)

        print(f"[seasons] discovered {len(self._shader_paths)} tree shader prims")

    def _resolve_texture_path(self, stage, season: str) -> str | None:
        """Compute the absolute path to the seasonal texture file."""
        if self._seasonal_dir is None:
            root_layer = stage.GetRootLayer()
            root_dir = os.path.dirname(root_layer.realPath)
            data_dir = os.path.normpath(os.path.join(root_dir, ".."))
            self._seasonal_dir = os.path.normpath(
                os.path.join(data_dir, _SEASONAL_TEXTURES_DIR)
            )
            print(f"[seasons] seasonal texture directory: {self._seasonal_dir}")

        filename = _TEXTURE_FILES.get(season)
        if not filename:
            return None

        full = os.path.join(self._seasonal_dir, filename)
        if not os.path.isfile(full):
            print(f"[seasons] texture not found: {full}")
            print("[seasons] run generate_seasonal_textures.py to create them")
            return None

        return full

    # ── terrain frost / snow ──────────────────────────────────────

    @staticmethod
    def _match_base_material(mat_prim_name: str) -> str | None:
        """Return the base material key from _SNOW_NATURAL_MATERIALS if
        *mat_prim_name* matches exactly or with a numeric suffix
        (e.g. ``mat_Graes_002`` → ``mat_Graes``)."""
        if mat_prim_name in _SNOW_BASE_NAMES:
            return mat_prim_name
        import re
        m = re.match(r"^(.+?)_\d+$", mat_prim_name)
        if m and m.group(1) in _SNOW_BASE_NAMES:
            return m.group(1)
        return None

    def _discover_terrain_shaders(self, stage):
        """Find shader prims for natural-terrain materials (snow cover).
        Paved surfaces are handled by wet_ground_service.
        Also caches original texture paths so we can restore them without
        attr.Clear() (which causes a neon-blue flash from the RTX renderer's
        missing-texture fallback)."""

        self._terrain_shader_paths = []
        self._terrain_original_textures = {}
        for prim in stage.Traverse():
            path_str = str(prim.GetPath())
            prim_name = prim.GetName()
            if prim_name not in _TERRAIN_SHADER_NAMES:
                continue
            parts = path_str.rsplit("/", 2)
            if len(parts) < 2:
                continue
            parent_name = parts[-2]
            base = self._match_base_material(parent_name)
            if base is not None:
                self._terrain_shader_paths.append((path_str, base))
                attr = prim.GetAttribute("inputs:file")
                if attr:
                    val = attr.Get()
                    if val:
                        self._terrain_original_textures[path_str] = str(
                            val.resolvedPath or val.path
                        )

        bases_found = {b for _, b in self._terrain_shader_paths}
        print(f"[seasons] discovered {len(self._terrain_shader_paths)} natural-terrain shader "
              f"prims ({len(bases_found)}/{len(_SNOW_NATURAL_MATERIALS)} material types, "
              f"{len(self._terrain_original_textures)} original textures cached)")
        missing = _SNOW_BASE_NAMES - bases_found
        if missing:
            print(f"[seasons]   missing material types: {sorted(missing)}")

    def _resolve_frost_dir(self, stage) -> str:
        """Compute the frost texture directory (lazy, cached)."""
        if self._frost_dir is None:
            root_layer = stage.GetRootLayer()
            root_dir = os.path.dirname(root_layer.realPath)
            data_dir = os.path.normpath(os.path.join(root_dir, ".."))
            self._frost_dir = os.path.normpath(
                os.path.join(data_dir, _FROST_TEXTURES_DIR)
            )
            print(f"[seasons] frost texture directory: {self._frost_dir}")
        return self._frost_dir

    def _resolve_snow_textures(self, stage) -> dict[str, str]:
        """Return {mat_name: absolute_path} for available snow-cover textures."""
        frost_dir = self._resolve_frost_dir(stage)
        result: dict[str, str] = {}
        missing = []
        for mat_name, filename in _SNOW_NATURAL_MATERIALS.items():
            full = os.path.join(frost_dir, filename)
            if os.path.isfile(full):
                result[mat_name] = full
            else:
                missing.append(mat_name)
        if missing:
            print(f"[seasons] snow textures missing for {len(missing)} materials — "
                  "run generate_frost_textures.py")
        return result

    def _apply_snow_terrain(self, stage, texture_season: str,
                            snow_map: dict[str, str]) -> None:
        """Override (or restore) natural-terrain snow textures.  Must be called
        inside an active Usd.EditContext on the session layer.
        Paved surfaces are handled separately by wet_ground_service.
        Restores original texture paths instead of attr.Clear() to avoid
        the RTX renderer's neon-blue missing-texture flash."""
        from pxr import Sdf

        if not self._terrain_shader_paths:
            return

        overridden = 0
        restored = 0
        for prim_path, base_mat in self._terrain_shader_paths:
            prim = stage.GetPrimAtPath(prim_path)
            if not prim:
                continue
            attr = prim.GetAttribute("inputs:file")
            if not attr:
                continue

            if texture_season == "winter":
                snow_path = snow_map.get(base_mat)
                if snow_path:
                    attr.Set(Sdf.AssetPath(snow_path))
                    overridden += 1
            else:
                original = self._terrain_original_textures.get(prim_path)
                if original:
                    attr.Set(Sdf.AssetPath(original))
                else:
                    attr.Clear()
                restored += 1

        if texture_season == "winter":
            print(f"[seasons] snow terrain: overrode {overridden} natural material textures")
        elif restored:
            print(f"[seasons] snow terrain: restored {restored} original textures")
