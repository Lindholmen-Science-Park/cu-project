import asyncio
import omni.ext


# ── module-level BBoxCache for _resolve_prim_at_world_point ──────────
_bbox_cache = None
_bbox_cache_stage_id = None


def _resolve_prim_at_world_point(stage, world_pos, tolerance=0.1, max_prims=5000):
    """
    Last-resort prim resolver: find the smallest UsdGeom.Gprim whose world
    bounding box contains *world_pos*.

    Uses a module-level BBoxCache so computed bounds persist across calls
    (cleared automatically when the stage object changes).
    *max_prims* caps the iteration to avoid stalling on very large scenes.
    """
    global _bbox_cache, _bbox_cache_stage_id
    if not stage or not world_pos or len(world_pos) < 3:
        return None
    try:
        from pxr import Usd, UsdGeom, Gf

        x, y, z = float(world_pos[0]), float(world_pos[1]), float(world_pos[2])

        current_id = id(stage)
        if _bbox_cache is None or _bbox_cache_stage_id != current_id:
            _bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
            _bbox_cache_stage_id = current_id
        cache = _bbox_cache

        candidates = []
        checked = 0
        for prim in stage.Traverse():
            if not prim.IsA(UsdGeom.Gprim):
                continue
            checked += 1
            if checked > max_prims:
                break
            try:
                bbox = cache.ComputeWorldBound(prim)
                r = bbox.ComputeAlignedBox() if hasattr(bbox, "ComputeAlignedBox") else bbox.GetRange()
                mn, mx = r.GetMin(), r.GetMax()
                if not (
                    mn[0] - tolerance <= x <= mx[0] + tolerance
                    and mn[1] - tolerance <= y <= mx[1] + tolerance
                    and mn[2] - tolerance <= z <= mx[2] + tolerance
                ):
                    continue
                vol = (mx[0] - mn[0]) * (mx[1] - mn[1]) * (mx[2] - mn[2])
                if vol <= 0:
                    continue
                candidates.append((vol, prim.GetPath().pathString))
            except Exception:
                continue
        if not candidates:
            return None
        candidates.sort(key=lambda t: t[0])
        return candidates[0][1]
    except Exception:
        return None


def _is_absolute_usd_prim_path(s: str) -> bool:
    """
    True only for absolute SdfPath-style strings.

    PhysX scene-query often fills ``collider`` with a **leaf name** (e.g. ``Pole``)
    with no ``/`` prefix. Treating that as ``primPath`` blocks the bbox fallback
    resolver and breaks downstream routing (IoT picks, clickables, etc.).
    """
    p = (s or "").strip()
    if not p.startswith("/"):
        return False
    # Require at least ``/Root/Child`` — reject ``/Pole`` and single-segment paths.
    return p.rfind("/") > 0


class PickingExtension(omni.ext.IExt):
    """
    Intent-based picking:
    - listens to `younite.pick.request`
    - emits `younite.pick.response` with requestId+intent and hit info
    - also emits legacy `younite.pick.result` for backward compatibility
    """

    def on_startup(self, ext_id: str):
        self._ext_id = ext_id
        self._subs = []

        self._raycast_interface = None
        try:
            import omni.kit.raycast.query as rcq
            self._raycast_interface = rcq.acquire_raycast_query_interface()
            print("[picking] ✓ raycast interface acquired")
        except Exception as e:
            print(f"[picking] ⚠️ raycast interface not available: {e}")

        from .raycast_service import RaycastService
        self._raycast_service = RaycastService(self._raycast_interface)

        try:
            import carb.eventdispatcher
            import omni.kit.app as kit_app
            import carb

            ed = carb.eventdispatcher.get_eventdispatcher()

            def _observe(name, handler):
                try:
                    kit_app.register_event_alias(carb.events.type_from_string(name), name)
                except Exception:
                    pass
                self._subs.append(
                    ed.observe_event(
                        observer_name=f"younite.picking_extension/{name}",
                        event_name=name,
                        on_event=handler,
                        order=0,
                    )
                )

            _observe("younite.pick.request", self._on_pick_request)
        except Exception as e:
            print(f"[picking] subscribe failed: {e}")

    # ── event handler (sync entry → async work) ─────────────────────

    def _on_pick_request(self, event):
        try:
            from younite.messaging_core_extension.message_utils import normalize_event_payload

            payload = normalize_event_payload(getattr(event, "payload", None) or {})
            request_id = str(payload.get("requestId") or "") or "missing_requestId"
            intent = str(payload.get("intent") or "")
            ndc_x = float(payload.get("ndcX", 0.0))
            ndc_y = float(payload.get("ndcY", 0.0))

            if not intent:
                try:
                    import carb.settings as carb_settings
                    s = carb_settings.get_settings()
                    if bool(s.get("/younite/markers/enabled")):
                        intent = "marker"
                except Exception:
                    pass
            if not intent:
                intent = "unknown"

            allow_navigation = bool(payload.get("allowNavigation", False))

            _KNOWN_KEYS = {"requestId", "intent", "ndcX", "ndcY", "allowNavigation"}
            extra = {k: v for k, v in payload.items() if k not in _KNOWN_KEYS}

            asyncio.ensure_future(
                self._handle_pick_async(
                    ndc_x, ndc_y,
                    request_id=request_id,
                    intent=intent,
                    allow_navigation=allow_navigation,
                    extra=extra,
                )
            )
        except Exception:
            pass

    # ── async pick handler ───────────────────────────────────────────

    async def _handle_pick_async(
        self,
        ndc_x: float,
        ndc_y: float,
        *,
        request_id: str,
        intent: str,
        allow_navigation: bool = False,
        extra: dict = None,
    ):
        try:
            res = await self._raycast_service.raycast_from_ndc_async(ndc_x, ndc_y)

            world_pos, normal, meta = None, None, {}
            try:
                if isinstance(res, (list, tuple)) and len(res) >= 3:
                    world_pos, normal, meta = res[0], res[1], res[2] or {}
                elif isinstance(res, (list, tuple)) and len(res) >= 2:
                    world_pos, normal = res[0], res[1]
            except Exception:
                pass

            hit = None
            if world_pos:
                hit = {
                    "world": {
                        "x": float(world_pos[0]),
                        "y": float(world_pos[1]),
                        "z": float(world_pos[2]),
                    },
                }
                if normal:
                    hit["normal"] = {
                        "x": float(normal[0]),
                        "y": float(normal[1]),
                        "z": float(normal[2]),
                    }

                # Extract prim identity from raycast meta
                try:
                    if isinstance(meta, dict):
                        # Prefer keys that are full paths. ``collider`` / ``rigidBody`` are
                        # often leaf names only — using them as primPath skips bbox resolve.
                        prim_path = None
                        for key in (
                            "primPath",
                            "prim_path",
                            "path",
                            "colliderPrimPath",
                            "bodyPrimPath",
                            "rigidBodyPrimPath",
                            "collider",
                            "rigidBody",
                        ):
                            v = meta.get(key)
                            if isinstance(v, str) and _is_absolute_usd_prim_path(v):
                                prim_path = v.strip()
                                break
                        if prim_path:
                            hit["primPath"] = prim_path
                            try:
                                hit["primName"] = prim_path.rstrip("/").rsplit("/", 1)[-1]
                            except Exception:
                                pass
                        hit["meta"] = dict(meta or {})
                except Exception:
                    pass

                # Last resort: resolve prim via USD bounding-box search
                if not hit.get("primPath") and world_pos:
                    try:
                        import omni.usd

                        usd_ctx = omni.usd.get_context()
                        stage = usd_ctx.get_stage() if usd_ctx else None
                        if stage:
                            resolved = _resolve_prim_at_world_point(stage, world_pos)
                            if isinstance(resolved, str) and resolved.strip():
                                hit["primPath"] = resolved.strip()
                                try:
                                    hit["primName"] = resolved.strip().rstrip("/").rsplit("/", 1)[-1]
                                except Exception:
                                    pass
                                if "meta" not in hit:
                                    hit["meta"] = {}
                                hit["meta"]["resolvedFromBounds"] = True
                    except Exception:
                        pass

            # Dispatch results (same contract as before)
            try:
                import carb.eventdispatcher as _ed

                payload = {
                    "requestId": request_id,
                    "intent": intent,
                    "hit": hit,
                    "allowNavigation": allow_navigation,
                }
                if extra:
                    payload.update(extra)
                _ed.get_eventdispatcher().dispatch_event("younite.pick.response", payload)
                _ed.get_eventdispatcher().dispatch_event("younite.pick.result", payload)

                if hit and world_pos:
                    name = hit.get("primName") or hit.get("primPath") or "world"
                    try:
                        print(
                            f"[picking] hit: {name} at "
                            f"({world_pos[0]:.1f}, {world_pos[1]:.1f}, {world_pos[2]:.1f})"
                        )
                    except Exception:
                        pass
            except Exception as ex:
                print(f"[picking] dispatch error: {ex}")

        except Exception as e:
            print(f"[picking] pick handle error: {e}")

    def on_shutdown(self):
        if getattr(self, "_subs", None) is not None:
            self._subs.clear()
