import random

import omni.ext


class IncidentExtension(omni.ext.IExt):
    """Incident placement: consume pick results with intent='incident',
    create a cube + NavMesh area, and trigger rebake."""

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []

        from .incident_placement_service import IncidentPlacementService
        self._placement = IncidentPlacementService()

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
                dispatch_to_events2,
            )

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.incident_extension/{name}",
                        event_name=name,
                        on_event=handler,
                        order=0,
                    )
                )

            def _on_pick_result(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                intent = str(payload.get("intent") or "")
                if intent not in ("incident", "incident.place", "addincident"):
                    return
                hit = payload.get("hit")
                if not hit or not isinstance(hit, dict) or not hit.get("world"):
                    print("[incident] pick result has no hit.world")
                    return
                w = hit["world"]
                try:
                    pos = (float(w.get("x")), float(w.get("y")), float(w.get("z")))
                    label = payload.get("label") or payload.get("incidentLabel") or "Incident"
                    width = float(payload["incidentWidth"]) if "incidentWidth" in payload else None
                    depth = float(payload["incidentDepth"]) if "incidentDepth" in payload else None
                    shape = str(payload["incidentShape"]) if "incidentShape" in payload else None
                    path = self._placement.place_incident(
                        pos, label=label, width=width, depth=depth, shape=shape)
                    if path:
                        severity = random.randint(1, 5)
                        dispatch_to_events2("incidentAdded", {
                            "incidentPath": path,
                            "position": {"x": pos[0], "y": pos[1], "z": pos[2]},
                            "label": label,
                            "severity": severity,
                            "status": "reported",
                        })
                        dispatch_to_events2("navmeshRebakeRequest", {})
                    else:
                        print("[incident] place_incident returned None")
                except Exception as e:
                    print(f"[incident] placement failed: {e}")
                    import traceback
                    traceback.print_exc()

            def _on_placement_toggle(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                enabled = bool(payload.get("enabled", False))
                if not enabled:
                    from .incident_placement_service import remove_all_incidents
                    count = remove_all_incidents()
                    if count > 0:
                        dispatch_to_events2("incidentsCleared", {"count": count})
                        dispatch_to_events2("navmeshRebakeRequest", {})

            def _on_remove(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                incident_path = payload.get("incidentPath") or payload.get("incident_path")
                if not incident_path:
                    return
                from .incident_placement_service import remove_single_incident
                if remove_single_incident(str(incident_path)):
                    dispatch_to_events2("incidentRemoved", {"incidentPath": incident_path})
                    if not payload.get("skipRebake", False):
                        dispatch_to_events2("navmeshRebakeRequest", {})

            _observe("younite.pick.result", _on_pick_result)
            _observe("incidentPlacementToggle", _on_placement_toggle)
            _observe("incidentRemove", _on_remove)
            print("[incident] extension loaded")
        except Exception as e:
            print(f"[incident] startup failed: {e}")
            import traceback
            traceback.print_exc()

    def on_shutdown(self):
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
        self._placement = None
