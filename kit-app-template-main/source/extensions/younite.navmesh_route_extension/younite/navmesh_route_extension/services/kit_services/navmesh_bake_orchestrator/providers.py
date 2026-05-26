"""Concrete ``NavMeshAreaProvider`` implementations."""

from __future__ import annotations

# Must match obstacle_detection.OBSTACLES_PARENT_PATH
DEPTH_OBSTACLES_ROOT = "/World/CameraDepthObstacles"


def set_camera_depth_areas_visible(visible: bool) -> None:
    """Show / hide the camera-depth obstacle area meshes.

    Routes through the payload orchestrator when available. Falls back
    to direct attr manipulation so the bake orchestrator still works
    if the payload orchestrator hasn't started yet.
    """
    try:
        import omni.usd
        from pxr import Usd, UsdGeom

        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        if not stage:
            return
        root = stage.GetPrimAtPath(DEPTH_OBSTACLES_ROOT)
        if not root or not root.IsValid():
            return

        from younite.payload_orchestrator_core_extension import Priority, batch_show_hide

        items = [
            (prim.GetPath().pathString, visible)
            for prim in Usd.PrimRange(root)
            if prim.IsA(UsdGeom.Imageable)
        ]
        if batch_show_hide(
            items,
            Priority.MEDIUM,
            source="camera_depth_obstacles",
            group="camera_depth_areas",
        ):
            print(
                f"[BAKE_ORCH] camera_depth areas visible={visible} ({len(items)} prims) -> orchestrator"
            )
            return

        token = UsdGeom.Tokens.inherited if visible else UsdGeom.Tokens.invisible
        count = 0
        for prim in Usd.PrimRange(root):
            if prim.IsA(UsdGeom.Imageable):
                UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(token)
                count += 1
        print(f"[BAKE_ORCH] camera_depth areas visible={visible} ({count} prims)")
    except Exception as exc:
        import traceback

        traceback.print_exc()
        print(f"[BAKE_ORCH] set_camera_depth_areas_visible({visible}) failed: {exc}")


class CameraAreaProvider:
    """Wraps ``camera_navmesh_areas.py`` functions."""

    def __init__(self) -> None:
        self._active = False
        self._show_areas = False

    @property
    def name(self) -> str:
        return "camera_areas"

    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = bool(active)

    @property
    def show_areas(self) -> bool:
        return self._show_areas

    def set_show_areas(self, visible: bool) -> None:
        self._show_areas = bool(visible)
        from ....scripts.camera_navmesh_areas import set_camera_area_cubes_visible

        set_camera_area_cubes_visible(visible)

    def get_area_definitions(self) -> list:
        """Return one area definition per discovered camera."""
        try:
            from ....scripts.camera_navmesh_areas import (
                _CAMERA_COLORS,
                get_camera_area_names,
            )

            names = get_camera_area_names()
            defs = []
            for i, area_name in enumerate(names.values()):
                color = _CAMERA_COLORS[i % len(_CAMERA_COLORS)][0]
                defs.append(
                    {
                        "areaName": area_name,
                        "color": list(color),
                        "defaultCost": 1.0,
                    }
                )
            return defs
        except Exception:
            return []

    def prepare_for_bake(self) -> None:
        from ....scripts.camera_navmesh_areas import (
            apply_navmesh_api_to_areas,
            set_camera_area_cubes_visible,
        )

        apply_navmesh_api_to_areas()
        set_camera_area_cubes_visible(True)

    def after_bake(self) -> None:
        if not self._show_areas:
            from ....scripts.camera_navmesh_areas import set_camera_area_cubes_visible

            set_camera_area_cubes_visible(False)

    def remove_areas(self) -> None:
        from ....scripts.camera_navmesh_areas import remove_navmesh_api_from_areas

        remove_navmesh_api_from_areas()


class SoundAreaProvider:
    """Wraps ``sound_navmesh_areas.py`` (fixed-size areas, cost sliders)."""

    def __init__(self) -> None:
        self._active = False
        self._show_areas = False

    @property
    def name(self) -> str:
        return "sound_areas"

    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = bool(active)

    @property
    def show_areas(self) -> bool:
        return self._show_areas

    def set_show_areas(self, visible: bool) -> None:
        self._show_areas = bool(visible)
        from younite.sound_area_extension.scripts.sound_navmesh_areas import (
            set_sound_areas_visible,
        )

        set_sound_areas_visible(visible)

    def get_area_definitions(self) -> list:
        """Return one area definition per discovered sound location."""
        try:
            from younite.sound_area_extension.scripts.sound_navmesh_areas import (
                _SOUND_COLORS,
                get_sound_location_names,
            )

            names = get_sound_location_names()
            defs = []
            for i, area_name in enumerate(names.values()):
                color = _SOUND_COLORS[i % len(_SOUND_COLORS)][0]
                defs.append(
                    {
                        "areaName": area_name,
                        "color": list(color),
                        "defaultCost": 1.0,
                    }
                )
            return defs
        except Exception:
            return []

    def prepare_for_bake(self) -> None:
        from younite.sound_area_extension.scripts.sound_navmesh_areas import (
            ensure_sound_areas,
            set_sound_areas_visible,
        )

        ensure_sound_areas()
        set_sound_areas_visible(True)

    def after_bake(self) -> None:
        if not self._show_areas:
            from younite.sound_area_extension.scripts.sound_navmesh_areas import (
                set_sound_areas_visible,
            )

            set_sound_areas_visible(False)

    def remove_areas(self) -> None:
        from younite.sound_area_extension.scripts.sound_navmesh_areas import (
            remove_sound_areas,
        )

        remove_sound_areas()


class IncidentAreaProvider:
    """Incident placement — prims stay on the nav layer; prepare/after are no-ops."""

    def __init__(self) -> None:
        self._active = True

    @property
    def name(self) -> str:
        return "incidents"

    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = bool(active)

    def prepare_for_bake(self) -> None:
        pass

    def after_bake(self) -> None:
        pass

    def remove_areas(self) -> None:
        try:
            from younite.incident_extension.incident_placement_service import (
                remove_all_incidents,
            )

            remove_all_incidents()
        except Exception as exc:
            print(f"[BAKE_ORCH] incident remove_areas failed: {exc}")


class CameraDepthObstacleProvider:
    """Camera-depth obstacles — visibility via ``set_camera_depth_areas_visible``."""

    def __init__(self) -> None:
        self._active = True
        self._show_areas = False

    @property
    def name(self) -> str:
        return "camera_depth_obstacles"

    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = bool(active)

    @property
    def show_areas(self) -> bool:
        return self._show_areas

    def set_show_areas(self, visible: bool) -> None:
        self._show_areas = bool(visible)
        set_camera_depth_areas_visible(visible)

    def prepare_for_bake(self) -> None:
        set_camera_depth_areas_visible(True)

    def after_bake(self) -> None:
        if not self._show_areas:
            set_camera_depth_areas_visible(False)

    def remove_areas(self) -> None:
        try:
            from younite.camera_depth_extension.obstacle_detection import (
                remove_obstacle_areas,
            )

            remove_obstacle_areas()
        except Exception as exc:
            print(f"[BAKE_ORCH] camera_depth remove_areas failed: {exc}")
