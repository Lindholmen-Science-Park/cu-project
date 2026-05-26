import asyncio
import os
from pathlib import Path
from typing import Optional

import omni.ext


class SceneSwitchExtension(omni.ext.IExt):
    """
    Optional scene switching extension.

    Listens to `switchScene` and opens the requested stage path (suffix under ./source/data/scenes/).
    It also resets readiness settings so StageCore/PlayerCore can re-initialize.

    On `ui.ready`, scans the scenes folder and dispatches `sceneListSync` so the
    web UI can populate the scene-switch dropdown dynamically.

    Scene switch does not call TeleportService directly. After the new stage opens,
    the same bootstrap path as first load runs: StageWatcher sets readyForPlayer,
    PlayerCore runs PhysxBootstrap. PhysxBootstrap creates the player and then
    performs a single placement via TeleportService (from the stage_core registry),
    so initial load and scene switch both use one placement path.
    """

    SCENES_BASE = "./source/data/scenes"
    PLAYER_READY_SETTING = "/younite/player/ready"
    READY_FOR_PLAYER_SETTING = "/younite/player/readyForPlayer"
    APP_READY_SETTING = "/younite/app/ready"

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._tasks = []
        self._subs = []

        try:
            import carb.settings as carb_settings

            self._settings = carb_settings.get_settings()
        except Exception:
            self._settings = None

        try:
            import omni.kit.app as kit_app
            import carb
            import carb.eventdispatcher
            from younite.messaging_core_extension.message_utils import register_outbound_events

            register_outbound_events(["sceneListSync"])

            for alias in ("switchScene", "ui.ready"):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(alias), alias)
                except Exception:
                    pass

            ed = carb.eventdispatcher.get_eventdispatcher()
            self._subs.append(ed.observe_event(
                observer_name="younite.scene_switch_extension/switchScene",
                event_name="switchScene",
                on_event=self._on_switch_scene_event,
                order=0,
            ))
            self._subs.append(ed.observe_event(
                observer_name="younite.scene_switch_extension/ui.ready",
                event_name="ui.ready",
                on_event=lambda _evt: self._dispatch_scene_list(),
                order=0,
            ))
            print("[scene_switch] subscribed to switchScene, ui.ready")
        except Exception as e:
            print(f"[scene_switch] could not subscribe: {e}")

    def on_shutdown(self):
        self._subs.clear()

        try:
            for t in getattr(self, "_tasks", []) or []:
                try:
                    t.cancel()
                except Exception:
                    pass
        except Exception:
            pass
        self._tasks = []

    def _scan_scenes(self):
        """Return a list of .usda files in the scenes folder, sorted with main_scene first."""
        try:
            import carb.tokens

            base = self.SCENES_BASE
            try:
                ti = carb.tokens.get_tokens_interface()
                base = ti.resolve(base) or base
            except Exception:
                pass

            scenes_dir = Path(base)
            if not scenes_dir.is_absolute():
                scenes_dir = Path(os.getcwd()) / base
            scenes_dir = scenes_dir.resolve()

            if not scenes_dir.is_dir():
                print(f"[scene_switch] scenes directory not found: {scenes_dir}")
                return []

            files = sorted(f.name for f in scenes_dir.iterdir() if f.suffix == ".usda" and f.is_file())
            if "main_scene.usda" in files:
                files.remove("main_scene.usda")
                files.insert(0, "main_scene.usda")

            return [{"id": name, "label": name} for name in files]
        except Exception as e:
            print(f"[scene_switch] failed to scan scenes: {e}")
            return []

    def _dispatch_scene_list(self):
        try:
            import carb.eventdispatcher

            scenes = self._scan_scenes()
            carb.eventdispatcher.get_eventdispatcher().dispatch_event(
                "sceneListSync", {"scenes": scenes}
            )
        except Exception as e:
            print(f"[scene_switch] failed to dispatch scene list: {e}")

    def _on_switch_scene_event(self, event):
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            target = payload.get("path") or payload.get("url") or payload.get("scene") or payload.get("name")
            if isinstance(target, str) and target:
                self._switch_scene(target)
        except Exception:
            pass

    def _resolve_stage_path(self, target: str) -> Optional[str]:
        """Resolve a scene name/suffix into an absolute file path under SCENES_BASE."""
        try:
            # Normalize: strip slashes, use forward slashes, disallow path traversal
            suffix = (target or "").strip().replace("\\", "/").lstrip("/")
            if ".." in suffix or suffix.startswith("/"):
                print(f"[scene_switch] ❌ Invalid path suffix (no '..' or absolute paths): {target!r}")
                return None

            path_str = (self.SCENES_BASE.rstrip("/") + "/" + suffix).replace("//", "/")
            try:
                import carb.tokens

                ti = carb.tokens.get_tokens_interface()
                path_str = ti.resolve(path_str) or path_str
            except Exception:
                pass

            p = Path(path_str)
            if not p.is_absolute():
                try:
                    p = p.resolve()
                except Exception:
                    p = Path(os.getcwd()) / path_str

            base_resolved = (Path(os.getcwd()) / self.SCENES_BASE).resolve()
            p = p.resolve()
            # Ensure result stays under scenes base (path traversal safety)
            try:
                p.relative_to(base_resolved)
            except (ValueError, OSError):
                print(f"[scene_switch] ❌ Path escapes scenes directory: {target!r}")
                return None

            if not p.is_file():
                print(f"[scene_switch] ❌ Scene file not found: {p}")
                return None

            return str(p)
        except Exception as e:
            print(f"[scene_switch] ❌ Failed to resolve path for {target!r}: {e}")
            return None

    def _reset_readiness_settings(self):
        try:
            s = self._settings
            if s:
                s.set(self.PLAYER_READY_SETTING, False)
                s.set(self.READY_FOR_PLAYER_SETTING, False)
                s.set(self.APP_READY_SETTING, False)
        except Exception:
            pass

    def _switch_scene(self, target: str) -> None:
        try:
            import omni.timeline
            import carb.eventdispatcher as _ed

            resolved = self._resolve_stage_path(target)
            if resolved is None:
                return
            print(f"[scene_switch] Switching scene to: {resolved}")

            try:
                _ed.get_eventdispatcher().dispatch_event("scene.loading", {"target": resolved})
            except Exception:
                pass

            try:
                tl = omni.timeline.get_timeline_interface()
                if tl and tl.is_playing():
                    tl.stop()
            except Exception:
                pass

            self._reset_readiness_settings()

            task = asyncio.ensure_future(self._open_stage_async(resolved))
            self._tasks.append(task)
        except Exception as e:
            print(f"[scene_switch] ❌ Scene switch failed: {e}")

    async def _open_stage_async(self, resolved_path: str):
        try:
            import omni.usd

            ctx = omni.usd.get_context()
            result = ctx.open_stage_async(resolved_path)
            if hasattr(result, "__await__"):
                await result
        except Exception as e:
            print(f"[scene_switch] ❌ Async stage open failed: {e}")

