"""Draw / clear an OSM route as a BasisCurves ribbon on the session layer."""

import math
from pxr import Gf, Usd, UsdGeom

ROUTE_PRIM_PATH = "/World/OSM_Route"
ROUTE_COLOR = Gf.Vec3f(0.0, 0.95, 0.95)  # bright cyan
ROUTE_WIDTH = 250.0

ROUTE_HOVER = 200.0        # 2 m above terrain surface
SUBDIVIDE_MAX_CM = 1000.0  # max 10 m between points — subdivide longer segments


def _subdivide(coords: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    """Insert intermediate points so no segment exceeds SUBDIVIDE_MAX_CM.
    Y values are linearly interpolated between endpoints."""
    if len(coords) < 2:
        return list(coords)

    result: list[tuple[float, float, float]] = [coords[0]]
    for i in range(1, len(coords)):
        ax, ay, az = coords[i - 1]
        bx, by, bz = coords[i]
        dx, dy, dz = bx - ax, by - ay, bz - az
        seg_len = math.hypot(dx, dz)

        if seg_len > SUBDIVIDE_MAX_CM:
            steps = int(math.ceil(seg_len / SUBDIVIDE_MAX_CM))
            for s in range(1, steps):
                t = s / steps
                result.append((ax + dx * t, ay + dy * t, az + dz * t))

        result.append((bx, by, bz))
    return result


def draw_route(stage: Usd.Stage, coords: list[tuple[float, float, float]]) -> None:
    """Create (or replace) a single BasisCurves prim for the route.
    Uses the Y values from the input coords (terrain-baked from the graph)
    plus ROUTE_HOVER offset."""
    clear_route(stage)

    if len(coords) < 2:
        return

    dense = _subdivide(coords)

    session = stage.GetSessionLayer()
    with Usd.EditContext(stage, session):
        curves = UsdGeom.BasisCurves.Define(stage, ROUTE_PRIM_PATH)
        curves.CreateTypeAttr("linear")
        curves.CreateCurveVertexCountsAttr([len(dense)])

        points = [Gf.Vec3f(x, y + ROUTE_HOVER, z) for x, y, z in dense]
        curves.CreatePointsAttr(points)
        curves.CreateWidthsAttr([ROUTE_WIDTH] * len(points))
        curves.GetDisplayColorAttr().Set([ROUTE_COLOR])


def clear_route(stage: Usd.Stage) -> None:
    """Remove the route prim if it exists."""
    prim = stage.GetPrimAtPath(ROUTE_PRIM_PATH)
    if prim and prim.IsValid():
        session = stage.GetSessionLayer()
        with Usd.EditContext(stage, session):
            stage.RemovePrim(ROUTE_PRIM_PATH)
