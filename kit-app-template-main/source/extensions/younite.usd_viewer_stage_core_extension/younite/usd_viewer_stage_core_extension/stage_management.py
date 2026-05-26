# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# Copied from the old monolithic implementation (keep behavior).

from pxr import UsdGeom, Usd

import carb
import carb.events
import carb.eventdispatcher
import omni.usd
from omni.kit.viewport.utility import get_active_viewport_camera_string


class StageManager:
    """This class manages the stage and its related events using Events 2.0."""

    def __init__(self):
        self._is_external_update: bool = False
        self._camera_attrs = {}
        self._subscriptions = []

        # subscribe to stage events using Events 2.0
        ed = carb.eventdispatcher.get_eventdispatcher()
        stage_observer = ed.observe_event(
            observer_name="younite.usd_viewer_stage_core_extension/stage_management/stage_events",
            event_name="omni.usd@stage_event",
            on_event=self._on_stage_event,
            order=0,
        )
        self._subscriptions.append(stage_observer)

    def get_children(self, prim_path, filters=None):
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return []
        prim = stage.GetPrimAtPath(prim_path)
        if not prim:
            return []

        filter_types = {
            "USDGeom": UsdGeom.Mesh,
            "mesh": UsdGeom.Mesh,
            "xform": UsdGeom.Xform,
            "scope": UsdGeom.Scope,
        }

        children = []
        for child in prim.GetChildren():
            if filters is not None:
                if not any(child.IsA(filter_types[filt]) for filt in filters if filt in filter_types):
                    continue

            child_name = child.GetName()
            child_path = str(prim.GetPath())
            if child_name.startswith('OmniverseKit_'):
                continue
            if prim_path == '/' and child_name == 'Render':
                continue
            child_path = child_path if child_path != '/' else ''
            info = {"name": child_name, "path": f'{child_path}/{child_name}'}
            if child.GetChildren():
                info["children"] = []
            children.append(info)

        return children

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.OPENED):
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            stage_url = stage.GetRootLayer().identifier

            if stage_url:
                ctx = omni.usd.get_context()
                ctx.set_pickable("/", False)
                self._camera_attrs.clear()
                camera_prim = stage.GetPrimAtPath(get_active_viewport_camera_string())
                if camera_prim:
                    for attr in camera_prim.GetAttributes():
                        self._camera_attrs[attr.GetName()] = attr.Get()

    def _on_sky_control(self, event: carb.events.IEvent):
        """Handle sky control request (kept here to keep stage access local). Returns apply_sky_control result for retry logic."""
        try:
            from younite.weather_and_seasons_extension.sky_service import apply_sky_control
            raw = getattr(event, "payload", None) or {}
            # Unwrap (payload,) if dispatched as tuple for backwards compatibility
            if isinstance(raw, (tuple, list)) and len(raw) == 1 and isinstance(raw[0], dict):
                raw = raw[0]
            return apply_sky_control(raw)
        except Exception as e:
            print(f"[stage_core] sky control error: {e}")
            return "no_env"

    def on_shutdown(self):
        self._subscriptions.clear()
        self._is_external_update = False
        self._camera_attrs.clear()

