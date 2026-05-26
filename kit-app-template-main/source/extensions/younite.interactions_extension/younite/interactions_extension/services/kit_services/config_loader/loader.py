"""Stateful :class:`ConfigLoader` — file discovery, mtime, parse, iconGroup fan-out.

Intentional USD side-effects: session-layer payload/collider attach and NPC
spawn Xforms (see :mod:`.session_authoring`).
"""
from __future__ import annotations

import os
import re
from typing import Any, List, Optional, Set

from .... import usd_helpers
from . import coins_loader
from . import expansion as exp
from . import session_authoring as sess
from .constants import (
    ENV_FALLBACKS,
    _CAPTION_EXTS,
    _MEDIA_EXTS,
)
from .types import LoadedConfig, SpatialTriggerSpec


class ConfigLoader:
    """Stateful loader that tracks file mtime + scene changes."""

    SETTINGS_KEY = "/exts/younite.interactions_extension/data_file"
    _ENV_FALLBACKS = ENV_FALLBACKS

    def __init__(self, settings=None):
        self._settings = settings

        self._cfg_mtime: int = 0
        self._cfg_last_check_ms: int = 0
        self._cfg_warned_missing: bool = False
        self._raw_cfg: Optional[dict] = None
        self._last_scene_key: str = ""
        self._last_applied_theme: str = ""

    def reset(self) -> None:
        """Clear caches so the next :meth:`maybe_reload` definitely reloads."""
        self._cfg_mtime = 0
        self._cfg_last_check_ms = 0
        self._last_scene_key = ""

    def get_config_path(self) -> str:
        """Resolve the config file path, preferring the carb setting override."""
        try:
            if self._settings:
                p = str(self._settings.get(self.SETTINGS_KEY) or "").strip()
                if p:
                    return p
        except Exception:
            pass

        try:
            from pathlib import Path

            here = Path(__file__).resolve()
            probe = here
            for _ in range(12):
                if probe.name.lower() == "source" and (probe / "data" / "interactions.json").exists():
                    return str(probe / "data" / "interactions.json")
                if probe.name.lower() == "kit-app-template-main" and (probe / "source" / "data" / "interactions.json").exists():
                    return str(probe / "source" / "data" / "interactions.json")
                if probe.parent == probe:
                    break
                probe = probe.parent
        except Exception:
            pass
        return ""

    def maybe_reload(
        self,
        *,
        now_ms: int,
        stage,
        media_content_theme: str = "horseshow",
        force: bool = False,
    ) -> Optional[LoadedConfig]:
        """Return a :class:`LoadedConfig` if a reload happened, else ``None``."""
        theme = str(media_content_theme or "horseshow").strip() or "horseshow"
        theme_changed = theme != str(self._last_applied_theme or "")

        if not force:
            if not theme_changed:
                try:
                    if (now_ms - int(self._cfg_last_check_ms or 0)) < 1000:
                        return None
                except Exception:
                    pass
        try:
            self._cfg_last_check_ms = int(now_ms)
        except Exception:
            self._cfg_last_check_ms = int(now_ms)

        path = self.get_config_path()
        if not path:
            return None

        candidates = self._scene_candidates_from_stage(stage)
        scene_key = "|".join(sorted(candidates))

        try:
            mtime = int(os.path.getmtime(path))
            same_file = int(self._cfg_mtime or 0) == mtime
            if same_file and scene_key == str(self._last_scene_key or "") and not theme_changed:
                return None
            self._cfg_mtime = mtime
        except Exception:
            if not self._cfg_warned_missing:
                self._cfg_warned_missing = True
                print(f"[interactions] config missing/unreadable: {path}")
            return None

        if not same_file or self._raw_cfg is None:
            try:
                import json

                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f) or {}
                self._raw_cfg = raw
            except Exception:
                return None
        else:
            raw = self._raw_cfg or {}

        result = self._parse(raw, candidates, stage, theme)
        self._last_scene_key = scene_key
        self._last_applied_theme = theme
        return result

    @staticmethod
    def _scene_candidates_from_stage(stage) -> Set[str]:
        out: Set[str] = set()
        try:
            if not stage:
                return out
            root = stage.GetRootLayer()
            ident = str(getattr(root, "identifier", "") or "").strip()
            if ident:
                out.add(ident)
                try:
                    base = os.path.basename(ident)
                    if base:
                        out.add(base)
                        if "." in base:
                            out.add(base.rsplit(".", 1)[0])
                except Exception:
                    pass
        except Exception:
            pass
        return out

    @staticmethod
    def _scene_match(entry: dict, scene_candidates: set) -> bool:
        s = entry.get("scene", None)
        if s is None or (isinstance(s, str) and s.strip() == ""):
            return True
        if isinstance(s, list):
            return any(str(v) in scene_candidates for v in s)
        return str(s) in scene_candidates

    @staticmethod
    def _icon_group_matches_content_theme(pt: dict, media_content_theme: str) -> bool:
        tc = pt.get("contentThemes")
        if tc is None:
            return True
        if isinstance(tc, str):
            allowed = {tc.strip()} if str(tc).strip() else set()
        else:
            allowed = {str(x).strip() for x in tc if x is not None and str(x).strip()}
        if not allowed:
            return True
        return str(media_content_theme or "").strip() in allowed

    def _parse(
        self, raw: dict, scene_candidates: set, stage, media_content_theme: str = "horseshow",
    ) -> LoadedConfig:
        meters_per_unit = usd_helpers.get_stage_meters_per_unit(stage) if stage else 0.01
        result = LoadedConfig(meters_per_unit=meters_per_unit)

        raw_points = list(raw.get("interactionPoints") or [])
        expanded_points: List[Any] = []
        for pt in raw_points:
            if not isinstance(pt, dict):
                continue
            if isinstance(pt.get("npcConfig"), dict):
                expanded_points.extend(exp.expand_npc_entry(pt))
            elif str(pt.get("interactionType") or "") == "iconGroup":
                expanded_points.extend(
                    self._expand_icon_group_entry(pt, media_content_theme)
                )
            elif isinstance(pt.get("iconConfig"), dict):
                expanded_points.extend(exp.expand_icon_entry(pt))
            else:
                expanded_points.append(pt)

        for pt in expanded_points:
            if not isinstance(pt, dict):
                continue
            if not self._scene_match(pt, scene_candidates):
                continue
            _id = str(pt.get("id") or "").strip()
            if not _id:
                continue

            pos_cfg = pt.get("position") or {}
            npc_cfg_attach = pt.get("npcConfig")
            if isinstance(npc_cfg_attach, dict):
                asset_rel = str(npc_cfg_attach.get("avatarAsset") or "").strip()
                if asset_rel:
                    prim_attach = usd_helpers.resolve_prim_path_from_config(pos_cfg)
                    if prim_attach:
                        sess.attach_npc_payload(prim_attach, npc_cfg_attach, data_root=self._data_root())

            result.all_points.append(pt)

            trigger_cfg = pt.get("trigger") or {}
            behaviors_cfg = pt.get("behaviors") or []
            if not isinstance(behaviors_cfg, list):
                behaviors_cfg = [behaviors_cfg] if behaviors_cfg else []

            pos_type = str(pos_cfg.get("type") or "xform")
            trigger_type = str(trigger_cfg.get("type") or "proximity")
            behavior_types = {str(b.get("type") or "") for b in behaviors_cfg if isinstance(b, dict)}

            world_pos = None
            bounds = None

            if pos_type == "xform":
                prim_path = usd_helpers.resolve_prim_path_from_config(pos_cfg)
                if prim_path:
                    world_pos = usd_helpers.resolve_prim_position(prim_path)
            elif pos_type == "coordinates":
                coords = pos_cfg.get("coordinates")
                if isinstance(coords, (list, tuple)) and len(coords) >= 3:
                    world_pos = (float(coords[0]), float(coords[1]), float(coords[2]))
            elif pos_type == "volume":
                prim_path = str(pos_cfg.get("primPath") or "")
                if prim_path:
                    world_pos, bounds = usd_helpers.resolve_prim_bounds(prim_path)
            elif pos_type == "geoCoords":
                print(f"[interactions] geoCoords position not yet supported, skipping: {_id}")
                continue

            if world_pos is None:
                continue

            offset = pos_cfg.get("positionOffset")
            if isinstance(offset, (list, tuple)) and len(offset) >= 3:
                world_pos = (
                    world_pos[0] + float(offset[0]),
                    world_pos[1] + float(offset[1]),
                    world_pos[2] + float(offset[2]),
                )

            npc_cfg = pt.get("npcConfig")
            if isinstance(npc_cfg, dict):
                npc_prim_path = usd_helpers.resolve_prim_path_from_config(pos_cfg)
                radius_m = trigger_cfg.get("radiusMeters")
                result.npc_registry[_id] = {
                    "prim_path": npc_prim_path,
                    "radius_meters": float(radius_m) if radius_m is not None else None,
                    "npc_config": exp.npc_config_for_web(npc_cfg),
                }

            icon_cfg = pt.get("iconConfig")
            if isinstance(icon_cfg, dict):
                icon_prim_path = usd_helpers.resolve_prim_path_from_config(pos_cfg)
                radius_m = trigger_cfg.get("radiusMeters")
                max_vert_m = trigger_cfg.get("maxVerticalMeters")
                icon_cfg_with_path = dict(icon_cfg)
                if icon_prim_path:
                    icon_cfg_with_path["primPath"] = icon_prim_path
                icon_reg_entry = {
                    "prim_path": icon_prim_path,
                    "radius_meters": float(radius_m) if radius_m is not None else None,
                    "icon_config": icon_cfg_with_path,
                }
                if max_vert_m is not None:
                    icon_reg_entry["max_vertical_meters"] = float(max_vert_m)
                result.icon_registry[_id] = icon_reg_entry

            if trigger_type == "click":
                click_path = usd_helpers.resolve_prim_path_from_config(pos_cfg)
                if click_path:
                    result.click_points_by_path[click_path] = pt
            elif trigger_type in ("proximity", "volume"):
                activation = str(trigger_cfg.get("activation") or "always")
                one_shot = bool(trigger_cfg.get("oneShot", False))
                xz_only = bool(trigger_cfg.get("xzOnly", False))
                radius = float(trigger_cfg.get("radius", 150.0) or 150.0)
                radius_meters = trigger_cfg.get("radiusMeters")
                radius_meters = float(radius_meters) if radius_meters is not None else None

                result.spatial_triggers.append(SpatialTriggerSpec(
                    trigger_id=_id,
                    position=world_pos,
                    trigger_type=trigger_type,
                    radius=radius,
                    radius_meters=radius_meters,
                    xz_only=xz_only,
                    one_shot=one_shot,
                    activation=activation,
                    behaviors=list(behaviors_cfg),
                    bounds=bounds,
                    active=(activation == "always"),
                ))

            if "projectable" in behavior_types:
                it = str(pt.get("interactionType") or "")
                if it not in ("npc", "icon"):
                    result.projectable_points.append(pt)

        for pt in result.all_points:
            it = str(pt.get("interactionType") or "")
            pos_cfg = pt.get("position") or {}
            pp = usd_helpers.resolve_prim_path_from_config(pos_cfg)
            if not pp:
                continue
            if it == "npc" and pp not in result.npc_marker_paths:
                result.npc_marker_paths.append(pp)
            elif it == "icon" and isinstance(pt.get("iconConfig"), dict) and pp not in result.icon_marker_paths:
                # POI coins (mediaType: coinPoi) opt out of the standard
                # icon marker treatment (no top/bottom pyramids, no
                # per-frame Y self-rotation that would override the
                # authored arrow direction). Optional per-coin spin: when
                # ``iconConfig.spinEnabled`` is true (default), register with
                # ``InteractionMarkerService`` mode ``"coin"`` to drive the
                # ``xformOp:rotate{X|Y|Z}:spin`` op authored by
                # ``session_authoring.attach_coin_payload``.
                icon_cfg = pt.get("iconConfig") or {}
                if icon_cfg.get("mediaType") == "coinPoi":
                    spin_axis = str(icon_cfg.get("spinAxis") or "z").lower().strip()
                    if spin_axis not in ("x", "y", "z"):
                        spin_axis = "z"
                    if icon_cfg.get("spinEnabled", True) and (pp, spin_axis) not in result.coin_marker_paths:
                        result.coin_marker_paths.append((pp, spin_axis))
                    continue
                result.icon_marker_paths.append(pp)

        try:
            print(
                f"[interactions] loaded: {len(result.all_points)} points "
                f"(projectable={len(result.projectable_points)}, "
                f"clickable={len(result.click_points_by_path)}, "
                f"spatial={len(result.spatial_triggers)}, "
                f"npc={len(result.npc_registry)}, "
                f"icon={len(result.icon_registry)})"
            )
        except Exception:
            pass

        return result

    def _expand_icon_group_entry(self, pt: dict, media_content_theme: str = "horseshow") -> list:
        if not self._icon_group_matches_content_theme(pt, media_content_theme):
            return []

        icon_cfg = pt.get("iconConfig") or {}
        pattern = str(pt.get("primNamePattern") or "").strip()
        if not pattern or not isinstance(icon_cfg, dict):
            return []

        # Coin POIs use the iconGroup template but resolve their per-coin
        # asset + metadata from a registry + the existing POI data files.
        # See coins_loader.py for the naming convention and expansion rules.
        if str(icon_cfg.get("kind") or "").strip() == "coin":
            return coins_loader.expand_coin_group_entry(pt, data_root=self._data_root())

        matches = usd_helpers.find_xforms_by_glob(pattern)
        if not matches:
            if usd_helpers.stage_has_world_children():
                print(f"[interactions] iconGroup '{pt.get('id')}': no Xforms match pattern '{pattern}'")
            return []

        media_dir = self._expand_env(icon_cfg.get("soundsDir") or icon_cfg.get("videosDir") or "")
        media_index = self._index_files_by_prefix(media_dir) if media_dir else {}
        captions_dir = self._expand_env(icon_cfg.get("captionsDir") or "") or media_dir
        captions_index = (
            self._index_files_by_prefix(captions_dir, _CAPTION_EXTS)
            if captions_dir else {}
        )

        media_field = "soundUrl" if icon_cfg.get("mediaType") == "spatialSound" else "videoUrl"
        i18n_pattern = str(icon_cfg.get("i18nKeyPattern") or "interactions.{id}")
        icon_asset = icon_cfg.get("iconAsset")

        shared_icon = {
            k: v for k, v in icon_cfg.items()
            if k not in ("soundsDir", "videosDir", "captionsDir", "iconAsset", "i18nKeyPattern")
        }

        expanded: list = []
        for prim_path, leaf_name in matches:
            prefix = self._extract_number_prefix(leaf_name)
            if prefix is None:
                print(f"[interactions] iconGroup: cannot extract number prefix from '{leaf_name}', skipping")
                continue
            media_filename = media_index.get(prefix)
            if not media_filename:
                print(
                    f"[interactions] iconGroup: no media file with prefix '{prefix}' in '{media_dir}' for {leaf_name}"
                )
                continue

            if icon_asset:
                sess.attach_icon_payload(prim_path, str(icon_asset), data_root=self._data_root())

            synth_id = f"icon_{leaf_name}"
            i18n_base = i18n_pattern.format(id=synth_id)
            pos_offset = (pt.get("position") or {}).get("positionOffset")

            icon_payload = {
                **shared_icon,
                media_field: media_filename,
                "greeting": f"{i18n_base}.greeting",
                "title": f"{i18n_base}.title",
                "subtitle": f"{i18n_base}.subtitle",
                "soundTitle": f"{i18n_base}.soundTitle",
                "videoTitle": f"{i18n_base}.videoTitle",
            }
            captions_filename = captions_index.get(prefix)
            if captions_filename:
                icon_payload["captionsUrl"] = captions_filename

            synth_entry = {
                "id": synth_id,
                "interactionType": "icon",
                "scene": pt.get("scene"),
                "position": {
                    "type": "xform",
                    "primName": leaf_name,
                    "positionOffset": pos_offset,
                },
                "trigger": dict(pt.get("trigger") or {}),
                "iconConfig": icon_payload,
            }
            expanded.extend(exp.expand_icon_entry(synth_entry))

        return expanded

    def _data_root(self):
        try:
            from pathlib import Path

            cfg = self.get_config_path()
            if cfg:
                return Path(cfg).resolve().parent
        except Exception:
            pass
        return None

    @classmethod
    def _expand_env(cls, raw: str) -> str:
        if not raw or "$" not in raw:
            return raw
        expanded = os.path.expandvars(raw)
        if "$" in expanded:
            def _resolve(match):
                name = match.group(1) or match.group(2)
                fallback = cls._ENV_FALLBACKS.get(name, "")
                if fallback:
                    print(
                        f"[interactions] env var ${{{name}}} unset — falling back to "
                        f"hardcoded default '{fallback}'. Add {name} to repo-root .env "
                        f"to silence this warning."
                    )
                else:
                    print(f"[interactions] env var ${{{name}}} unset and no fallback registered")
                return fallback
            expanded = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", _resolve, expanded)
        return expanded

    def _index_files_by_prefix(self, rel_dir: str, extensions: Optional[set] = None) -> dict:
        out: dict = {}
        root = self._data_root()
        if not root or not rel_dir:
            return out
        ext_filter = extensions if extensions is not None else _MEDIA_EXTS
        try:
            abs_dir = (root / rel_dir).resolve()
            if not abs_dir.is_dir():
                print(f"[interactions] iconGroup: media dir not found: {abs_dir}")
                return out
            for name in os.listdir(str(abs_dir)):
                m = re.match(r"^(\d+)_", name)
                if not m:
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext_filter and ext not in ext_filter:
                    continue
                prefix = m.group(1)
                if prefix not in out:
                    out[prefix] = name
        except Exception:
            pass
        return out

    @staticmethod
    def _extract_number_prefix(leaf_name: str):
        m = re.search(r"_(\d+)$", leaf_name)
        if not m:
            m = re.search(r"(\d+)$", leaf_name)
        return m.group(1) if m else None
