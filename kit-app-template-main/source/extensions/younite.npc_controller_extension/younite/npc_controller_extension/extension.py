"""
NPC Controller Extension

Wires Events 2.0 messages to the NPC controller service so that external
systems (web UI, script, other extensions) can spawn NPC characters and
have them walk along NavMesh-computed routes.

Events listened to:
  npcSpawn      { npcId, primPath, routeId?, speed?, loop?, start, end, drawPath?, model? }
  npcStop       { npcId? | all? }
  npcStartAll   {}  — spawn all NPCs defined in config/npc_configs.json
  npcStopAll    {}  — stop and remove all active NPCs
  navmeshRouteWaypoints  (forwarded from navmesh_route_extension)
"""
import json
import os

import omni.ext


class NpcControllerExtension(omni.ext.IExt):

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []

        from .services.kit_services.npc_controller_service import NpcControllerService
        self._svc = NpcControllerService()

        self._npc_config = self._load_config(ext_id)

        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            ed = carb.eventdispatcher.get_eventdispatcher()

            event_names = ["npcSpawn", "npcStop", "npcStartAll", "npcStopAll", "navmeshRouteWaypoints", "npcStatus", "npcArrived"]
            for name in event_names:
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass

            def _observe(event_name, handler, *, order=0):
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.npc_controller_extension/{event_name}",
                        event_name=event_name,
                        on_event=handler,
                        order=order,
                    )
                )

            def _parse_vec3(payload, keys):
                for k in keys:
                    v = payload.get(k)
                    if v is None:
                        continue
                    if isinstance(v, (list, tuple)) and len(v) >= 3:
                        try:
                            return (float(v[0]), float(v[1]), float(v[2]))
                        except Exception:
                            continue
                    if isinstance(v, dict):
                        x, y, z = v.get("x", v.get("X")), v.get("y", v.get("Y")), v.get("z", v.get("Z"))
                        if x is not None and y is not None and z is not None:
                            try:
                                return (float(x), float(y), float(z))
                            except Exception:
                                continue
                    if isinstance(v, str):
                        return v
                return None

            # ── npcSpawn ──────────────────────────────────────────────────
            def _on_spawn(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                npc_id = str(payload.get("npcId") or payload.get("npc_id") or "npc_default")
                prim_path = str(payload.get("primPath") or payload.get("prim_path") or "")
                if not prim_path:
                    print("[npc_controller] npcSpawn missing primPath")
                    return

                route_id = str(payload.get("routeId") or payload.get("route_id") or npc_id)
                speed = float(payload.get("speed", 150.0))
                loop = bool(payload.get("loop", False))
                draw_path = bool(payload.get("drawPath", False))
                model = payload.get("model") or None
                if model is not None:
                    model = str(model)

                start_ref = _parse_vec3(payload, ["start", "startPos", "startPosition", "startPoint", "startpointPath"])
                end_ref = _parse_vec3(payload, ["end", "endPos", "endPosition", "endPoint", "endpointPath", "targetPos"])

                self._svc.spawn_npc(
                    npc_id,
                    prim_path,
                    route_id,
                    speed=speed,
                    loop=loop,
                    start_ref=start_ref,
                    end_ref=end_ref,
                    draw_path=draw_path,
                    model=model,
                )

            # ── npcStop ───────────────────────────────────────────────────
            def _on_stop(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                if bool(payload.get("all")):
                    self._svc.stop_all()
                    return
                npc_id = payload.get("npcId") or payload.get("npc_id")
                if npc_id:
                    self._svc.stop_npc(str(npc_id))

            # ── npcStartAll — spawn all NPCs from config ─────────────────
            def _on_start_all(evt):
                cfg = self._npc_config
                if not cfg or not cfg.get("npcs"):
                    print("[npc_controller] npcStartAll: no NPC config loaded")
                    return
                default_model = cfg.get("defaultModel")
                for npc in cfg["npcs"]:
                    self._svc.spawn_npc(
                        npc_id=str(npc["npcId"]),
                        prim_path=str(npc["primPath"]),
                        route_id=str(npc.get("routeId", npc["npcId"])),
                        speed=float(npc.get("speed", cfg.get("speed", 200))),
                        loop=bool(npc.get("loop", cfg.get("loop", True))),
                        start_ref=npc.get("start"),
                        end_ref=npc.get("end"),
                        draw_path=bool(npc.get("drawPath", cfg.get("drawPath", False))),
                        model=str(npc.get("model", default_model)) if npc.get("model") or default_model else None,
                    )

            # ── npcStopAll — stop and remove all active NPCs ─────────────
            def _on_stop_all(evt):
                self._svc.stop_all()

            # ── navmeshRouteWaypoints (forward to service) ────────────────
            def _on_waypoints(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                self._svc.on_route_waypoints(payload)

            _observe("npcSpawn", _on_spawn)
            _observe("npcStop", _on_stop)
            _observe("npcStartAll", _on_start_all)
            _observe("npcStopAll", _on_stop_all)
            _observe("navmeshRouteWaypoints", _on_waypoints, order=20)

            print(f"[npc_controller] Extension started ({ext_id})")
        except Exception as e:
            print(f"[npc_controller] subscribe failed: {e}")

    @staticmethod
    def _load_config(ext_id: str) -> dict:
        """Load NPC definitions from config/npc_configs.json next to extension.toml."""
        try:
            import omni.kit.app
            ext_mgr = omni.kit.app.get_app().get_extension_manager()
            ext_path = ext_mgr.get_extension_path(ext_id)
            config_path = os.path.join(ext_path, "config", "npc_configs.json")
            with open(config_path, "r") as f:
                cfg = json.load(f)
            print(f"[npc_controller] Loaded {len(cfg.get('npcs', []))} NPC(s) from {config_path}")
            return cfg
        except Exception as e:
            print(f"[npc_controller] Failed to load npc_configs.json: {e}")
            return {}

    def on_shutdown(self):
        if getattr(self, "_svc", None):
            try:
                self._svc.shutdown()
            except Exception:
                pass
        self._subs.clear()
        self._svc = None
