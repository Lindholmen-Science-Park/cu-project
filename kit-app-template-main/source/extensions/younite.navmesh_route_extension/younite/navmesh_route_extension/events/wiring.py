"""Shared carb event wiring helpers for the navmesh route extension."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class NavmeshWireContext:
    """Mutable bag passed through event registration modules."""

    ext: Any
    ed: Any
    carb: Any
    kit_app: Any
    observe: Callable[[str, Callable], None]
    normalize_event_payload: Callable[..., dict]
    poi_configs: dict[str, dict] = field(default_factory=dict)
    waypoint_route_ids: frozenset = field(default_factory=frozenset)


def make_observe(ext, ed) -> Callable[[str, Callable], None]:
    subs = ext._subs

    def _alias(name: str) -> None:
        try:
            import carb
            import omni.kit.app as kit_app_mod

            kit_app_mod.register_event_alias(carb.events.type_from_string(name), name)
        except Exception:
            pass

    def observe(name: str, handler: Callable) -> None:
        _alias(name)
        subs.append(
            ed.observe_event(
                observer_name=f"younite.navmesh_route_extension/{name}",
                event_name=name,
                on_event=handler,
                order=0,
            )
        )

    return observe


def make_view_transition_dispatchers(ed: Any) -> tuple[Callable[[bool], None], Callable]:
    _STREAM_SETTLE_FRAMES = 4

    def dispatch_view_transition_ready(success: bool) -> None:
        try:
            ed.dispatch_event("viewTransitionReady", {
                "result": "success" if success else "error",
            })
        except Exception:
            pass

    async def dispatch_view_transition_ready_after_settle(success: bool) -> None:
        try:
            import omni.kit.app as kit_app

            for _ in range(_STREAM_SETTLE_FRAMES):
                await kit_app.get_app().next_update_async()
        except Exception:
            pass
        dispatch_view_transition_ready(success)

    return dispatch_view_transition_ready, dispatch_view_transition_ready_after_settle
