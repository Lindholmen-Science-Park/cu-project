"""
Live transit journey positions as USD vehicles.

**Default: Västtrafik Travel Planner v4** — ``GET /positions`` with a bbox around
``TRANSIT_LIVE_CENTER_*`` using OAuth2 client credentials
(``VASTTRAFIK_CLIENT_ID`` / ``VASTTRAFIK_CLIENT_SECRET``). Suitable for Göteborg /
Skandinavium. See https://developer.vasttrafik.se/

Requires GeoCoordinateService (CesiumGeoreference on stage).

**Vertical placement:** When ``TRANSIT_LIVE_VEHICLE_Y_FROM_OSM`` is on (default), **Y** comes from
the nearest **OSM graph** node (same ``gothenburg_graph.json`` terrain-baked heights as the road
curves) plus ``TRANSIT_LIVE_VEHICLE_OSM_Y_OFFSET_CM`` — aligned with tile ground without PhysX.
If the graph is missing or no node is found, fall back to ellipsoid height +
``TRANSIT_LIVE_VEHICLE_POST_Y_LIFT_CM`` / ``TRANSIT_LIVE_VEHICLE_CLEARANCE_CM`` and optional
``TRANSIT_LIVE_SNAP_TO_GROUND`` (PhysX + NavMesh; off by default when tiles lack colliders).

**Motion:** Between polls, vehicles **ease** along a polyline from the last pose to the new API
position (``TRANSIT_LIVE_MOVE_BLEND_SEC`` / ``TRANSIT_LIVE_MOVE_BLEND_MAX_JUMP_CM``). When
``TRANSIT_LIVE_OSM_ROUTE_BETWEEN_UPDATES`` is on (default), the polyline follows the **OSM road
graph** (``gothenburg_graph.json`` via ``OsmGraphService``, ``car`` mode by default) so vehicles
do not cut straight through blocks between sparse GPS ticks. Falls back to a straight segment if
routing fails.

Yaw uses bearing from the feed when present; otherwise it is inferred from successive (x, z)
samples, blended toward the target yaw near the end of the tween.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

_ROOT = "/World/TransitLiveOverlay"
_DEFAULT_CENTER = (57.69924, 11.98767)  # Skandinavium anchor (see cesium-geolocation topic)
# Tight default: stadium + inner city only — widen with ``TRANSIT_LIVE_RADIUS_KM`` if needed.
_DEFAULT_RADIUS_KM_VASTTRAFIK = 3.2
_VASTTRAFIK_TOKEN_URL = "https://ext-api.vasttrafik.se/token"
_VASTTRAFIK_PLANERA_BASE_DEFAULT = "https://ext-api.vasttrafik.se/pr/v4"

# Vehicle dimensions in cm (Omniverse 1 unit = 1 cm).
# Layout: scale = (width X, height Y, length Z); +Z is local forward at yaw 0
# (matches ``_bearing_to_yaw_deg`` and the polyline yaw convention used in
# ``_tick_vehicle_blends`` — yaw = atan2(dx, dz)).
# Authored as a non-uniform scale on a unit cube under each vehicle prim.
_BUS_SCALE_CM = (250.0, 300.0, 1000.0)   # 2.5 m wide × 3 m tall × 10 m long
_TRAM_SCALE_CM = (265.0, 335.0, 3300.0)  # 2.65 m wide × 3.35 m tall × 33 m long
_BUS_COLOR = (0.2, 0.45, 1.0)            # blue
_TRAM_COLOR = (0.15, 0.85, 0.35)         # green

# Optional 3D models that replace the cube body. Resolved relative to the stage
# root layer directory unless the corresponding ``TRANSIT_LIVE_*_USD_PATH`` env
# is set to an absolute path. Setting the env to ``0`` / ``off`` / ``cube``
# forces cube fallback for that vehicle kind.
_BUS_MODEL_RELATIVE_PATH = "Assets/Bus/bus_edited.usd"
_TRAM_MODEL_RELATIVE_PATH = "Assets/Tram/tram.usd"
# ``bus_edited.usd``'s local +X is forward; our overlay yaw convention is
# +Z forward (yaw = atan2(dx, dz), see ``_bearing_to_yaw_deg`` and the layout
# comment above). Apply this rotateY on the body Xform so the bus nose points
# along the polyline tangent at slot yaw=0 without baking anything into the
# asset on disk.
_BUS_MODEL_YAW_BIAS_DEG = -90.0
# ``Assets/Tram/tram.usd`` is authored lengthwise on local +Z, so no yaw bias.
_TRAM_MODEL_YAW_BIAS_DEG = 0.0
# Tram asset compensation (from measured world bbox of tram.usd:
# ~3852 x 6395 x 22380 cm) to target ~265 x 335 x 3300 cm.
# Applied on the tram body Xform only (bus stays asset-authored scale).
_TRAM_MODEL_SCALE_COMP = (0.068785699, 0.052383697, 0.147449638)

# Göteborg Spårvagn lines (1–13, no 12). Used as the default for
# ``TRANSIT_LIVE_TRAM_ROUTE_IDS`` — explicit empty env (``=``) opts out, an
# explicit list overrides. Transport-mode-based classification (when the feed
# carries it) still wins over this list.
_DEFAULT_TRAM_ROUTE_IDS_GOTHENBURG = frozenset(
    {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "13"}
)
# Substrings searched (case-insensitive) in any ``line.transportMode`` /
# ``line.productCategory`` style hint Västtrafik returns on ``/positions``
# rows. Covers English + Swedish + GTFS-style spellings.
_TRAM_TRANSPORT_MODE_HINTS = (
    "tram",
    "spårvagn",
    "sparvagn",
    "light_rail",
    "lightrail",
    "streetcar",
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _lerp_xyz(
    a: Tuple[float, float, float], b: Tuple[float, float, float], u: float
) -> Tuple[float, float, float]:
    return (
        a[0] + (b[0] - a[0]) * u,
        a[1] + (b[1] - a[1]) * u,
        a[2] + (b[2] - a[2]) * u,
    )


def _lerp_yaw_deg(y0: float, y1: float, u: float) -> float:
    d = ((float(y1) - float(y0) + 540.0) % 360.0) - 180.0
    return float(y0) + d * float(u)


def _polyline_cumulative_len(poly: List[Tuple[float, float, float]]) -> List[float]:
    cum: List[float] = [0.0]
    for i in range(1, len(poly)):
        ax, ay, az = poly[i - 1]
        bx, by, bz = poly[i]
        dx, dy, dz = bx - ax, by - ay, bz - az
        cum.append(cum[-1] + math.sqrt(dx * dx + dy * dy + dz * dz))
    return cum


def _segment_at_alpha(
    cum: List[float], alpha: float, hint_idx: int = 0
) -> Tuple[int, float]:
    """Locate ``alpha`` (in [0,1] of arc length) on cumulative-length array.

    Returns ``(segment_idx, t_in_segment)``. ``hint_idx`` is the previously
    returned segment idx for the same polyline; because blend ``alpha`` is
    monotonically non-decreasing within a single tween, this turns the search
    into amortised O(1) (was O(N) per call from index 0 every frame).
    """
    n = len(cum) - 1
    if n <= 0:
        return 0, 0.0
    total = cum[-1]
    if total < 1e-6:
        return n - 1, 1.0
    a = 0.0 if alpha < 0.0 else (1.0 if alpha > 1.0 else float(alpha))
    target = a * total
    i = hint_idx
    if i < 0:
        i = 0
    elif i > n - 1:
        i = n - 1
    # Forward scan: blend alpha grows over the lifetime of a tween.
    while i < n - 1 and cum[i + 1] < target:
        i += 1
    # Defensive rewind in case alpha went backwards (shouldn't normally happen).
    while i > 0 and cum[i] > target:
        i -= 1
    seg = cum[i + 1] - cum[i]
    if seg < 1e-9:
        return i, 0.0
    t = (target - cum[i]) / seg
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return i, t


def _sanitize_token(raw: str, max_len: int = 48) -> str:
    """Build a USD-safe, stable token with collision resistance.

    Older logic truncated/normalized directly, so two distinct feed ids could
    collapse to the same token (e.g. long ids sharing a prefix, or ids that
    differ only by punctuation). That made separate vehicles reuse one slot and
    appear to "swap direction"/teleport as updates alternated.
    """
    src = str(raw or "v")
    stem = re.sub(r"[^a-zA-Z0-9_]", "_", src) or "v"
    # Stable short hash of the *full* raw id to avoid collisions after
    # normalization/truncation while keeping token length bounded.
    h = hashlib.blake2s(src.encode("utf-8"), digest_size=4).hexdigest()
    stem_max = max(1, max_len - 1 - len(h))
    return f"{stem[:stem_max]}_{h}"


def _vasttrafik_env_creds_ok() -> bool:
    return bool(
        os.environ.get("VASTTRAFIK_CLIENT_ID", "").strip()
        and os.environ.get("VASTTRAFIK_CLIENT_SECRET", "").strip()
    )


def _vasttrafik_api_error_detail(http_code: int, err_txt: str) -> str:
    """Turn Västtrafik fault JSON into a short message (often subscription-related)."""
    t = (err_txt or "").strip()
    if http_code == 403 and "900908" in t:
        return (
            "HTTP 403 fault 900908: your OAuth app is not allowed to call this API. "
            "In developer.vasttrafik.se open your **Application** and use **Prenumerera på API / "
            "Subscribe** to add **Travel Planner v4**, then request a new token (restart Kit)."
        )
    if http_code == 403 and "Resource forbidden" in t:
        return (
            "HTTP 403 Resource forbidden — confirm the app is subscribed to **Travel Planner v4** "
            "(same place you created client id/secret)."
        )
    one = t.replace("\n", " ")[:220]
    return f"HTTP {http_code} {one}" if one else f"HTTP {http_code}"


def _bbox_from_center_radius_km(clat: float, clon: float, radius_km: float) -> tuple[float, float, float, float]:
    """South-west corner, then north-east (degrees WGS84) for Västtrafik /positions."""
    dlat = radius_km / 111.0
    cos_lat = max(0.25, abs(math.cos(math.radians(clat))))
    dlon = radius_km / (111.0 * cos_lat)
    ll_lat = clat - dlat
    ll_lon = clon - dlon
    ur_lat = clat + dlat
    ur_lon = clon + dlon
    return (ll_lat, ll_lon, ur_lat, ur_lon)


class TransitOverlayService:
    """Background fetch + main-thread USD updates."""

    def __init__(self, on_status: Optional[Callable[[Dict[str, Any]], None]] = None):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="transit_rt")
        self._poll_task: Optional[asyncio.Future] = None
        self._enabled = False
        self._source = "vasttrafik"
        self._vt_access_token: str = ""
        self._vt_token_expires_at: float = 0.0
        self._interval_s = float(os.environ.get("TRANSIT_LIVE_POLL_SEC", "20"))
        self._max_vehicles = int(os.environ.get("TRANSIT_LIVE_MAX_VEHICLES", "72"))
        clat = float(os.environ.get("TRANSIT_LIVE_CENTER_LAT", str(_DEFAULT_CENTER[0])))
        clon = float(os.environ.get("TRANSIT_LIVE_CENTER_LON", str(_DEFAULT_CENTER[1])))
        self._center_latlon = (clat, clon)
        self._radius_km = self._radius_km_from_env_unset_default()
        print(
            "[transit_live] Västtrafik Planera Resa v4 — "
            f"VASTTRAFIK_CLIENT={'set' if _vasttrafik_env_creds_ok() else 'unset'}"
        )
        base = os.environ.get("VASTTRAFIK_PLANERA_BASE", _VASTTRAFIK_PLANERA_BASE_DEFAULT).rstrip("/")
        print(f"[transit_live] Planera Resa base: {base}")
        print(
            f"[transit_live] geo filter: center_latlon=({self._center_latlon[0]:.5f}, "
            f"{self._center_latlon[1]:.5f}) radius_km={self._radius_km}"
        )
        # Tram-route allow-list (used only when the feed row has *no*
        # transport-mode hint — see ``_classify_is_tram_from``). Env unset →
        # default to Göteborg's Spårvagn lines so the overlay paints trams
        # green out of the box. Explicit empty env (``TRANSIT_LIVE_TRAM_ROUTE_IDS=``)
        # disables the route-id heuristic entirely; mode-based detection still runs.
        raw_tram = os.environ.get("TRANSIT_LIVE_TRAM_ROUTE_IDS")
        if raw_tram is None:
            self._tram_route_ids: Set[str] = set(_DEFAULT_TRAM_ROUTE_IDS_GOTHENBURG)
        else:
            self._tram_route_ids = {x.strip() for x in raw_tram.split(",") if x.strip()}
        self._known_prim_paths: Dict[str, str] = {}
        # XformOp handle cache: vid -> {"translate_op", "rotate_op", "scale_op"}.
        # Avoids re-resolving GetPrimAtPath / Xformable / GetOrderedXformOps per
        # vehicle per frame (the per-frame writer was the dominant USD cost).
        self._vehicle_handles: Dict[str, Dict[str, Any]] = {}
        self._last_error: Optional[str] = None
        self._last_vehicle_count = 0
        self._last_fetch_ms: int = 0
        self._on_status = on_status
        self._warned_radius_empty = False
        # Smooth motion between polls (GLOBAL_EVENT_UPDATE)
        self._update_sub: Optional[Any] = None
        self._blend: Dict[str, Dict[str, Any]] = {}
        self._prev_target_xz: Dict[str, Tuple[float, float]] = {}
        self._last_yaw: Dict[str, float] = {}
        self._osm_graph: Optional[Any] = None
        self._osm_graph_load_failed = False
        # Spatial hash for OSM nodes, **per routing mode** (car vs tram, etc. —
        # each mode has a different valid-node set in ``OsmGraphService``).
        self._osm_spatial_by_mode: Dict[str, Dict[Tuple[int, int], List[Tuple[str, float, float, float]]]] = {}
        self._osm_spatial_key_by_mode: Dict[str, str] = {}
        self._osm_grid_cell_cm: float = 30_000.0
        self._last_vehicle_dev_list: List[Dict[str, Any]] = []
        # EMA of observed wall-clock interval between successive successful
        # _apply_vehicles() calls (monotonic seconds). Drives the per-tween
        # ``dur`` so blends end roughly when the next snapshot lands —
        # eliminating the synchronised "freeze gap" between polls.
        self._last_apply_monotonic: Optional[float] = None
        self._cadence_ema_s: Optional[float] = None
        # Per-vehicle low-pass-filtered yaw (degrees). Smooths the
        # stair-step yaw at OSM-node boundaries without hiding real turns.
        # First-order exponential filter with time constant
        # ``TRANSIT_LIVE_YAW_SMOOTH_TAU_S`` (default 0.15 s; 0 disables).
        self._smoothed_yaw: Dict[str, float] = {}
        self._last_tick_monotonic: Optional[float] = None
        # Prim pool: hide-don't-destroy when a vehicle leaves the feed, then
        # reuse the prim for the next new vehicle. Avoids USD composition
        # invalidation + Hydra resync churn from constant create/destroy.
        # Slot paths use a synthetic ``v_NNNNN`` name decoupled from feed IDs
        # so any pooled prim can host any vehicle.
        self._free_slots: List[str] = []
        self._slot_counter: int = 0

    def _dev_vehicle_list_max(self) -> int:
        raw = os.environ.get("TRANSIT_LIVE_DEV_VEHICLE_LIST_MAX", "").strip()
        if raw:
            return max(1, min(200, int(raw)))
        return 64

    def _classify_is_tram_from(self, mode_hint: str, route_id: str) -> bool:
        """Decide whether a Västtrafik row is a tram.

        Priority:

        1. **Transport-mode hint from the feed** (``line.transportMode`` /
           ``line.productCategory`` / ``line.mode``, any case). If present,
           we trust it absolutely — match against ``_TRAM_TRANSPORT_MODE_HINTS``
           returns ``True``, anything else (bus, ferry, train, …) returns
           ``False``. The feed is more authoritative than our static list.
        2. **Route-id allow-list fallback** (``self._tram_route_ids``).
           Used only when the feed gave us no mode at all (older v4 payloads
           sometimes omit it). Defaults to Göteborg's Spårvagn lines 1–13;
           overridable via ``TRANSIT_LIVE_TRAM_ROUTE_IDS``.
        """
        m = (mode_hint or "").strip().lower()
        if m:
            return any(kw in m for kw in _TRAM_TRANSPORT_MODE_HINTS)
        rid = (route_id or "").strip()
        return bool(rid) and rid in self._tram_route_ids

    def _vasttrafik_dev_extras(self, raw: Dict[str, Any], route_id: str, journey_name: str) -> Dict[str, Any]:
        """Small JSON-safe strings/numbers for dev UI (subset of /positions row)."""
        out: Dict[str, Any] = {
            "line": (route_id or "")[:64],
            "journeyName": str(journey_name or "")[:120],
        }
        dir_ = raw.get("direction") if raw.get("direction") is not None else raw.get("Direction")
        if dir_ is not None and str(dir_).strip():
            out["direction"] = str(dir_).strip()[:80]
        st = raw.get("state") if raw.get("state") is not None else raw.get("State")
        if st is not None and str(st).strip():
            out["state"] = str(st).strip()[:48]
        delay = raw.get("delay") if raw.get("delay") is not None else raw.get("Delay")
        if delay is not None:
            try:
                out["delayMinutes"] = float(delay)
            except (TypeError, ValueError):
                pass
        return out

    def _refresh_perf_settings_from_env(self) -> None:
        """Re-read poll / cap from env so .env edits apply without restarting Kit."""
        try:
            self._interval_s = float(os.environ.get("TRANSIT_LIVE_POLL_SEC", "20"))
        except (TypeError, ValueError):
            self._interval_s = 20.0
        try:
            self._max_vehicles = int(os.environ.get("TRANSIT_LIVE_MAX_VEHICLES", "72"))
        except (TypeError, ValueError):
            self._max_vehicles = 72
        self._max_vehicles = max(1, min(200, self._max_vehicles))

    def _invalidate_osm_spatial_index(self) -> None:
        self._osm_spatial_by_mode = {}
        self._osm_spatial_key_by_mode = {}

    def _scene_focus_radius_sq_cm(self) -> Optional[float]:
        """Drop vehicles whose scene (x,z) is farther than this from the stadium anchor — ``None`` = off."""
        raw = (os.environ.get("TRANSIT_LIVE_SCENE_RADIUS_CM") or "").strip()
        if raw and raw.lower() in ("0", "off", "none", "false"):
            return None
        if raw:
            try:
                r = float(raw)
                return (r * r) if r > 0 else None
            except (TypeError, ValueError):
                return None
        # ~2.6 km horizontal radius around ``TRANSIT_LIVE_CENTER_*`` (scene cm).
        return 260_000.0**2

    def _radius_km_from_env_unset_default(self) -> float:
        raw = os.environ.get("TRANSIT_LIVE_RADIUS_KM")
        if raw is not None and str(raw).strip() != "":
            return float(raw)
        return _DEFAULT_RADIUS_KM_VASTTRAFIK

    def _radius_km_from_env_refresh(self) -> float:
        raw = os.environ.get("TRANSIT_LIVE_RADIUS_KM")
        if raw is not None and str(raw).strip() != "":
            return float(raw)
        return _DEFAULT_RADIUS_KM_VASTTRAFIK

    def _refresh_geo_filter_from_env(self) -> None:
        self._radius_km = self._radius_km_from_env_refresh()
        clat = float(os.environ.get("TRANSIT_LIVE_CENTER_LAT", str(_DEFAULT_CENTER[0])))
        clon = float(os.environ.get("TRANSIT_LIVE_CENTER_LON", str(_DEFAULT_CENTER[1])))
        self._center_latlon = (clat, clon)

    def _emit_status(self):
        if self._on_status:
            try:
                self._on_status(self.status_payload())
            except Exception:
                pass

    def shutdown(self):
        self.set_enabled(False)
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self._executor.shutdown(wait=False)

    def set_enabled(self, enabled: bool, api_key_override: Optional[str] = None) -> str:
        """Start/stop polling. Returns human-readable status for logging."""
        self._source = "vasttrafik"
        _ = api_key_override  # legacy web payload field; Västtrafik uses env OAuth only

        self._enabled = bool(enabled)
        if self._enabled:
            if not _vasttrafik_env_creds_ok():
                self._enabled = False
                self._emit_status()
                return "missing_vasttrafik_credentials"

        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            self._poll_task = None

        if not self._enabled:
            self._clear_stage_vehicles()
            self._emit_status()
            return "disabled"

        try:
            import omni.kit.app as kit_app

            self._ensure_update_sub()
            self._poll_task = asyncio.ensure_future(
                self._poll_loop(kit_app.get_app())
            )
        except Exception as e:
            self._last_error = str(e)
            self._emit_status()
            return f"start_error:{e}"
        self._emit_status()
        return "enabled"

    def _ensure_update_sub(self) -> None:
        if self._update_sub is not None:
            return
        try:
            import carb.eventdispatcher
            import omni.kit.app

            ed = carb.eventdispatcher.get_eventdispatcher()
            self._update_sub = ed.observe_event(
                observer_name="younite.open_data_live_extension/update_blend",
                event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
                on_event=self._on_update_frame,
                order=0,
            )
        except Exception as e:
            print(f"[transit_live] blend update subscription failed: {e}")
            self._update_sub = None

    def _stop_update_sub(self) -> None:
        self._update_sub = None
        self._blend.clear()

    def _on_update_frame(self, _event=None) -> None:
        if not self._enabled or not self._blend:
            return
        try:
            self._tick_vehicle_blends()
        except Exception:
            pass

    def _blend_duration_s(self) -> float:
        """Choose tween length so blends end roughly when the next snapshot
        lands. Order of preference:

        1. ``TRANSIT_LIVE_MOVE_BLEND_SEC`` env override (manual tuning).
        2. Observed cadence EMA × 0.98 (true network/poll interval).
        3. Configured ``TRANSIT_LIVE_POLL_SEC`` × 0.92 (cold-start fallback,
           used only before the first inter-poll sample is recorded).
        """
        raw = os.environ.get("TRANSIT_LIVE_MOVE_BLEND_SEC", "").strip()
        if raw:
            return max(0.12, float(raw))
        if self._cadence_ema_s is not None:
            return max(0.5, min(30.0, float(self._cadence_ema_s) * 0.98))
        return max(3.0, min(14.0, float(self._interval_s) * 0.92))

    def _yaw_smooth_tau_s(self) -> float:
        """Time constant (seconds) for the per-frame yaw low-pass filter.
        ``0`` (or unparseable) → smoothing disabled (raw yaw is written)."""
        raw = (os.environ.get("TRANSIT_LIVE_YAW_SMOOTH_TAU_S") or "").strip()
        if not raw:
            return 0.15
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return 0.15
        return max(0.0, min(2.0, v))

    def _blend_max_jump_cm(self) -> float:
        raw = os.environ.get("TRANSIT_LIVE_MOVE_BLEND_MAX_JUMP_CM", "").strip()
        if raw:
            return max(0.0, float(raw))
        return 250_000.0

    def _transit_osm_routing_enabled(self) -> bool:
        raw = (os.environ.get("TRANSIT_LIVE_OSM_ROUTE_BETWEEN_UPDATES") or "1").strip().lower()
        return raw not in ("0", "false", "no", "off")

    def _transit_osm_route_mode(self) -> str:
        m = (os.environ.get("TRANSIT_LIVE_OSM_ROUTE_MODE") or "car").strip().lower()
        if m not in ("walking", "wheelchair", "car", "tram", "train"):
            return "car"
        return m

    def _transit_osm_route_mode_for_vehicle(self, is_tram: bool) -> str:
        """Buses/road vehicles use ``TRANSIT_LIVE_OSM_ROUTE_MODE`` (default
        ``car``). Trams use ``TRANSIT_LIVE_OSM_ROUTE_MODE_TRAM`` (default
        ``tram``) so Dijkstra runs on ``railway=tram`` / ``light_rail`` edges
        in ``gothenburg_graph.json`` when that graph includes rail.
        """
        if not is_tram:
            return self._transit_osm_route_mode()
        raw = (os.environ.get("TRANSIT_LIVE_OSM_ROUTE_MODE_TRAM") or "tram").strip().lower()
        if raw in ("walking", "wheelchair", "car", "tram", "train"):
            return raw
        return "tram"

    def _osm_route_max_per_poll(self) -> int:
        raw = os.environ.get("TRANSIT_LIVE_OSM_ROUTE_MAX_PER_POLL", "").strip()
        if raw:
            return max(0, int(raw))
        return 24

    def _osm_main_component_only(self) -> bool:
        raw = (os.environ.get("TRANSIT_LIVE_OSM_MAIN_COMPONENT_ONLY") or "1").strip().lower()
        return raw not in ("0", "false", "no", "off")

    def _ensure_osm_graph(self) -> bool:
        if self._osm_graph is not None and bool(getattr(self._osm_graph, "is_loaded", False)):
            return True
        if self._osm_graph_load_failed:
            return False
        try:
            from younite.osm_navigation_extension.osm_graph_service import OsmGraphService

            g = OsmGraphService()
            gp = os.environ.get("TRANSIT_LIVE_OSM_GRAPH_PATH", "").strip()
            if not g.load(gp or None):
                self._osm_graph_load_failed = True
                self._invalidate_osm_spatial_index()
                print(
                    "[transit_live] OSM graph not found or invalid — "
                    "using straight blends (see gothenburg_graph.json / TRANSIT_LIVE_OSM_GRAPH_PATH)."
                )
                return False
            self._osm_graph = g
            self._invalidate_osm_spatial_index()
            self._build_osm_spatial_index()
            print("[transit_live] OSM graph loaded for road-following blends (+ spatial index)")
            return True
        except Exception as e:
            self._osm_graph_load_failed = True
            self._invalidate_osm_spatial_index()
            print(f"[transit_live] OSM graph unavailable ({e}) — straight blends")
            return False

    def _build_osm_spatial_index(self, mode: Optional[str] = None) -> None:
        """Bucket OSM nodes for O(1)-ish nearest lookup (full scan was dominating poll time).

        *mode* defaults to ``TRANSIT_LIVE_OSM_ROUTE_MODE`` (buses). Tram routing
        passes ``mode="tram"`` so we hash **tram-graph** nodes, not car-only.
        """
        if not self._osm_graph or not getattr(self._osm_graph, "is_loaded", False):
            return
        if mode is None:
            mode = self._transit_osm_route_mode()
        g = self._osm_graph
        valid = getattr(g, "_valid_nodes_by_mode", {}).get(mode) or set()
        nodes: Dict[str, Any] = getattr(g, "_nodes", {}) or {}
        try:
            cell = float(os.environ.get("TRANSIT_LIVE_OSM_GRID_CELL_CM", "").strip() or "30000")
        except (TypeError, ValueError):
            cell = 30_000.0
        self._osm_grid_cell_cm = max(8000.0, min(cell, 120_000.0))
        main_comp: Optional[int] = None
        comps: Optional[Dict[str, int]] = None
        if self._osm_main_component_only():
            try:
                main_comp = g.main_component_id(mode)
            except Exception:
                main_comp = None
            if main_comp is not None:
                comps = getattr(g, "_components_by_mode", {}).get(mode)
        key = f"{mode}|{main_comp}|{self._osm_grid_cell_cm}"
        if self._osm_spatial_key_by_mode.get(mode) == key and mode in self._osm_spatial_by_mode:
            return
        if not valid or not nodes:
            self._osm_spatial_by_mode[mode] = {}
            self._osm_spatial_key_by_mode[mode] = key
            return
        bins: Dict[Tuple[int, int], List[Tuple[str, float, float, float]]] = {}
        for nid in valid:
            if comps is not None and main_comp is not None:
                if comps.get(nid) != main_comp:
                    continue
            c = nodes.get(nid)
            if not c or len(c) < 3:
                continue
            gx, gy, gz = float(c[0]), float(c[1]), float(c[2])
            ix = int(gx // self._osm_grid_cell_cm)
            iz = int(gz // self._osm_grid_cell_cm)
            bins.setdefault((ix, iz), []).append((str(nid), gx, gy, gz))
        self._osm_spatial_by_mode[mode] = bins
        self._osm_spatial_key_by_mode[mode] = key

    def _osm_nearest_node_id_fast(
        self,
        graph: Any,
        gx: float,
        gz: float,
        mode: str,
        main_comp: Optional[int],
    ) -> Optional[str]:
        want = f"{mode}|{main_comp}|{self._osm_grid_cell_cm}"
        if self._osm_spatial_key_by_mode.get(mode) != want:
            self._build_osm_spatial_index(mode)
        bins = self._osm_spatial_by_mode.get(mode) or {}
        if not bins:
            if main_comp is not None:
                return graph.nearest_node(gx, gz, mode=mode, component=main_comp)
            return graph.nearest_node(gx, gz, mode=mode)
        cell = self._osm_grid_cell_cm
        ix, iz = int(gx // cell), int(gz // cell)
        best_id: Optional[str] = None
        best_d2 = float("inf")
        for dix in (-1, 0, 1):
            for diz in (-1, 0, 1):
                for row in bins.get((ix + dix, iz + diz), ()):
                    nid, nx, _ny, nz = row
                    dd = (nx - gx) ** 2 + (nz - gz) ** 2
                    if dd < best_d2:
                        best_d2 = dd
                        best_id = nid
        if best_id is None:
            if main_comp is not None:
                return graph.nearest_node(gx, gz, mode=mode, component=main_comp)
            return graph.nearest_node(gx, gz, mode=mode)
        # If the 3×3 neighbourhood is still far, fall back to exact scan (rare at cell edges).
        if best_d2 > (2.2 * cell) ** 2:
            if main_comp is not None:
                return graph.nearest_node(gx, gz, mode=mode, component=main_comp)
            return graph.nearest_node(gx, gz, mode=mode)
        return best_id

    def _get_osm_roads_offset(self, stage) -> Tuple[float, float, float]:
        """Match ``younite.osm_navigation_extension`` — graph nodes are under ``/World/OSM_Roads`` space."""
        try:
            from pxr import UsdGeom

            prim = stage.GetPrimAtPath("/World/OSM_Roads")
            if not prim or not prim.IsValid():
                return (0.0, 0.0, 0.0)
            xform = UsdGeom.Xformable(prim)
            for op in xform.GetOrderedXformOps():
                if op.GetOpName() == "xformOp:translate":
                    t = op.Get()
                    return (float(t[0]), float(t[1]), float(t[2]))
        except Exception:
            pass
        return (0.0, 0.0, 0.0)

    def _transit_osm_y_from_road_enabled(self) -> bool:
        raw = (os.environ.get("TRANSIT_LIVE_VEHICLE_Y_FROM_OSM") or "1").strip().lower()
        return raw not in ("0", "false", "no", "off")

    def _osm_y_offset_cm(self) -> float:
        raw = os.environ.get("TRANSIT_LIVE_VEHICLE_OSM_Y_OFFSET_CM", "").strip()
        if raw:
            return float(raw)
        return 90.0

    def _osm_terrain_y_at_world(self, stage, wx: float, wz: float) -> Optional[float]:
        """World-space Y on the road surface from the terrain-baked OSM graph (nearest car node)."""
        if not self._ensure_osm_graph() or self._osm_graph is None:
            return None
        graph = self._osm_graph
        ox, oy, oz = self._get_osm_roads_offset(stage)
        gx = float(wx) - ox
        gz = float(wz) - oz
        mode = self._transit_osm_route_mode()
        main_comp: Optional[int] = None
        if self._osm_main_component_only():
            try:
                main_comp = graph.main_component_id(mode)
            except Exception:
                main_comp = None
        try:
            nid = self._osm_nearest_node_id_fast(graph, gx, gz, mode, main_comp)
            if not nid:
                return None
            nc = graph.node_coords(nid)
            if not nc:
                return None
            return float(nc[1]) + oy
        except Exception:
            return None

    def _try_build_osm_polyline_world(
        self,
        graph: Any,
        ox: float,
        oz: float,
        mode: str,
        p0: Tuple[float, float, float],
        p1: Tuple[float, float, float],
        main_comp: Optional[int],
    ) -> Optional[Tuple[List[Tuple[float, float, float]], List[float]]]:
        """Return (polyline_world_xyz, cumulative_lengths) or None."""
        x0, y0, z0 = p0
        x1, y1, z1 = p1
        gx0, gz0 = x0 - ox, z0 - oz
        gx1, gz1 = x1 - ox, z1 - oz
        n0 = self._osm_nearest_node_id_fast(graph, gx0, gz0, mode, main_comp)
        n1 = self._osm_nearest_node_id_fast(graph, gx1, gz1, mode, main_comp)
        if not n0 or not n1:
            return None
        path, _ = graph.shortest_path(n0, n1, mode=mode)
        if len(path) < 2:
            return None
        coords = graph.path_to_coords(path)
        if len(coords) < 2:
            return None
        shifted = [(float(x) + ox, float(y), float(z) + oz) for x, y, z in coords]
        poly: List[Tuple[float, float, float]] = [p0]
        if shifted:
            s0x, s0y, s0z = shifted[0]
            if (s0x - x0) ** 2 + (s0z - z0) ** 2 > 400.0:
                poly.append((s0x, s0y, s0z))
            for sx, sy, sz in shifted[1:]:
                poly.append((sx, sy, sz))
        if poly:
            lx, ly, lz = poly[-1]
            if (lx - x1) ** 2 + (lz - z1) ** 2 > 400.0:
                poly.append((x1, y1, z1))
        dedup: List[Tuple[float, float, float]] = [poly[0]]
        for pt in poly[1:]:
            px, py, pz = pt
            qx, qy, qz = dedup[-1]
            if (px - qx) ** 2 + (py - qy) ** 2 + (pz - qz) ** 2 > 25.0:
                dedup.append(pt)
        if len(dedup) < 2:
            return None
        return (dedup, _polyline_cumulative_len(dedup))

    def _subdivide_straight_with_osm_y(
        self,
        stage,
        p0: Tuple[float, float, float],
        p1: Tuple[float, float, float],
    ) -> Optional[Tuple[List[Tuple[float, float, float]], List[float]]]:
        """Insert N intermediate samples on the straight ``p0→p1`` line and
        snap each to the OSM-terrain Y. Used as a cheap "follow the hill"
        fallback when full pathfinding isn't done (graph budget exhausted,
        routing failed, or routing disabled but graph still loaded).

        Returns ``None`` if the OSM graph isn't available or the segment is
        too short to bother subdividing — caller keeps the original 2-point
        polyline in that case.
        """
        if not self._ensure_osm_graph():
            return None
        x0, y0, z0 = p0
        x1, y1, z1 = p1
        dx = x1 - x0
        dz = z1 - z0
        horiz_sq = dx * dx + dz * dz
        # Don't bother below ~40 m horizontal travel — straight lerp of Y
        # over that distance is visually fine even on slopes.
        if horiz_sq < 4000.0 * 4000.0:
            return None
        horiz = math.sqrt(horiz_sq)
        # ~one sample per 20 m of travel, capped at 8 segments to bound cost.
        n_steps = int(min(8, max(2, horiz / 2000.0)))
        out: List[Tuple[float, float, float]] = [(x0, y0, z0)]
        offset = self._osm_y_offset_cm()
        for k in range(1, n_steps):
            t = k / float(n_steps)
            ix = x0 + t * dx
            iz = z0 + t * dz
            iy = self._osm_terrain_y_at_world(stage, ix, iz)
            if iy is None:
                # Graph said "no node here" — fall back to lerp for this point.
                iy = y0 + t * (y1 - y0)
            else:
                iy = iy + offset
            out.append((ix, iy, iz))
        out.append((x1, y1, z1))
        return out, _polyline_cumulative_len(out)

    def _clear_stage_vehicles(self):
        self._stop_update_sub()
        self._prev_target_xz.clear()
        self._last_yaw.clear()
        try:
            import omni.usd
            from younite.payload_orchestrator_core_extension import hide

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            root = stage.GetPrimAtPath(_ROOT)
            if root and root.IsValid():
                for child in root.GetChildren():
                    try:
                        p = str(child.GetPath())
                        stage.RemovePrim(p)
                    except Exception:
                        pass
            hide(_ROOT, source="transit_live_overlay")
        except Exception:
            pass
        self._known_prim_paths.clear()
        self._vehicle_handles.clear()
        self._smoothed_yaw.clear()
        # Pool is invalidated since the destroy loop above wiped every prim
        # under _ROOT. _slot_counter intentionally keeps growing — paths
        # stay unique even if a stale reference somewhere points at an old
        # ``v_00042`` name.
        self._free_slots.clear()
        self._last_tick_monotonic = None
        self._last_vehicle_count = 0
        self._last_vehicle_dev_list = []
        self._last_apply_monotonic = None
        self._cadence_ema_s = None

    def _credentials_ok(self) -> bool:
        return _vasttrafik_env_creds_ok()

    def _status_hint(self) -> Optional[str]:
        if self._credentials_ok():
            return None
        return (
            "Add VASTTRAFIK_CLIENT_ID and VASTTRAFIK_CLIENT_SECRET, and subscribe the OAuth "
            "application to **Travel Planner v4** on developer.vasttrafik.se (otherwise /positions returns 403)."
        )

    def _ensure_vasttrafik_token_blocking(self, force: bool = False) -> str:
        now = time.time()
        if (
            not force
            and self._vt_access_token
            and now < self._vt_token_expires_at
        ):
            return self._vt_access_token
        cid = os.environ.get("VASTTRAFIK_CLIENT_ID", "").strip()
        sec = os.environ.get("VASTTRAFIK_CLIENT_SECRET", "").strip()
        if not cid or not sec:
            raise RuntimeError("missing_vasttrafik_credentials")
        basic = base64.b64encode(f"{cid}:{sec}".encode("utf-8")).decode("ascii")
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
        req = urllib.request.Request(
            _VASTTRAFIK_TOKEN_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic}",
                "Accept": "application/json",
            },
        )
        print("[transit_live] Västtrafik OAuth token request …")
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        tok = str(payload.get("access_token") or "").strip()
        if not tok:
            raise RuntimeError("vasttrafik_token_empty")
        exp_in = int(payload.get("expires_in") or 3600)
        self._vt_access_token = tok
        self._vt_token_expires_at = now + max(120.0, float(exp_in) - 90.0)
        print(f"[transit_live] Västtrafik token OK (expires_in≈{exp_in}s)")
        return tok

    def _vj_latlon(self, obj: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
        lat = obj.get("latitude", obj.get("Latitude"))
        lon = obj.get("longitude", obj.get("Longitude"))
        try:
            if lat is None or lon is None:
                return None, None
            return float(lat), float(lon)
        except (TypeError, ValueError):
            return None, None

    def _vehicles_from_vasttrafik_rows(self, rows: List[Any]) -> List[Dict[str, Any]]:
        self._refresh_geo_filter_from_env()
        clat, clon = self._center_latlon
        scored: List[Tuple[float, str, str, Dict[str, Any]]] = []
        for i, raw in enumerate(rows):
            if not isinstance(raw, dict):
                continue
            lat, lon = self._vj_latlon(raw)
            if lat is None or lon is None:
                continue
            dist_km = _haversine_km(clat, clon, lat, lon)
            if dist_km > self._radius_km:
                continue
            ref = raw.get("detailsReference") or raw.get("DetailsReference")
            name = raw.get("name") or raw.get("Name") or ""
            vid = str(ref or name or f"row{i}")[:96]
            sk = _sanitize_token(vid)
            line = raw.get("line") or raw.get("Line")
            route_id = ""
            mode_hint = ""
            if isinstance(line, dict):
                route_id = str(
                    line.get("designation")
                    or line.get("Designation")
                    or line.get("name")
                    or line.get("Name")
                    or ""
                )
                # Västtrafik /positions has shipped these key spellings across
                # versions; the first non-empty value wins.
                for key in (
                    "transportMode",
                    "TransportMode",
                    "productCategory",
                    "ProductCategory",
                    "mode",
                    "Mode",
                ):
                    v = line.get(key)
                    if v:
                        mode_hint = str(v).strip()
                        if mode_hint:
                            break
            is_tram = self._classify_is_tram_from(mode_hint, route_id)
            dev_extras = self._vasttrafik_dev_extras(raw, route_id, str(name))
            if mode_hint:
                # Surface the raw mode hint in the dev panel so it's obvious
                # whether classification came from the feed or our route-id list.
                dev_extras["transportMode"] = mode_hint[:48]
            scored.append(
                (
                    dist_km,
                    sk,
                    vid,
                    {
                        "id": vid,
                        "lat": lat,
                        "lon": lon,
                        "bearing": None,
                        "route_id": route_id,
                        "is_tram": is_tram,
                        "dev": dev_extras,
                    },
                )
            )
        scored.sort(key=lambda t: t[0])
        by_id: Dict[str, Dict[str, Any]] = {}
        for _dist_km, sk, _vid, payload in scored:
            if sk in by_id:
                continue
            by_id[sk] = payload
            if len(by_id) >= self._max_vehicles:
                break
        out = list(by_id.values())
        if not out and len(rows) > 5 and not self._warned_radius_empty:
            self._warned_radius_empty = True
            print(
                f"[transit_live] Västtrafik returned {len(rows)} rows but none within "
                f"radius_km={self._radius_km} of center — try increasing TRANSIT_LIVE_RADIUS_KM."
            )
        if out:
            self._warned_radius_empty = False
        return out

    def _vasttrafik_positions_bbox_half_extent_km(self) -> float:
        """BBox for ``/positions`` query — cap so ``limit=200`` is dense near the scene anchor."""
        raw = os.environ.get("TRANSIT_LIVE_VASTTRAFIK_BBOX_RADIUS_KM", "").strip()
        if raw:
            return max(0.5, float(raw))
        return max(0.5, min(float(self._radius_km), 2.5))

    def _fetch_parse_vasttrafik_blocking(self) -> List[Dict[str, Any]]:
        self._refresh_geo_filter_from_env()
        token = self._ensure_vasttrafik_token_blocking()
        planera = os.environ.get("VASTTRAFIK_PLANERA_BASE", _VASTTRAFIK_PLANERA_BASE_DEFAULT).rstrip(
            "/"
        )
        bbox_km = self._vasttrafik_positions_bbox_half_extent_km()
        ll_lat, ll_lon, ur_lat, ur_lon = _bbox_from_center_radius_km(
            self._center_latlon[0], self._center_latlon[1], bbox_km
        )
        print(
            f"[transit_live] Västtrafik /positions bbox half-extent_km={bbox_km:.2f} "
            f"(filter radius_km={self._radius_km:.2f})"
        )
        lim = min(200, max(1, self._max_vehicles))
        q = urllib.parse.urlencode(
            {
                "lowerLeftLat": f"{ll_lat:.6f}",
                "lowerLeftLong": f"{ll_lon:.6f}",
                "upperRightLat": f"{ur_lat:.6f}",
                "upperRightLong": f"{ur_lon:.6f}",
                "limit": str(lim),
            }
        )
        url = f"{planera}/positions?{q}"
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "GoteverseTransitLiveOverlay/0.1",
        }

        def _get_json(retry_on_401: bool) -> Any:
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    return json.loads(resp.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as e:
                if e.code == 401 and retry_on_401:
                    return None
                try:
                    err_txt = e.read().decode("utf-8", errors="replace")[:800]
                except Exception:
                    err_txt = ""
                detail = _vasttrafik_api_error_detail(int(e.code), err_txt)
                print(f"[transit_live] Västtrafik /positions failed: {detail}")
                if int(e.code) == 403 and "900908" in err_txt:
                    raise RuntimeError(
                        "vasttrafik_403_not_subscribed (subscribe app to Travel Planner v4 on developer.vasttrafik.se)"
                    ) from e
                raise RuntimeError(f"vasttrafik_{detail}") from e

        data = _get_json(True)
        if data is None:
            token = self._ensure_vasttrafik_token_blocking(force=True)
            headers["Authorization"] = f"Bearer {token}"
            data = _get_json(False)
        rows = data
        if isinstance(data, dict):
            for key in ("results", "positions", "data", "value", "journeys"):
                v = data.get(key)
                if isinstance(v, list):
                    rows = v
                    break
            else:
                rows = []
        if not isinstance(rows, list):
            rows = []
        print(f"[transit_live] Västtrafik /positions → {len(rows)} journey rows (limit={lim})")
        return self._vehicles_from_vasttrafik_rows(rows)

    def _bearing_to_yaw_deg(self, bearing_deg: float) -> float:
        """GTFS bearing: degrees clockwise from north. Scene: +X east, +Z south, north = -Z."""
        rad = math.radians(bearing_deg)
        fx = math.sin(rad)
        fz = -math.cos(rad)
        return math.degrees(math.atan2(fx, fz))

    def _resolve_handles_from_prim(self, prim) -> Optional[Dict[str, Any]]:
        """Resolve translate / rotate / scale XformOps from an existing vehicle prim.

        Also probes ``<prim>/body`` to determine ``body_kind``:

        * ``"cube"`` — primitive ``UsdGeom.Cube`` body; pool reuse rewrites the
          slot-level scale op + the cube's ``displayColor`` so the same cube
          can host buses or trams interchangeably.
        * ``"model"`` — referenced bus asset under an Xform body; pool reuse
          must skip both writes (the model carries its own meter-scaled meshes
          and authored materials).
        """
        from pxr import UsdGeom

        try:
            xf = UsdGeom.Xformable(prim)
            ops = xf.GetOrderedXformOps()
        except Exception:
            return None
        if len(ops) < 2:
            return None
        body_kind = "cube"
        try:
            body = prim.GetStage().GetPrimAtPath(prim.GetPath().AppendChild("body"))
            if body and body.IsValid() and body.GetTypeName() != "Cube":
                body_kind = "model"
        except Exception:
            pass
        return {
            "translate_op": ops[0],
            "rotate_op": ops[1],
            "scale_op": ops[2] if len(ops) >= 3 else None,
            "body_kind": body_kind,
        }

    def _ensure_handles(
        self, stage, vid: str, prim_path: str
    ) -> Optional[Dict[str, Any]]:
        """Return cached XformOp handles, resolving from the prim on first hit."""
        h = self._vehicle_handles.get(vid)
        if h is not None:
            return h
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return None
        h = self._resolve_handles_from_prim(prim)
        if h is not None:
            self._vehicle_handles[vid] = h
        return h

    def _read_pose_from_handles(
        self, handles: Dict[str, Any]
    ) -> Optional[Tuple[float, float, float, float]]:
        try:
            tr = handles["translate_op"].Get()
            if tr is None:
                return None
            x, y, z = float(tr[0]), float(tr[1]), float(tr[2])
            rv = handles["rotate_op"].Get()
            yaw = float(rv) if rv is not None else 0.0
            return (x, y, z, yaw)
        except Exception:
            return None

    def _write_pose(
        self,
        handles: Dict[str, Any],
        xyz: Tuple[float, float, float],
        yaw: float,
    ) -> None:
        """Per-frame hot path: only translate + rotate. Scale and color are
        authored once at spawn, never per frame."""
        from pxr import Gf

        handles["translate_op"].Set(Gf.Vec3d(*xyz))
        handles["rotate_op"].Set(yaw)

    def _resolve_model_asset_path(
        self, stage, env_var_name: str, default_relative_path: str
    ) -> Optional[str]:
        """Resolve a vehicle model USD path (env override → stage-relative).

        Order of resolution:

        1. ``env_var_name`` env. Empty / unset → step 2.
           Values ``0`` / ``off`` / ``false`` / ``none`` / ``cube`` → ``None``
           (forces cube fallback).
           Absolute paths used as-is; relative paths joined to the stage root
           layer dir (and one level up).
        2. ``default_relative_path`` joined against the stage root layer dir
           and one level up — same resolution scheme as the maintenance-bot
           extension (``MODEL_RELATIVE_PATH``), so a checked-in stage in
           ``source/data`` finds checked-in assets automatically.

        Never returns an absolute path embedded in the source tree — the
        resolved string is whatever ``os.path.join`` produces from the live
        stage, satisfying ``project-base.mdc``'s "no absolute paths" rule.
        """
        raw = (os.environ.get(env_var_name) or "").strip()
        if raw.lower() in {"0", "off", "false", "none", "cube"}:
            return None
        candidates: List[str] = []
        scene_dir: Optional[str] = None
        try:
            real = stage.GetRootLayer().realPath
            if real:
                scene_dir = os.path.dirname(real)
        except Exception:
            scene_dir = None
        if raw:
            if os.path.isabs(raw):
                candidates.append(raw)
            elif scene_dir:
                candidates.append(os.path.normpath(os.path.join(scene_dir, raw)))
                candidates.append(os.path.normpath(os.path.join(scene_dir, "..", raw)))
        if scene_dir:
            candidates.append(
                os.path.normpath(os.path.join(scene_dir, default_relative_path))
            )
            candidates.append(
                os.path.normpath(os.path.join(scene_dir, "..", default_relative_path))
            )
        for c in candidates:
            try:
                if os.path.isfile(c):
                    return c
            except Exception:
                continue
        return None

    def _resolve_bus_asset_path(self, stage) -> Optional[str]:
        """Resolve bus model USD path from env override or default location."""
        return self._resolve_model_asset_path(
            stage=stage,
            env_var_name="TRANSIT_LIVE_BUS_USD_PATH",
            default_relative_path=_BUS_MODEL_RELATIVE_PATH,
        )

    def _resolve_tram_asset_path(self, stage) -> Optional[str]:
        """Resolve tram model USD path from env override or default location."""
        return self._resolve_model_asset_path(
            stage=stage,
            env_var_name="TRANSIT_LIVE_TRAM_USD_PATH",
            default_relative_path=_TRAM_MODEL_RELATIVE_PATH,
        )

    def _acquire_slot_for_new_vehicle(
        self,
        stage,
        vid: str,
        xyz: Tuple[float, float, float],
        yaw: float,
        scale_cm: Tuple[float, float, float],
        color: Tuple[float, float, float],
        is_tram: bool = False,
    ) -> str:
        """Hand a brand-new ``vid`` either a pooled-and-hidden prim or a
        freshly created one. Records handles + path in the service maps and
        returns the slot path. The vehicle is positioned at ``xyz`` with the
        given pose / scale / colour and made visible.

        Pooled reuse path is preferred — it avoids USD prim creation +
        Hydra prim sync, which dominate the cost of high-churn feeds where
        vehicles enter/leave the bbox every few polls.
        """
        from pxr import Gf, UsdGeom
        from younite.payload_orchestrator_core_extension import show

        while self._free_slots:
            slot_path = self._free_slots.pop()
            handles = self._ensure_handles(stage, vid, slot_path)
            if handles is None:
                # Underlying prim went missing (e.g. external edit / stage
                # mutation). Drop and try the next pooled slot.
                continue
            # Cube slots: rewrite the slot-level scale + cube displayColor so
            # the same prim can host any size / colour. Model slots: skip
            # both — the asset carries its own meter-scaled geometry and
            # authored materials, and we never want to squash it.
            if handles.get("body_kind") != "model":
                try:
                    handles["scale_op"].Set(Gf.Vec3f(*scale_cm))
                except Exception:
                    pass
                cube_prim = stage.GetPrimAtPath(f"{slot_path}/body")
                if cube_prim and cube_prim.IsValid():
                    try:
                        UsdGeom.Cube(cube_prim).GetDisplayColorAttr().Set(
                            [Gf.Vec3f(*color)]
                        )
                    except Exception:
                        pass
            self._write_pose(handles, xyz, yaw)
            try:
                show(slot_path, source="transit_live_overlay")
            except Exception:
                pass
            self._vehicle_handles[vid] = handles
            self._known_prim_paths[vid] = slot_path
            return slot_path

        # No reusable slot — allocate a fresh one. Counter monotonically
        # grows so we never collide with an in-use or already-deleted name.
        self._slot_counter += 1
        slot_path = f"{_ROOT}/v_{self._slot_counter:05d}"
        handles = self._create_vehicle_prim(
            stage, slot_path, xyz, yaw, scale_cm, color, is_tram=is_tram
        )
        self._vehicle_handles[vid] = handles
        self._known_prim_paths[vid] = slot_path
        return slot_path

    def _create_vehicle_prim(
        self,
        stage,
        prim_path: str,
        xyz: Tuple[float, float, float],
        yaw: float,
        scale_cm: Tuple[float, float, float],
        color: Tuple[float, float, float],
        is_tram: bool = False,
    ) -> Dict[str, Any]:
        """Idempotent spawn / rebuild for a single vehicle. Returns the
        XformOp handles cached by the per-frame writer.

        Op order on the slot Xform is ``translate · rotateY · scale``,
        evaluated right-to-left (scale → rotate → translate in local space).
        Two body shapes are supported, chosen at spawn time:

        * **Model body** (when the bus/tram asset path resolves):
          asset): ``<prim>/body`` is an ``Xform`` with ``rotateY =
          ``*_MODEL_YAW_BIAS_DEG`` and a reference to the model USD's
          ``defaultPrim``. Slot-level scale stays at ``(1,1,1)`` (model-scale
          compensation, if needed, is authored on the body Xform). The body
          Xform's rotateY is *constant* — yaw animation still happens on the
          slot's ``rotate_op``.
        * **Cube body** (fallback when no asset is available): unit
          ``UsdGeom.Cube`` driven by the slot's non-uniform scale op so each
          axis is in cm directly (1 unit = 1 cm), with ``displayColor`` for
          the bus / tram tint.
        """
        from pxr import Gf, Sdf, UsdGeom

        x, y, z = xyz
        sx, sy, sz = scale_cm
        xform = UsdGeom.Xform.Define(stage, prim_path)
        xf = UsdGeom.Xformable(xform)
        xf.ClearXformOpOrder()
        translate_op = xf.AddTranslateOp(precision=UsdGeom.XformOp.PrecisionDouble)
        rotate_op = xf.AddRotateYOp(precision=UsdGeom.XformOp.PrecisionDouble)
        scale_op = xf.AddScaleOp(precision=UsdGeom.XformOp.PrecisionFloat)
        translate_op.Set(Gf.Vec3d(x, y, z))
        rotate_op.Set(yaw)

        asset_path = (
            self._resolve_tram_asset_path(stage)
            if is_tram
            else self._resolve_bus_asset_path(stage)
        )
        model_yaw_bias = _TRAM_MODEL_YAW_BIAS_DEG if is_tram else _BUS_MODEL_YAW_BIAS_DEG
        model_kind = "tram" if is_tram else "bus"
        body_path = f"{prim_path}/body"

        if asset_path:
            scale_op.Set(Gf.Vec3f(1.0, 1.0, 1.0))
            body_xform = UsdGeom.Xform.Define(stage, body_path)
            body_xf = UsdGeom.Xformable(body_xform)
            body_xf.ClearXformOpOrder()
            body_xf.AddRotateYOp(precision=UsdGeom.XformOp.PrecisionDouble).Set(
                model_yaw_bias
            )
            if is_tram:
                body_xf.AddScaleOp(precision=UsdGeom.XformOp.PrecisionFloat).Set(
                    Gf.Vec3f(*_TRAM_MODEL_SCALE_COMP)
                )
            try:
                body_xform.GetPrim().GetReferences().AddReference(
                    Sdf.Reference(assetPath=asset_path)
                )
            except Exception as exc:
                # If the reference fails to compose for any reason, fall back
                # to the cube so the slot still renders something.
                print(
                    f"[transit_live] {model_kind} asset reference failed ({exc!r}); "
                    "falling back to cube body."
                )
                stage.RemovePrim(body_path)
                asset_path = None

        if not asset_path:
            scale_op.Set(Gf.Vec3f(sx, sy, sz))
            cube = UsdGeom.Cube.Define(stage, body_path)
            cube.CreateSizeAttr(1.0)
            cube.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])

        return {
            "translate_op": translate_op,
            "rotate_op": rotate_op,
            "scale_op": scale_op,
            "body_kind": "model" if asset_path else "cube",
        }

    def _tick_vehicle_blends(self) -> None:
        if not self._blend:
            return
        from pxr import Gf, Sdf
        import omni.usd

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return
        now = time.monotonic()
        # Frame-rate-independent yaw low-pass: alpha = 1 - exp(-dt / tau).
        # Computed once per frame (not per vehicle) so 70 buses share the
        # work. dt is wall-clock between successive _on_update_frame calls.
        last_tick = self._last_tick_monotonic
        self._last_tick_monotonic = now
        tau = self._yaw_smooth_tau_s()
        if tau > 0.0 and last_tick is not None:
            dt = now - last_tick
            if dt <= 0.0 or dt > 0.5:
                # Long pause (paused tab, hitch) — snap rather than slewing
                # over many frames at once.
                yaw_alpha = 1.0
            else:
                yaw_alpha = 1.0 - math.exp(-dt / tau)
        else:
            yaw_alpha = 1.0  # smoothing off (or first frame) → write raw yaw
        # Build the per-frame pose set first, then flush all attribute writes
        # inside a single Sdf.ChangeBlock so Hydra observes one batched update
        # rather than 2*N individual notifications.
        pose_writes: List[Tuple[Dict[str, Any], Tuple[float, float, float], float]] = []
        finished: List[str] = []

        for vid, b in self._blend.items():
            prim_path = self._known_prim_paths.get(vid)
            if not prim_path:
                finished.append(vid)
                continue
            handles = self._ensure_handles(stage, vid, prim_path)
            if handles is None:
                finished.append(vid)
                continue
            poly = b.get("poly")
            cum = b.get("cum")
            y0 = float(b["y0"])
            y1 = float(b["y1"])
            t0 = float(b["t0"])
            dur = max(1e-6, float(b["dur"]))
            u = (now - t0) / dur
            # Linear easing on the arc-length parameter so velocity is
            # constant within a tween. Smoothstep used to ease-out at u=1
            # and ease-in at u=0 of the next blend → vehicles decelerated
            # to a halt at every poll boundary (the visible "pulse" between
            # cycles). With linear sm, the EMA-driven ``dur`` keeps the next
            # blend starting just as the current one finishes, so motion is
            # effectively continuous. The yaw start/end transitions below
            # (sm < 0.06 / sm > 0.9) still operate on the first/last 6% of
            # the tween, which now corresponds to the first/last 6% of time
            # rather than of the smoothstep curve.
            sm = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
            if isinstance(poly, list) and isinstance(cum, list) and len(poly) >= 2 and len(cum) >= 2:
                # Single segment lookup, reused for both position and yaw.
                hint = int(b.get("seg_idx", 0))
                seg_i, seg_t = _segment_at_alpha(cum, sm, hint)
                b["seg_idx"] = seg_i
                ax, ay, az = poly[seg_i]
                bx, by, bz = poly[seg_i + 1]
                xyz = (
                    ax + seg_t * (bx - ax),
                    ay + seg_t * (by - ay),
                    az + seg_t * (bz - az),
                )
                dxs = bx - ax
                dzs = bz - az
                # Same "ignore micro-segment yaw" guard as the old helper
                # (4 cm² in scene units), so jitter from near-coincident
                # OSM nodes doesn't spin the bus.
                if dxs * dxs + dzs * dzs < 4.0:
                    y_seg = y1
                else:
                    y_seg = math.degrees(math.atan2(dxs, dzs))
                if sm < 0.06:
                    yaw = _lerp_yaw_deg(y0, y_seg, sm / 0.06)
                elif sm < 0.9:
                    yaw = y_seg
                else:
                    mix = (sm - 0.9) / 0.1
                    yaw = _lerp_yaw_deg(y_seg, y1, mix)
            else:
                p0 = b.get("p0")
                p1 = b.get("p1")
                if (
                    isinstance(p0, tuple)
                    and isinstance(p1, tuple)
                    and len(p0) == 3
                    and len(p1) == 3
                ):
                    xyz = _lerp_xyz(p0, p1, sm)
                    yaw = _lerp_yaw_deg(y0, y1, sm)
                else:
                    finished.append(vid)
                    continue
            # Per-vehicle low-pass on yaw (shortest-arc lerp toward target).
            # ``yaw_alpha == 1.0`` short-circuits to write raw yaw — used when
            # smoothing is disabled, on the first frame, or after a hitch.
            if yaw_alpha < 1.0:
                prev_yaw = self._smoothed_yaw.get(vid)
                if prev_yaw is None:
                    smoothed = yaw
                else:
                    smoothed = _lerp_yaw_deg(prev_yaw, yaw, yaw_alpha)
                self._smoothed_yaw[vid] = smoothed
                yaw_to_write = smoothed
            else:
                self._smoothed_yaw[vid] = yaw
                yaw_to_write = yaw
            pose_writes.append((handles, xyz, yaw_to_write))
            if u >= 1.0:
                finished.append(vid)

        if pose_writes:
            with Sdf.ChangeBlock():
                for handles, xyz, yaw in pose_writes:
                    handles["translate_op"].Set(Gf.Vec3d(*xyz))
                    handles["rotate_op"].Set(yaw)

        for vid in finished:
            self._blend.pop(vid, None)
            # Note: ``_smoothed_yaw`` is intentionally retained — the next
            # blend on the same vehicle should start from its current
            # smoothed orientation, not snap. It's pruned in the per-poll
            # removal pass and on _clear_stage_vehicles.

    def _apply_vehicles(self, vehicles: List[Dict[str, Any]]):
        from pxr import UsdGeom
        import omni.usd
        from younite.usd_viewer_stage_core_extension import get_geo_coordinate_service
        from younite.usd_viewer_stage_core_extension.services.core_services.geo_teleport_transform import (
            snap_geo_scene_position_to_ground,
        )
        from younite.payload_orchestrator_core_extension import show

        stage = omni.usd.get_context().get_stage()
        if not stage:
            self._last_error = "no_stage"
            return
        geo = get_geo_coordinate_service()
        if not geo or not geo.ready:
            self._last_error = "geo_not_ready"
            return

        world = stage.GetPrimAtPath("/World")
        if not world or not world.IsValid():
            self._last_error = "no_world"
            return

        root = stage.GetPrimAtPath(_ROOT)
        if not root or not root.IsValid():
            UsdGeom.Xform.Define(stage, _ROOT)
        show(_ROOT, source="transit_live_overlay")

        self._refresh_perf_settings_from_env()

        # ``latlon_to_usd`` third arg is **WGS84 height (m)**, same as CesiumGeoreference origin — not
        # "meters above local ground". A constant like 4m is far below origin when h≈100m → prims under tiles.
        raw_abs_h = os.environ.get("TRANSIT_LIVE_VEHICLE_WGS84_HEIGHT_M", "").strip()
        if raw_abs_h:
            default_wgs84_h = float(raw_abs_h)
        else:
            oh = float(geo.origin[2])
            off = float(os.environ.get("TRANSIT_LIVE_VEHICLE_ALT_OFFSET_M", "12"))
            default_wgs84_h = oh + off

        snap_raw = (os.environ.get("TRANSIT_LIVE_SNAP_TO_GROUND") or "0").strip().lower()
        snap_to_ground = snap_raw not in ("0", "false", "no", "off")
        # Extra scene Y (cm) after lat/lon → USD; default when snap is off so cubes clear tiles
        # without PhysX hits. Same units as geo.latlon_to_usd (cm when metersPerUnit 0.01).
        _post_raw = os.environ.get("TRANSIT_LIVE_VEHICLE_POST_Y_LIFT_CM")
        if _post_raw is not None and str(_post_raw).strip() != "":
            post_y_lift_cm = float(str(_post_raw).strip())
        elif not snap_to_ground:
            post_y_lift_cm = 580.0
        else:
            post_y_lift_cm = 0.0

        _clr_raw = os.environ.get("TRANSIT_LIVE_VEHICLE_CLEARANCE_CM", "").strip()
        if _clr_raw:
            clearance_cm = float(_clr_raw)
        else:
            clearance_cm = 140.0 if not snap_to_ground else 50.0

        max_jump_sq = self._blend_max_jump_cm() ** 2
        near_sq = 90.0 * 90.0  # skip tween when movement < ~90 cm

        # Update cadence EMA from observed wall-clock spacing between
        # successful applies. Sanity-clamp to ignore the first call after
        # an enable / very long stall (e.g. paused tab, network outage).
        apply_now = time.monotonic()
        if self._last_apply_monotonic is not None:
            dt = apply_now - self._last_apply_monotonic
            if 1.0 <= dt <= 120.0:
                if self._cadence_ema_s is None:
                    self._cadence_ema_s = dt
                else:
                    # ~3-sample memory: respond quickly to interval changes
                    # (e.g. user editing TRANSIT_LIVE_POLL_SEC) without
                    # being noisy on jitter.
                    self._cadence_ema_s = 0.35 * dt + 0.65 * self._cadence_ema_s
        self._last_apply_monotonic = apply_now

        blend_dur = self._blend_duration_s()

        scene_r2 = self._scene_focus_radius_sq_cm()
        anchor_xyz: Optional[Tuple[float, float, float]] = None
        if scene_r2 is not None:
            ac = geo.latlon_to_usd(self._center_latlon[0], self._center_latlon[1], default_wgs84_h)
            if ac:
                anchor_xyz = (float(ac[0]), float(ac[1]), float(ac[2]))

        targets: Dict[str, Dict[str, Any]] = {}
        seen: Set[str] = set()
        for v in vehicles:
            vid = _sanitize_token(str(v["id"]))
            lat = float(v["lat"])
            lon = float(v["lon"])
            wgs84_h = default_wgs84_h
            wh = v.get("wgs84_height_m")
            if wh is not None:
                try:
                    wgs84_h = float(wh)
                except (TypeError, ValueError):
                    wgs84_h = default_wgs84_h
            coords = geo.latlon_to_usd(lat, lon, wgs84_h)
            if not coords:
                continue
            x, y, z = float(coords[0]), float(coords[1]), float(coords[2])
            used_osm_y = False
            if self._transit_osm_y_from_road_enabled():
                y_osm = self._osm_terrain_y_at_world(stage, x, z)
                if y_osm is not None:
                    y = y_osm + self._osm_y_offset_cm()
                    used_osm_y = True
            if not used_osm_y:
                y += post_y_lift_cm + clearance_cm
            if snap_to_ground and not used_osm_y:
                try:
                    x, y, z = snap_geo_scene_position_to_ground(x, y, z, quiet=True)
                except Exception:
                    pass
            if anchor_xyz is not None and scene_r2 is not None:
                ax, _ay, az = anchor_xyz
                dxs, dzs = x - ax, z - az
                if dxs * dxs + dzs * dzs > scene_r2:
                    continue
            # Slot path is resolved later via the pool — pooled prims have
            # synthetic ``v_NNNNN`` names decoupled from feed IDs.
            is_tram = bool(v.get("is_tram"))
            scale_cm = _TRAM_SCALE_CM if is_tram else _BUS_SCALE_CM
            color = _TRAM_COLOR if is_tram else _BUS_COLOR
            bearing = v.get("bearing")
            last_xz = self._prev_target_xz.get(vid)
            if bearing is not None:
                try:
                    yaw = self._bearing_to_yaw_deg(float(bearing))
                except (TypeError, ValueError):
                    yaw = self._last_yaw.get(vid, 0.0)
            elif last_xz is not None:
                lx, lz = last_xz
                dx, dz = x - lx, z - lz
                if dx * dx + dz * dz > 400.0:
                    yaw = math.degrees(math.atan2(dx, dz))
                else:
                    yaw = self._last_yaw.get(vid, 0.0)
            else:
                yaw = 0.0
            self._last_yaw[vid] = yaw
            self._prev_target_xz[vid] = (x, z)

            feed_meta: Dict[str, Any] = {
                "feedId": str(v["id"])[:96],
                "lat": lat,
                "lon": lon,
                "routeId": str(v.get("route_id") or ""),
                "bearing": v.get("bearing"),
                "isTram": bool(is_tram),
            }
            for k, val in (v.get("dev") or {}).items():
                if isinstance(val, (str, int, float, bool)) or val is None:
                    if k not in feed_meta:
                        feed_meta[k] = val

            targets[vid] = {
                "xyz": (x, y, z),
                "yaw": yaw,
                "scale_cm": scale_cm,
                "color": color,
                "is_tram": is_tram,
                "feedMeta": feed_meta,
            }
            seen.add(vid)

        # Pool-aware removal: hide prims via the orchestrator and push the
        # slot back to the free list. The next new vehicle reuses it instead
        # of paying USD prim-creation + Hydra prim-sync cost.
        from younite.payload_orchestrator_core_extension import hide as _hide

        to_remove = [k for k in self._known_prim_paths if k not in seen]
        for k in to_remove:
            self._blend.pop(k, None)
            self._prev_target_xz.pop(k, None)
            self._last_yaw.pop(k, None)
            self._smoothed_yaw.pop(k, None)
            self._vehicle_handles.pop(k, None)
            p = self._known_prim_paths.pop(k, None)
            if p:
                try:
                    _hide(p, source="transit_live_overlay")
                except Exception:
                    pass
                self._free_slots.append(p)

        t_now = time.monotonic()
        blend_queue: List[Tuple[str, Dict[str, Any], Tuple[float, float, float, float], float]] = []
        for vid, t in targets.items():
            tx, ty, tz = t["xyz"]
            yaw = float(t["yaw"])
            scale_cm = t["scale_cm"]
            color = t["color"]
            is_tram = bool(t.get("is_tram"))

            prim_path = self._known_prim_paths.get(vid)
            if prim_path is None:
                # Brand-new vehicle: claim a pooled prim if one exists,
                # otherwise allocate a fresh slot. Pose is snapped (no tween).
                self._acquire_slot_for_new_vehicle(
                    stage, vid, (tx, ty, tz), yaw, scale_cm, color, is_tram=is_tram
                )
                self._blend.pop(vid, None)
                continue

            xf_prim = stage.GetPrimAtPath(prim_path)
            if not xf_prim or not xf_prim.IsValid():
                # Slot's underlying prim disappeared (external edit) —
                # rebuild in place under the same path.
                handles = self._create_vehicle_prim(
                    stage, prim_path, (tx, ty, tz), yaw, scale_cm, color, is_tram=is_tram
                )
                self._vehicle_handles[vid] = handles
                self._blend.pop(vid, None)
                continue

            handles = self._ensure_handles(stage, vid, prim_path)
            if handles is None:
                handles = self._create_vehicle_prim(
                    stage, prim_path, (tx, ty, tz), yaw, scale_cm, color, is_tram=is_tram
                )
                self._vehicle_handles[vid] = handles
                self._blend.pop(vid, None)
                continue

            cur = self._read_pose_from_handles(handles)
            if cur is None:
                self._write_pose(handles, (tx, ty, tz), yaw)
                self._blend.pop(vid, None)
                continue

            cx, cy, cz, cyaw = cur
            dx = tx - cx
            dy = ty - cy
            dz = tz - cz
            dist_sq = dx * dx + dy * dy + dz * dz
            jump_sq = dx * dx + dz * dz
            # Either tiny correction (no point tweening) or huge teleport
            # (don't try to road-snap — just snap and reset blend).
            if dist_sq <= near_sq or jump_sq > max_jump_sq:
                self._write_pose(handles, (tx, ty, tz), yaw)
                self._blend.pop(vid, None)
                continue

            blend_queue.append((vid, t, (cx, cy, cz, cyaw), float(jump_sq)))

        graph: Optional[Any] = None
        if self._transit_osm_routing_enabled() and blend_queue and self._ensure_osm_graph():
            graph = self._osm_graph
        ox, oy, oz = (0.0, 0.0, 0.0)
        if graph is not None:
            ox, _oy, oz = self._get_osm_roads_offset(stage)
        budget = self._osm_route_max_per_poll() if graph is not None else 0
        use_main_comp = self._osm_main_component_only()
        blend_queue.sort(key=lambda row: -row[3])

        for vid, t, cur4, _jq in blend_queue:
            cx, cy, cz, cyaw = cur4
            tx, ty, tz = t["xyz"]
            yaw = float(t["yaw"])
            is_tram = bool(t.get("is_tram"))
            mode_veh = self._transit_osm_route_mode_for_vehicle(is_tram)
            main_comp: Optional[int] = None
            if graph is not None and use_main_comp:
                try:
                    main_comp = graph.main_component_id(mode_veh)
                except Exception:
                    main_comp = None
            p0w = (cx, cy, cz)
            p1w = (tx, ty, tz)
            poly: List[Tuple[float, float, float]] = [p0w, p1w]
            cum = _polyline_cumulative_len(poly)
            routed = False
            if graph is not None and budget > 0:
                alt = self._try_build_osm_polyline_world(
                    graph, ox, oz, mode_veh, p0w, p1w, main_comp
                )
                if alt:
                    poly, cum = alt
                    budget -= 1
                    routed = True
            # Fallback: routing not done (disabled, budget gone, or
            # pathfinding failed) — subdivide the straight line and pin Y
            # to OSM terrain. Still the escape hatch for trams when the
            # track graph is disconnected or the graph is road-only.
            if not routed:
                sub = self._subdivide_straight_with_osm_y(stage, p0w, p1w)
                if sub:
                    poly, cum = sub
            self._blend[vid] = {
                "poly": poly,
                "cum": cum,
                "y0": cyaw,
                "y1": yaw,
                "t0": t_now,
                "dur": blend_dur,
                # Cached segment index — advanced in-place by the per-frame
                # tick so polyline lookups are O(1) amortised.
                "seg_idx": 0,
            }
            # _known_prim_paths[vid] was set when the slot was acquired;
            # blending doesn't change which slot the vehicle occupies.

        lim_dev = self._dev_vehicle_list_max()
        dev_list: List[Dict[str, Any]] = []
        for vid in sorted(seen)[:lim_dev]:
            t = targets.get(vid)
            if not t:
                continue
            tx, ty, tz = t["xyz"]
            yaw = float(t["yaw"])
            row: Dict[str, Any] = {
                "token": vid,
                "sceneXyzCm": [round(tx, 1), round(ty, 1), round(tz, 1)],
                "yawDeg": round(yaw, 1),
            }
            fm = t.get("feedMeta")
            if isinstance(fm, dict):
                for k, val in fm.items():
                    if isinstance(val, (str, int, float, bool)) or val is None:
                        row[k] = val
            dev_list.append(row)
        self._last_vehicle_dev_list = dev_list

        self._last_vehicle_count = len(seen)
        self._last_error = None
        self._emit_status()

    async def _poll_loop(self, app):
        loop = asyncio.get_event_loop()
        while self._enabled:
            try:
                self._refresh_perf_settings_from_env()
                self._source = "vasttrafik"
                vehicles = await loop.run_in_executor(
                    self._executor, self._fetch_parse_vasttrafik_blocking
                )
                await app.next_update_async()
                self._apply_vehicles(vehicles)
                self._last_fetch_ms = int(time.time() * 1000)
            except asyncio.CancelledError:
                break
            except urllib.error.HTTPError as e:
                self._last_error = f"http_{e.code}"
                self._emit_status()
            except Exception as e:
                self._last_error = str(e)[:200]
                self._emit_status()
            try:
                await asyncio.sleep(max(5.0, self._interval_s))
            except asyncio.CancelledError:
                break

    def status_payload(self) -> Dict[str, Any]:
        hint = self._status_hint()
        return {
            "enabled": self._enabled,
            "vehicleCount": self._last_vehicle_count,
            "lastError": self._last_error,
            "lastFetchEpochMs": self._last_fetch_ms,
            "hasApiKey": self._credentials_ok(),
            "transitSource": self._source,
            "vehicles": list(self._last_vehicle_dev_list),
            **({"hint": hint} if hint else {}),
        }
