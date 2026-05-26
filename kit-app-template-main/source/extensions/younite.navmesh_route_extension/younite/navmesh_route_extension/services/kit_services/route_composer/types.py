"""
Data types and tunables for :mod:`route_composer`.

Split out of the package root so the dataclasses can be imported
without dragging in the full composer / OSM graph stack. The module
is intentionally dependency-free (stdlib only) to stay safe to import
during Kit extension startup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


Vec3 = Tuple[float, float, float]


# ────────────────────────────────────────────────────────────────────
# Tunables
# ────────────────────────────────────────────────────────────────────

# XZ tolerance (cm) for "is this position on the NavMesh?" in the
# RouteComposer. Bird-eye pin placement uses nearest-magnet distance
# instead; keep this aligned with walkable-surface checks only.
NAVMESH_TOLERANCE_CM = 50.0

# Legacy entrances (`nav_waypoint_entrance_<idx>`) have no island token
# and belong to Scandinavium, the first stadium we shipped. Future
# islands encode their name in the entrance prim name:
# `nav_waypoint_entrance_artmuseum_01`, etc.
DEFAULT_ISLAND = "scandinavium"
ENTRANCE_PREFIX = "nav_waypoint_entrance_"

# Per-segment speed multipliers applied to ComposedRoute.segment_speeds.
# 1.0 is the auto-mover's base speed (~3 m/s). OSM segments cover much
# longer city distances at a brisker pace so the user does not wait
# minutes to walk a few hundred meters — clicking along the OSM
# overlay should feel snappy (~24 m/s ≈ 86 km/h, "city flyover"
# pacing). Indoor NavMesh legs stay at 1.0 so inside-the-arena pacing
# matches the rest of the app.
OSM_SEGMENT_SPEED = 12.0
NAVMESH_SEGMENT_SPEED = 1.0

# Shortcut segments (entrance → exit) are not walked: the
# ``shortcut_traversal_service`` intercepts the ``"shortcut"`` path-class
# transition, fades, teleports the player to the exit, and resumes.
# We still emit a tiny non-zero speed so that — in the unlikely event
# the traversal service is unavailable — the auto-mover doesn't deadlock
# on a zero-speed segment; instead it crawls (~30 cm/s) and the user
# can cancel the route.
SHORTCUT_SEGMENT_SPEED = 0.1

# Walk-speed assumption for estimated_time_seconds. 1.3 m/s matches
# route_measure.constants.DEFAULT_WALK_SPEED_M_PER_S.
DEFAULT_WALK_SPEED_M_PER_S = 1.3


# ────────────────────────────────────────────────────────────────────
# Composed route data classes
# ────────────────────────────────────────────────────────────────────


@dataclass
class ComposedLeg:
    """One segment of a composed route.

    Attributes:
        kind: ``"navmesh"``, ``"osm"`` or ``"shortcut"``.
        island: For navmesh legs, the island name this leg walks on
            (e.g. ``"scandinavium"``). ``None`` for OSM / shortcut legs.
        points: World-space polyline vertices, at least 2 points.
            Shortcut legs always have exactly 2 points (entrance, exit)
            — the auto-mover never walks them; the
            ``shortcut_traversal_service`` intercepts the path-class
            transition into ``"shortcut"`` and runs a fade+teleport.
        edge_classes: For OSM legs, the class string of each edge in
            the leg (``len == len(points) - 1``). NavMesh legs leave this
            empty — the finalizer fills their slots with ``"navmesh"``.
            Shortcut legs leave this empty too (finalizer fills with
            ``"shortcut"``).
        shortcut_meta: Optional metadata for shortcut legs:
            ``group_id`` / ``type`` / ``from_prim_path`` /
            ``to_prim_path`` / ``traversal_seconds``. Used by the
            traversal service to look up the destination Xform and
            time the fade transition. Empty / ignored for non-shortcut
            legs.
    """

    kind: str
    island: Optional[str]
    points: List[Vec3]
    edge_classes: List[str] = field(default_factory=list)
    shortcut_meta: Optional[dict] = None


@dataclass
class ComposedRoute:
    """A composed walkable route: ordered legs + derived convenience fields.

    The flat ``polyline`` stitches all legs together (shared boundary
    points de-duplicated) and is the input to the PointClickAutoMover.
    ``segment_speeds`` has length ``len(polyline) - 1``.
    ``segment_classes`` has the same length and tags each segment with
    its path class (``"navmesh"`` / ``"pedestrian"`` / ``"residential"``
    / ``"arterial"`` / ``"highway"`` / ``"steps"`` / ``"bridge"``).
    """

    legs: List[ComposedLeg]
    polyline: List[Vec3] = field(default_factory=list)
    segment_speeds: List[float] = field(default_factory=list)
    segment_classes: List[str] = field(default_factory=list)
    start_island: Optional[str] = None
    end_island: Optional[str] = None

    # ----- convenience -----

    @property
    def has_osm(self) -> bool:
        return any(leg.kind == "osm" for leg in self.legs)

    @property
    def has_navmesh(self) -> bool:
        return any(leg.kind == "navmesh" for leg in self.legs)

    @property
    def has_shortcut(self) -> bool:
        return any(leg.kind == "shortcut" for leg in self.legs)

    @property
    def navmesh_points(self) -> List[Vec3]:
        """All NavMesh leg points concatenated (for a single overlay polyline).

        For cross-island routes this produces a single continuous
        polyline that the overlay will render as one line — currently
        acceptable because the only production deployment is single-
        island (Scandinavium). Once a second navmesh lands, the
        projector can start accepting a list of legs here instead.
        """
        out: List[Vec3] = []
        for leg in self.legs:
            if leg.kind == "navmesh":
                out.extend(leg.points)
        return out

    @property
    def osm_points(self) -> List[Vec3]:
        """All OSM leg points concatenated."""
        out: List[Vec3] = []
        for leg in self.legs:
            if leg.kind == "osm":
                out.extend(leg.points)
        return out

    @property
    def distance_cm(self) -> float:
        total = 0.0
        for i in range(1, len(self.polyline)):
            a = self.polyline[i - 1]
            b = self.polyline[i]
            dx = a[0] - b[0]
            dz = a[2] - b[2]
            total += (dx * dx + dz * dz) ** 0.5
        return total

    @property
    def distance_meters(self) -> float:
        return self.distance_cm / 100.0

    @property
    def estimated_time_seconds(self) -> float:
        """Time to walk the whole polyline, honouring ``segment_speeds``.

        Base speed is ``DEFAULT_WALK_SPEED_M_PER_S``; each segment
        scales by its multiplier (OSM = 5×, NavMesh = 1×).
        """
        total = 0.0
        base_cm_s = DEFAULT_WALK_SPEED_M_PER_S * 100.0
        for i in range(1, len(self.polyline)):
            a = self.polyline[i - 1]
            b = self.polyline[i]
            dx = a[0] - b[0]
            dz = a[2] - b[2]
            length = (dx * dx + dz * dz) ** 0.5
            mult = (
                self.segment_speeds[i - 1]
                if (i - 1) < len(self.segment_speeds)
                else 1.0
            )
            speed = base_cm_s * max(0.001, mult)
            total += length / speed
        return total


__all__ = [
    "Vec3",
    "NAVMESH_TOLERANCE_CM",
    "DEFAULT_ISLAND",
    "ENTRANCE_PREFIX",
    "OSM_SEGMENT_SPEED",
    "NAVMESH_SEGMENT_SPEED",
    "SHORTCUT_SEGMENT_SPEED",
    "DEFAULT_WALK_SPEED_M_PER_S",
    "ComposedLeg",
    "ComposedRoute",
]
