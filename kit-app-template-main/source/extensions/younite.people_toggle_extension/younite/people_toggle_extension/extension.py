import omni.ext


TRAFFIC_PEOPLE_PRIM_PATH = "/World/cctv1_crowd"
SEATED_CROWD_PRIM_PATH = "/World/Skandinavium/seated_people"
SEATED_CROWD_VARIANT_SET = "crowd_density"
SEATED_CROWD_DEFAULT_VARIANT = "dense"


class PeopleToggleExtension(omni.ext.IExt):
    """
    Master "Display crowd" handler — toggles the traffic-density crowd
    (/World/cctv1_crowd) and switches the seated-crowd density variant
    (/World/Skandinavium/seated_people).

    The animated /World/test_people layer (formerly toggled here) was
    removed; the seated PointInstancer crowd replaces it. The seated
    crowd's actual on/off is driven from the web side: the same CU
    "Display crowd" toggle dispatches `peopleToggle` (handled here for
    the traffic crowd) AND `seatedCrowdLayoutChange` (handled here as
    the seated-crowd variant switch — `dense` = on, `none` = off).

    Traffic-density people: the slider sends `peopleDensityUpdate` with
    a density value (1-15) and this extension shows a proportional
    number of child prims.
    """

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []
        self._usd_sub = None
        self._enabled = False
        self._last_density = 1.0
        self._last_max_density = 15.0

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb
            from younite.messaging_core_extension.message_utils import (
                normalize_event_payload,
                dispatch_to_events2,
            )
            import omni.usd

            ed = carb.eventdispatcher.get_eventdispatcher()
            for _evt_name in ("peopleToggle", "peopleDensityUpdate", "seatedCrowdLayoutChange"):
                try:
                    kit_app.register_event_alias(
                        carb.events.type_from_string(_evt_name), _evt_name,
                    )
                except Exception:
                    pass

            from younite.payload_orchestrator_core_extension import show_hide, batch_show_hide, Priority

            def _set_traffic_visibility(visible: bool):
                """Hide or show the entire traffic people group (no-op if prim missing)."""
                try:
                    stage = omni.usd.get_context().get_stage()
                    if not stage:
                        return
                    prim = stage.GetPrimAtPath(TRAFFIC_PEOPLE_PRIM_PATH)
                    if not prim or not prim.IsValid():
                        return
                except Exception:
                    return
                show_hide(TRAFFIC_PEOPLE_PRIM_PATH, visible, Priority.HIGH, source="people_toggle")

            def _set_traffic_density(density: float, max_density: float):
                """Show a proportional number of peoples_test_02 children.

                density=1 -> 1 person visible, density=max_density -> all visible.
                Only applies when the people toggle is enabled.
                """
                self._last_density = density
                self._last_max_density = max_density

                if not self._enabled:
                    return

                try:
                    stage = omni.usd.get_context().get_stage()
                    if not stage:
                        return
                    parent = stage.GetPrimAtPath(TRAFFIC_PEOPLE_PRIM_PATH)
                    if not parent.IsValid():
                        print(f"[people_toggle] traffic prim {TRAFFIC_PEOPLE_PRIM_PATH} not found")
                        return

                    show_hide(TRAFFIC_PEOPLE_PRIM_PATH, True, Priority.HIGH, source="people_toggle")

                    children = [c for c in parent.GetChildren() if c.IsValid()]
                    total = len(children)
                    if total == 0:
                        return

                    count = max(1, round(density / max_density * total))
                    count = min(count, total)

                    items = [(child.GetPath().pathString, i < count) for i, child in enumerate(children)]
                    batch_show_hide(items, Priority.HIGH, source="people_toggle", group="people_density")

                    print(f"[people_toggle] traffic density: {count}/{total} people visible (slider={density})")
                except Exception as e:
                    print(f"[people_toggle] traffic density update failed: {e}")

            def _on_toggle(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                self._enabled = bool(payload.get("enabled", not self._enabled))
                print(f"[people_toggle] crowd {'enabled' if self._enabled else 'disabled'}")
                if self._enabled:
                    _set_traffic_density(self._last_density, self._last_max_density)
                else:
                    _set_traffic_visibility(False)
                dispatch_to_events2("peopleToggleStatus", {"enabled": self._enabled})

            def _on_density(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                density = float(payload.get("density", 1.0))
                max_density = float(payload.get("maxDensity", 15.0))
                _set_traffic_density(density, max_density)

            def _seated_crowd_variant_set():
                """Returns (vset, available_variants_list) or (None, [])."""
                try:
                    stage = omni.usd.get_context().get_stage()
                    if not stage:
                        return None, []
                    prim = stage.GetPrimAtPath(SEATED_CROWD_PRIM_PATH)
                    if not prim or not prim.IsValid():
                        return None, []
                    vsets = prim.GetVariantSets()
                    if SEATED_CROWD_VARIANT_SET not in vsets.GetNames():
                        return None, []
                    vset = vsets.GetVariantSet(SEATED_CROWD_VARIANT_SET)
                    return vset, list(vset.GetVariantNames())
                except Exception as e:
                    print(f"[people_toggle] seated crowd variant lookup failed: {e}")
                    return None, []

            def _on_seated_crowd_layout_change(evt):
                payload = normalize_event_payload(getattr(evt, "payload", None) or {})
                requested = str(payload.get("variant") or payload.get("layout") or "").strip()

                vset, variants = _seated_crowd_variant_set()
                if vset is None:
                    dispatch_to_events2("seatedCrowdLayoutChanged", {
                        "variant": "", "success": False, "variants": [],
                        "error": "seated_crowd_not_found",
                    })
                    return

                if not requested:
                    current = vset.GetVariantSelection() or SEATED_CROWD_DEFAULT_VARIANT
                    dispatch_to_events2("seatedCrowdLayoutChanged", {
                        "variant": current, "success": True, "variants": variants,
                    })
                    return

                if requested not in variants:
                    dispatch_to_events2("seatedCrowdLayoutChanged", {
                        "variant": requested, "success": False, "variants": variants,
                        "error": "unknown_variant",
                    })
                    return

                old = vset.GetVariantSelection()
                vset.SetVariantSelection(requested)
                print(f"[people_toggle] seated crowd density: '{old}' -> '{requested}'")
                dispatch_to_events2("seatedCrowdLayoutChanged", {
                    "variant": requested, "success": True, "variants": variants,
                })

            self._subs.append(
                ed.observe_event(
                    observer_name="younite.people_toggle_extension/peopleToggle",
                    event_name="peopleToggle",
                    on_event=_on_toggle,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.people_toggle_extension/peopleDensityUpdate",
                    event_name="peopleDensityUpdate",
                    on_event=_on_density,
                    order=0,
                )
            )
            self._subs.append(
                ed.observe_event(
                    observer_name="younite.people_toggle_extension/seatedCrowdLayoutChange",
                    event_name="seatedCrowdLayoutChange",
                    on_event=_on_seated_crowd_layout_change,
                    order=0,
                )
            )

            # On stage open: crowd is off by default.
            # Traffic people default to showing 1 person (density=1) once enabled.
            try:
                import carb.eventdispatcher

                def _on_stage_event(e):
                    try:
                        from omni.usd import StageEventType
                        et = int(getattr(e, "type", 0))
                        if et == int(StageEventType.OPENED):
                            self._enabled = False
                            self._last_density = 1.0
                            self._last_max_density = 15.0
                            _set_traffic_visibility(False)
                            dispatch_to_events2("peopleToggleStatus", {"enabled": False})
                    except Exception:
                        pass

                ed = carb.eventdispatcher.get_eventdispatcher()
                self._usd_sub = ed.observe_event(
                    observer_name="younite.people_toggle_extension/stage_events",
                    event_name="omni.usd@stage_event",
                    on_event=_on_stage_event,
                    order=0,
                )
            except Exception as e:
                print(f"[people_toggle] stage event subscribe failed: {e}")

        except Exception as e:
            print(f"[people_toggle] startup failed: {e}")

    def on_shutdown(self):
        if getattr(self, "_usd_sub", None):
            self._usd_sub = None
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
