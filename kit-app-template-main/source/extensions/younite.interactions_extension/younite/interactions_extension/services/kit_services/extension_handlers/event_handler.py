"""Carb / USD stage Events 2.0 subscriptions and handler methods."""
from __future__ import annotations


class _InteractionEventHandler:
    """Base supplying pick, marker, trigger, dev, and stage event handlers."""

    def _on_trigger_entered(self, trigger) -> None:
        try:
            from younite.messaging_core_extension.message_utils import dispatch_to_events2

            dispatch_to_events2(self.POINT_TRIGGERED_EVENT, {
                "pointId": trigger.trigger_id,
                "triggerType": trigger.trigger_type,
                "behaviors": trigger.behaviors,
            })
            print(
                f"[interactions] Triggered: {trigger.trigger_id} "
                f"(type={trigger.trigger_type}, behaviors={len(trigger.behaviors)})"
            )
        except Exception as e:
            print(f"[interactions] trigger dispatch failed: {e}")

    def _subscribe_events(self) -> None:
        try:
            import carb
            import carb.eventdispatcher
            import omni.kit.app as kit_app

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler, order=0):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.interactions_extension/{name}",
                        event_name=name,
                        on_event=handler,
                        order=order,
                    )
                )

            _observe("younite.pick.response", self._on_pick_response)
            _observe("uiInteractionBoxesToggle", self._on_interaction_boxes_toggle)
            _observe("npcMarkers.hide", self._on_markers_hide)
            _observe("npcMarkers.show", self._on_markers_show)
            _observe("interactionPointActivate", self._on_activate_trigger)
            _observe("interactionPointDeactivate", self._on_deactivate_trigger)
            _observe("navigationStateSet", self._on_navigation_state)
            _observe("autoMoveStatus", self._on_auto_move_status)
            _observe("navmeshRouteWaypoints", self._on_waypoints, order=10)
            _observe("devMediaRegistryRequest", self._on_dev_media_registry_request)
            _observe("devLocaleJsonWrite", self._on_dev_locale_json_write)
            _observe("scene.loaded", self._on_scene_loaded_retry_config)
        except Exception as e:
            print(f"[interactions] subscribe failed: {e}")

    def _subscribe_stage_events(self) -> None:
        try:
            import carb.eventdispatcher

            ed = carb.eventdispatcher.get_eventdispatcher()
            self._stage_sub = ed.observe_event(
                observer_name="younite.interactions_extension/stage_events",
                event_name="omni.usd@stage_event",
                on_event=self._on_stage_event,
                order=0,
            )
        except Exception:
            self._stage_sub = None

    def _payload(self, evt) -> dict:
        from younite.messaging_core_extension.message_utils import normalize_event_payload
        return normalize_event_payload(getattr(evt, "payload", None) or {})

    def _on_scene_loaded_retry_config(self, _evt=None) -> None:
        try:
            if self._config_loader is not None:
                self._config_loader.reset()
            self._force_reload_config()
        except Exception:
            pass

    def _on_pick_response(self, evt) -> None:
        self._click_router.handle_pick_response(self._payload(evt))

    def _on_interaction_boxes_toggle(self, evt) -> None:
        self._enabled_range = bool(self._payload(evt).get("enabled", False))

    def _on_markers_hide(self, _evt) -> None:
        try:
            self._marker_service.hide()
        except Exception:
            pass

    def _on_markers_show(self, _evt) -> None:
        try:
            self._marker_service.show()
        except Exception:
            pass

    def _on_activate_trigger(self, evt) -> None:
        payload = self._payload(evt)
        point_id = str(payload.get("pointId") or payload.get("id") or "")
        if not point_id or not self._spatial_service:
            return
        if self._spatial_service.activate(point_id):
            print(f"[interactions] Activated: {point_id}")
        else:
            print(f"[interactions] Activate failed (not found): {point_id}")

    def _on_deactivate_trigger(self, evt) -> None:
        payload = self._payload(evt)
        point_id = str(payload.get("pointId") or payload.get("id") or "")
        if not point_id or not self._spatial_service:
            return
        if self._spatial_service.deactivate(point_id):
            print(f"[interactions] Deactivated: {point_id}")

    def _on_navigation_state(self, evt) -> None:
        payload = self._payload(evt)
        if "autoMove" not in payload:
            return
        entering = bool(payload.get("autoMove"))
        if entering and not self._auto_move_active:
            self._auto_move_active = True
            self._clear_interaction_state()
        elif not entering and self._auto_move_active:
            self._auto_move_active = False

    def _on_auto_move_status(self, evt) -> None:
        if not bool(self._payload(evt).get("active", False)) and self._auto_move_active:
            self._auto_move_active = False

    def _on_waypoints(self, evt) -> None:
        payload = self._payload(evt)
        route_id = str(payload.get("routeId") or payload.get("route_id") or "")
        if not route_id or not self._spatial_service:
            return
        if not bool(payload.get("success", True)):
            return
        points = payload.get("points") or []
        if not points:
            return
        last = points[-1]
        if not isinstance(last, (list, tuple)) or len(last) < 3:
            return
        new_pos = (float(last[0]), float(last[1]), float(last[2]))
        if self._spatial_service.update_position(route_id, new_pos):
            print(
                f"[interactions] {route_id} refined to navmesh endpoint "
                f"({new_pos[0]:.1f}, {new_pos[1]:.1f}, {new_pos[2]:.1f})"
            )

    def _on_stage_event(self, e) -> None:
        try:
            from omni.usd import StageEventType
            if int(getattr(e, "type", 0)) == int(StageEventType.OPENED):
                self._on_stage_opened()
        except Exception:
            pass

    def _on_stage_opened(self) -> None:
        if self._spatial_service:
            self._spatial_service.clear_all()
        self._all_points = []
        self._projectable_points = []
        self._click_points_by_path = {}
        self._npc_registry = {}
        self._icon_registry = {}
        self._nearest_npc.reset()
        self._nearest_icon.reset()
        self._projectables_loop.reset()
        self._config_loader.reset()
        print("[interactions] Stage opened - all state cleared, config will reload")

    def _on_dev_media_registry_request(self, evt) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
            )

            payload = self._payload(evt)
            patterns = payload.get("patterns")
            if not isinstance(patterns, list) or not patterns:
                patterns = ["video_360_*", "spatial_sound_*"]
            items: list = []
            for pat in patterns:
                pstr = str(pat or "").strip()
                if not pstr:
                    continue
                for prim_path, leaf in self._usd_helpers.find_xforms_by_glob(pstr):
                    pos = self._usd_helpers.resolve_prim_position(prim_path)
                    items.append(
                        {
                            "pattern": pstr,
                            "primPath": prim_path,
                            "primName": leaf,
                            "worldTranslate": [pos[0], pos[1], pos[2]] if pos else None,
                        }
                    )
            dispatch_to_events2("devMediaRegistryResponse", {"items": items})
        except Exception as e:
            try:
                from younite.messaging_core_extension.message_utils import (
                    dispatch_to_events2,
                )

                dispatch_to_events2(
                    "devMediaRegistryResponse",
                    {"items": [], "error": str(e)},
                )
            except Exception:
                pass

    def _on_dev_locale_json_write(self, evt) -> None:
        try:
            from younite.messaging_core_extension.message_utils import (
                dispatch_to_events2,
            )

            payload = self._payload(evt)
            locale = str(payload.get("locale") or "").strip().lower()
            patch = payload.get("patch") or {}
            inter = patch.get("interactions") if isinstance(patch, dict) else None
            if not locale or not isinstance(inter, dict):
                dispatch_to_events2(
                    "devLocaleJsonWriteResult",
                    {"ok": False, "error": "locale and patch.interactions required"},
                )
                return

            from ....dev_locale_io import resolve_interactions_config_path, write_locale_patch

            cfg_path = resolve_interactions_config_path(self._settings)
            if not cfg_path:
                dispatch_to_events2(
                    "devLocaleJsonWriteResult",
                    {"ok": False, "error": "interactions.json path not resolved"},
                )
                return

            ok, msg = write_locale_patch(
                interactions_path=cfg_path,
                locale=locale,
                patch_interactions=inter,
            )
            dispatch_to_events2(
                "devLocaleJsonWriteResult",
                {"ok": ok, "message": msg},
            )
        except Exception as e:
            try:
                from younite.messaging_core_extension.message_utils import (
                    dispatch_to_events2,
                )

                dispatch_to_events2(
                    "devLocaleJsonWriteResult",
                    {"ok": False, "error": str(e)},
                )
            except Exception:
                pass
