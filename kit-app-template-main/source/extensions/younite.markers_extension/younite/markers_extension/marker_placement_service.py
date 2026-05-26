import time
from typing import Optional


class MarkerPlacementService:
    """Place visual markers (cubes) at world positions."""

    def __init__(self):
        self._markers_parent_path = "/ClickMarkers"

    def place_marker(self, world_pos: tuple, normal: Optional[tuple] = None, size: float = 100.0) -> Optional[str]:
        try:
            import omni.usd
            from pxr import UsdGeom, Gf, UsdPhysics

            stage = omni.usd.get_context().get_stage()
            if not stage:
                print("[MARKER] No stage available for creating marker")
                return None

            marker_name = f"ClickMarker_{int(time.time() * 1000)}"
            marker_path = f"{self._markers_parent_path}/{marker_name}"

            markers_parent = stage.GetPrimAtPath(self._markers_parent_path)
            if not markers_parent or not markers_parent.IsValid():
                UsdGeom.Xform.Define(stage, self._markers_parent_path)

            cube = UsdGeom.Cube.Define(stage, marker_path)
            if not cube:
                print("[MARKER] Failed to define cube")
                return None

            cube.GetSizeAttr().Set(float(size))

            xform = UsdGeom.Xformable(cube)
            xform.ClearXformOpOrder()
            translate_op = xform.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
            translate_op.Set(Gf.Vec3d(world_pos[0], world_pos[1], world_pos[2]))

            from younite.payload_orchestrator_core_extension import show, Priority
            if not show(self._markers_parent_path, Priority.HIGH, source="markers"):
                UsdGeom.Imageable(cube).MakeVisible()
            show(marker_path, Priority.HIGH, source="markers")

            # Optional: collider so PhysX raycasts can hit markers too
            try:
                prim = stage.GetPrimAtPath(marker_path)
                if prim and prim.IsValid():
                    UsdPhysics.CollisionAPI.Apply(prim)
            except Exception:
                pass

            print(f"[MARKER] ✓ Created marker cube at {marker_path}")
            return marker_path
        except Exception as e:
            print(f"[MARKER] Error creating marker cube: {e}")
            return None

