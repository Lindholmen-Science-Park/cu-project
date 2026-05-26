"""
LOD Management Extension — switches the Skandinavium LOD variant from
camera view (bird's-eye → light, first-person → full) and from manual
web UI toggle (stadiumLodToggle).

After the variant switch, an async Unload → frame gap → Load cycle forces
Hydra to fully discard cached PointInstancer instances before loading the
new variant's content.
"""

import omni.ext


_PRIM_PATH = "/World/Skandinavium"
_VARIANT_SET = "lod"
_LOD_FULL = "full"
_LOD_LIGHT = "light"
_LOD_SETTING = "/younite/stadium/currentLod"

_AUTO_LOD_ENABLED = True
_VIEW_TYPE_SETTING = "/younite/camera/viewType"
_HYDRA_SETTLE_FRAMES_AFTER_LOAD = 4

_VIEW_TO_LOD = {
    "birdEye": _LOD_LIGHT,
    "firstPerson": _LOD_FULL,
}


class LodManagementExtension(omni.ext.IExt):

    def on_startup(self, ext_id):
        self._ext_id = ext_id
        self._subs = []
        self._current_lod = None
        self._stage_sub = None
        self._start_observers()
        self._start_stage_sync()

    def on_shutdown(self):
        self._subs.clear()
        self._stage_sub = None

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------

    def _start_observers(self):
        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(
                        carb.events.type_from_string(name), name
                    )
                except Exception:
                    pass
                try:
                    self._subs.append(
                        ed.observe_event(
                            observer_name=f"younite.lod_management_extension/{name}",
                            event_name=name,
                            on_event=handler,
                            order=0,
                        )
                    )
                except Exception:
                    pass

            _observe("younite.camera.viewTypeChanged", self._on_view_type_changed)
            _observe("stadiumLodToggle", self._on_manual_toggle)
        except Exception as e:
            print(f"[lod_mgmt] failed to start observers: {e}")

    def _start_stage_sync(self):
        """Match stadium LOD to the current camera view when the stage opens."""
        try:
            import asyncio
            import omni.usd

            def _sync_from_settings():
                try:
                    import carb

                    vt = str(carb.settings.get_settings().get(_VIEW_TYPE_SETTING) or "firstPerson").strip()
                    target = _VIEW_TO_LOD.get(vt)
                    if target:
                        self._apply_lod(target)
                except Exception as e:
                    print(f"[lod_mgmt] settings sync error: {e}")

            async def _sync_when_prim_ready():
                import time
                import omni.kit.app as kit_app

                deadline = time.monotonic() + 30.0
                try:
                    while time.monotonic() < deadline:
                        stage = omni.usd.get_context().get_stage()
                        if stage:
                            prim = stage.GetPrimAtPath(_PRIM_PATH)
                            if prim and prim.IsValid():
                                _sync_from_settings()
                                return
                        await kit_app.get_app().next_update_async()
                    _sync_from_settings()
                except Exception as e:
                    print(f"[lod_mgmt] prim-ready sync error: {e}")

            def _on_stage_event(event):
                try:
                    event_type = event.type if hasattr(event, "type") else None
                    if event_type == int(omni.usd.StageEventType.OPENED):
                        asyncio.ensure_future(_sync_when_prim_ready())
                except Exception:
                    pass

            usd_context = omni.usd.get_context()
            self._stage_sub = usd_context.get_stage_event_stream().create_subscription_to_pop(
                _on_stage_event, name="LOD Management Stage Sync"
            )
            if usd_context.get_stage():
                asyncio.ensure_future(_sync_when_prim_ready())
        except Exception as e:
            print(f"[lod_mgmt] stage sync start failed: {e}")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_view_type_changed(self, event):
        if not _AUTO_LOD_ENABLED:
            return
        try:
            payload = getattr(event, "payload", None) or {}
            view_type = str(payload.get("viewType", "")).strip()
            target = _VIEW_TO_LOD.get(view_type)
            if target is None:
                return
            self._apply_lod(target)
        except Exception as e:
            print(f"[lod_mgmt] view-type handler error: {e}")

    def _on_manual_toggle(self, event):
        try:
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
            )

            payload = normalize_event_payload(
                getattr(event, "payload", None) or {}
            )
            lod = str(payload.get("lod", "")).strip().lower()
            if not lod:
                lod = _LOD_LIGHT if self._current_lod == _LOD_FULL else _LOD_FULL
            self._apply_lod(lod)
        except Exception as e:
            print(f"[lod_mgmt] manual toggle error: {e}")
            self._dispatch_response(error=str(e))

    # ------------------------------------------------------------------
    # Core LOD switch — variant set + async Unload/frame/Load
    # ------------------------------------------------------------------

    def _apply_lod(self, target: str):
        import asyncio
        asyncio.ensure_future(self._apply_lod_async(target))

    async def _apply_lod_async(self, target: str):
        try:
            import omni.usd
            import omni.kit.app as kit_app
            from pxr import Sdf

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            prim = stage.GetPrimAtPath(_PRIM_PATH)
            if not prim or not prim.IsValid():
                print(f"[lod_mgmt] prim not found: {_PRIM_PATH}")
                return

            vset = prim.GetVariantSet(_VARIANT_SET)
            if not vset:
                print(f"[lod_mgmt] variant set '{_VARIANT_SET}' not found")
                return

            current = vset.GetVariantSelection()
            if current == target:
                if self._current_lod != target:
                    self._current_lod = target
                    self._publish_current_lod(target)
                    self._dispatch_response(lod=target)
                return

            vset.SetVariantSelection(target)

            sdf_path = Sdf.Path(_PRIM_PATH)
            stage.Unload(sdf_path)

            app = kit_app.get_app()
            await app.next_update_async()
            await app.next_update_async()

            stage.Load(sdf_path)

            for _ in range(_HYDRA_SETTLE_FRAMES_AFTER_LOAD):
                await app.next_update_async()

            self._current_lod = target
            self._publish_current_lod(target)
            self._dispatch_response(lod=target)
            print(f"[lod_mgmt] variant switched: {current} -> {target}")
        except Exception as e:
            print(f"[lod_mgmt] apply error: {e}")
            self._dispatch_response(error=str(e))

    # ------------------------------------------------------------------
    # State publication
    # ------------------------------------------------------------------

    def _publish_current_lod(self, lod: str):
        try:
            import carb
            carb.settings.get_settings().set(_LOD_SETTING, str(lod))
        except Exception:
            pass

    def _dispatch_response(self, lod: str | None = None, error: str | None = None):
        try:
            import carb.eventdispatcher as _ed

            payload = {}
            if error:
                payload = {"result": "error", "error": error}
            else:
                payload = {"result": "success", "lod": lod or ""}

            _ed.get_eventdispatcher().dispatch_event(
                "stadiumLodResponse", payload
            )
        except Exception:
            pass
