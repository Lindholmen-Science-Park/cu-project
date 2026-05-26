"""
Minimal Human Playback (Omniverse) - Extension module.
- Reads mqtt_messages.json (default) or data from API in future.
- Uses payload JSON with fields: id, timestamp (ms), x, y, active
- Groups by timestamp and updates all spheres for that frame
- Stable random color per id
- No USD timeline binding
"""

import json
from pathlib import Path
from collections import defaultdict, deque
from bisect import bisect_left
from typing import Optional, List, Any, Dict, Set, Tuple
from datetime import datetime

import omni.kit.app
import omni.usd
from pxr import UsdGeom, Gf, Usd

# -----------------------------
# CONFIG
# -----------------------------
ROOT_PATH_BASE = "/World/Humans"
SPHERE_RADIUS = 25.0

def get_sphere_root_path(camera_id: str) -> str:
    """Get the USD path for spheres root based on camera_id."""
    return f"{ROOT_PATH_BASE}/{camera_id}"

Y_HEIGHT = 50.0
FPS = 20.0
PLAY_EVERY_NTH_TIMESTAMP = 1
LERP_SPEED = 0.15

# Statistics constants
WINDOW_MS = 60_000  # 1 minute window
STALE_MS = 2_000    # Drop active ID if no updates for > 2 seconds
STATS_UPDATE_INTERVAL = 1.0  # Send stats to UI every 1 second
TRAFFIC_LOW_RATIO = 0.34
TRAFFIC_MED_RATIO = 0.67
OCCUPANCY_MATCH_TOLERANCE_MS = 250  # Match nearest occupancy snapshot within 250ms
TRAFFIC_LOW_COUNT = 6
TRAFFIC_MED_COUNT = 10
CAMERA_AREA_M2 = 10.0

# -----------------------------
# Helpers
# -----------------------------
def _stable_color_for_id(human_id: str):
    h = abs(hash(str(human_id)))
    r = ((h >>  0) & 255) / 255.0
    g = ((h >>  8) & 255) / 255.0
    b = ((h >> 16) & 255) / 255.0
    if max(r, g, b) < 0.35:
        r = min(1.0, r + 0.4)
        g = min(1.0, g + 0.4)
        b = min(1.0, b + 0.4)
    return (r, g, b)

def _ensure_xform_translate(prim):
    xform = UsdGeom.Xformable(prim)
    ops = xform.GetOrderedXformOps()
    for op in ops:
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            return op
    xform.ClearXformOpOrder()
    return xform.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)

def _set_visible(prim, visible: bool):
    from younite.payload_orchestrator_core_extension import show_hide, Priority
    if show_hide(prim.GetPath().pathString, visible, Priority.MEDIUM, source="camera_data_viz"):
        return
    img = UsdGeom.Imageable(prim)
    if visible:
        img.MakeVisible()
    else:
        vis = img.GetVisibilityAttr()
        if not vis:
            vis = img.CreateVisibilityAttr()
        vis.Set(UsdGeom.Tokens.invisible)

def _parse_message_ts_ms(msg: dict) -> Optional[int]:
    iso_ts = msg.get("timestamp", "")
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None

def _median_int(values: List[int]) -> Optional[int]:
    if not values:
        return None
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2 == 1:
        return int(sorted_vals[mid])
    return int((sorted_vals[mid - 1] + sorted_vals[mid]) // 2)

def _align_occupancy_timestamps(
    occupancy_by_timestamp: Dict[int, dict],
    occupancy_from_msg_ts: Set[int],
    tracker_offsets: List[int],
) -> Tuple[Dict[int, dict], int]:
    if not occupancy_from_msg_ts or not tracker_offsets:
        return occupancy_by_timestamp, 0
    offset_ms = _median_int(tracker_offsets)
    if not offset_ms:
        return occupancy_by_timestamp, 0
    aligned = {}
    for ts_ms, occ in occupancy_by_timestamp.items():
        if ts_ms in occupancy_from_msg_ts:
            aligned[ts_ms + offset_ms] = occ
        else:
            aligned[ts_ms] = occ
    return aligned, offset_ms

def _estimate_occupancy_tolerance_ms(occupancy_ts: List[int]) -> int:
    if not occupancy_ts or len(occupancy_ts) < 2:
        return OCCUPANCY_MATCH_TOLERANCE_MS
    deltas = sorted(occupancy_ts[i] - occupancy_ts[i - 1] for i in range(1, len(occupancy_ts)))
    median_delta = deltas[len(deltas) // 2]
    tolerance = max(OCCUPANCY_MATCH_TOLERANCE_MS, int(median_delta * 0.5))
    return min(tolerance, 2000)

def _create_or_get_sphere(stage, human_id: str, camera_id: str):
    sphere_root = get_sphere_root_path(camera_id)
    prim_path = f"{sphere_root}/Human_{human_id}"
    prim = stage.GetPrimAtPath(prim_path)
    if prim and prim.IsValid():
        return prim
    UsdGeom.Xform.Define(stage, sphere_root)
    sphere = UsdGeom.Sphere.Define(stage, prim_path)
    sphere.CreateRadiusAttr(SPHERE_RADIUS)
    prim = stage.GetPrimAtPath(prim_path)
    gprim = UsdGeom.Gprim(prim)
    color = _stable_color_for_id(human_id)
    gprim.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    _ensure_xform_translate(prim)
    return prim

def _payload_to_dict(payload):
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            return None
        try:
            return json.loads(payload)
        except Exception:
            return None
    return None

def load_tracker_rows(json_path: str) -> Tuple[List[dict], Dict[int, dict]]:
    """
    Load tracker rows and occupancy messages from JSON.
    Returns: (tracker_rows, occupancy_by_timestamp)
    """
    p = Path(json_path)
    print(f"[Playback] load_tracker_rows: reading {p}")
    with p.open("r", encoding="utf-8") as f:
        messages = json.load(f)
    print(f"[Playback] load_tracker_rows: file has {len(messages)} messages")
    rows = []
    occupancy_by_timestamp = {}
    occupancy_from_msg_ts = set()
    tracker_offsets = []
    
    for msg in messages:
        topic = msg.get("topic", "")
        payload_parsed = msg.get("payload_parsed", {})
        
        # Handle occupancy messages
        if "dataq/occupancy/" in topic:
            if "occupancy" in payload_parsed and isinstance(payload_parsed["occupancy"], dict):
                # Try to get timestamp from message or payload
                ts_ms = None
                if "timestamp" in payload_parsed:
                    try:
                        ts_ms = int(payload_parsed["timestamp"])
                    except:
                        pass
                if ts_ms is None:
                    # Parse ISO timestamp from message
                    ts_ms = _parse_message_ts_ms(msg)
                    if ts_ms is None:
                        continue
                if ts_ms:
                    occupancy_by_timestamp[ts_ms] = payload_parsed["occupancy"]
                    if "timestamp" not in payload_parsed:
                        occupancy_from_msg_ts.add(ts_ms)
            continue
        
        # Handle detection/tracker messages
        if "dataq/detections/" in topic or "dataq/tracker/" in topic:
            msg_ts_ms = _parse_message_ts_ms(msg)
            detection_list = payload_parsed.get("list", [])
            if not isinstance(detection_list, list):
                continue
            if msg_ts_ms is not None:
                for det in detection_list:
                    if isinstance(det, dict) and "timestamp" in det:
                        try:
                            tracker_offsets.append(int(det["timestamp"]) - msg_ts_ms)
                            break
                        except Exception:
                            pass
            for det in detection_list:
                if not isinstance(det, dict):
                    continue
                # Filter for valid human detections
                if (det.get("class") != "Human" or 
                    det.get("ignore", False) or 
                    "id" not in det or 
                    "timestamp" not in det or
                    "x" not in det or 
                    "y" not in det):
                    continue
                try:
                    ts = int(det["timestamp"])
                    rows.append({
                        "timestamp": ts,
                        "id": str(det["id"]),
                        "x": float(det.get("x", 0.0)),
                        "y": float(det.get("y", 0.0)),
                        "active": bool(det.get("active", True)),
                    })
                except Exception:
                    continue
    
    rows.sort(key=lambda r: r["timestamp"])
    occupancy_by_timestamp, offset_ms = _align_occupancy_timestamps(
        occupancy_by_timestamp,
        occupancy_from_msg_ts,
        tracker_offsets,
    )
    if offset_ms:
        print(f"[Playback] Aligned occupancy timestamps by offset {offset_ms} ms")
    print(f"[Playback] load_tracker_rows: extracted {len(rows)} tracker rows, {len(occupancy_by_timestamp)} occupancy messages")
    return rows, occupancy_by_timestamp

def load_tracker_rows_from_data(messages: List[Any]) -> Tuple[List[dict], Dict[int, dict]]:
    """Load tracker rows and occupancy from message list. Returns: (tracker_rows, occupancy_by_timestamp)"""
    rows = []
    occupancy_by_timestamp = {}
    occupancy_from_msg_ts = set()
    tracker_offsets = []
    
    for msg in messages:
        topic = msg.get("topic", "")
        payload_parsed = msg.get("payload_parsed", {})
        
        # Handle occupancy messages
        if "dataq/occupancy/" in topic:
            if "occupancy" in payload_parsed and isinstance(payload_parsed["occupancy"], dict):
                ts_ms = None
                if "timestamp" in payload_parsed:
                    try:
                        ts_ms = int(payload_parsed["timestamp"])
                    except:
                        pass
                if ts_ms is None:
                    ts_ms = _parse_message_ts_ms(msg)
                    if ts_ms is None:
                        continue
                if ts_ms:
                    occupancy_by_timestamp[ts_ms] = payload_parsed["occupancy"]
                    if "timestamp" not in payload_parsed:
                        occupancy_from_msg_ts.add(ts_ms)
            continue
        
        # Handle detection/tracker messages
        if "dataq/detections/" in topic or "dataq/tracker/" in topic:
            msg_ts_ms = _parse_message_ts_ms(msg)
            detection_list = payload_parsed.get("list", [])
            if isinstance(detection_list, list):
                if msg_ts_ms is not None:
                    for det in detection_list:
                        if isinstance(det, dict) and "timestamp" in det:
                            try:
                                tracker_offsets.append(int(det["timestamp"]) - msg_ts_ms)
                                break
                            except Exception:
                                pass
                for det in detection_list:
                    if (isinstance(det, dict) and
                        det.get("class") == "Human" and
                        not det.get("ignore", False) and
                        "id" in det and "timestamp" in det and "x" in det and "y" in det):
                        try:
                            ts = int(det["timestamp"])
                            rows.append({
                                "timestamp": ts,
                                "id": str(det["id"]),
                                "x": float(det.get("x", 0.0)),
                                "y": float(det.get("y", 0.0)),
                                "active": bool(det.get("active", True)),
                            })
                        except Exception:
                            continue
            elif isinstance(payload_parsed, dict) and msg_ts_ms is not None and "timestamp" in payload_parsed:
                try:
                    tracker_offsets.append(int(payload_parsed["timestamp"]) - msg_ts_ms)
                except Exception:
                    pass
    
    rows.sort(key=lambda r: r["timestamp"])
    occupancy_by_timestamp, offset_ms = _align_occupancy_timestamps(
        occupancy_by_timestamp,
        occupancy_from_msg_ts,
        tracker_offsets,
    )
    if offset_ms:
        print(f"[Playback] Aligned occupancy timestamps by offset {offset_ms} ms")
    return rows, occupancy_by_timestamp

def group_by_timestamp(rows):
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["timestamp"]].append(r)
    return sorted(grouped.keys()), grouped

# -----------------------------
# Statistics processing
# -----------------------------

def _process_occupancy_batch(t_ms: int, occupancy_data: dict):
    """Process occupancy snapshot for this timestamp."""
    if occupancy_data and isinstance(occupancy_data, dict):
        _state["stats"]["latest_occupancy"] = occupancy_data.copy()
        _state["stats"]["latest_occupancy_t_ms"] = t_ms

def _get_occupancy_snapshot_near(t_ms: int) -> Optional[dict]:
    """Find nearest occupancy snapshot within tolerance of timestamp."""
    ts_list = _state.get("occupancy_ts", [])
    if not ts_list:
        return None
    idx = bisect_left(ts_list, t_ms)
    candidates = []
    if idx < len(ts_list):
        candidates.append(ts_list[idx])
    if idx > 0:
        candidates.append(ts_list[idx - 1])
    if not candidates:
        return None
    best_ts = min(candidates, key=lambda ts: abs(ts - t_ms))
    tolerance_ms = _state.get("occupancy_match_tolerance_ms", OCCUPANCY_MATCH_TOLERANCE_MS)
    if abs(best_ts - t_ms) <= tolerance_ms:
        return _state["occupancy_by_timestamp"].get(best_ts)
    return None

def _process_tracker_batch(t_ms: int, batch: List[dict]):
    """Process tracker batch: update active set and event log."""
    stats = _state["stats"]
    # Process batch: if same ID appears multiple times, use the last one (dedupe by ID)
    by_id = {}
    for r in batch:
        human_id = r["id"]
        by_id[human_id] = r  # Last one wins if duplicates
    
    for human_id, r in by_id.items():
        new_active = r.get("active", True)
        stats["last_seen_any_ms"][human_id] = t_ms
        
        # Update last seen for active IDs
        if new_active:
            stats["last_seen_ms"][human_id] = t_ms
        
        # Track state changes
        was_active = human_id in stats["active_ids"]
        
        if new_active and not was_active:
            stats["active_ids"].add(human_id)
            stats["event_log"].append((t_ms, human_id, True))
        elif not new_active and was_active:
            stats["active_ids"].discard(human_id)
            if human_id in stats["last_seen_ms"]:
                del stats["last_seen_ms"][human_id]
            stats["event_log"].append((t_ms, human_id, False))

def _expire_stale(now_ms: int):
    """Remove IDs that haven't been seen recently."""
    stats = _state["stats"]
    to_remove = []
    for human_id in stats["active_ids"]:
        last_seen = stats["last_seen_ms"].get(human_id, 0)
        if now_ms - last_seen > STALE_MS:
            to_remove.append(human_id)
    
    for human_id in to_remove:
        stats["active_ids"].discard(human_id)
        if human_id in stats["last_seen_ms"]:
            del stats["last_seen_ms"][human_id]
        stats["event_log"].append((now_ms, human_id, False))

def _trim_event_log(now_ms: int):
    """Remove events older than window + buffer."""
    stats = _state["stats"]
    cutoff = now_ms - WINDOW_MS - 5000  # 5s buffer
    while stats["event_log"] and stats["event_log"][0][0] < cutoff:
        stats["event_log"].popleft()
    while stats["occupancy_log"] and stats["occupancy_log"][0][0] < cutoff:
        stats["occupancy_log"].popleft()

def _record_occupancy_sample(t_ms: int):
    """Record a point-in-time occupancy sample."""
    stats = _state["stats"]
    stats["occupancy_log"].append((t_ms, _current_occupancy_now(t_ms)))

def _current_occupancy_now(now_ms: int) -> int:
    """Get current occupancy: use occupancy snapshot if fresh, else tracker active set."""
    stats = _state["stats"]
    if (stats["latest_occupancy"] and 
        (now_ms - stats["latest_occupancy_t_ms"]) <= STALE_MS):
        return stats["latest_occupancy"].get("Human", 0)
    return len(stats["active_ids"])

def _unique_ids_seen_last_minute(now_ms: int) -> int:
    """Count distinct IDs active at any point in last minute."""
    stats = _state["stats"]
    window_start = now_ms - WINDOW_MS
    return sum(1 for t_ms in stats["last_seen_any_ms"].values() if t_ms >= window_start)

def _average_concurrent_last_minute(now_ms: int) -> float:
    """Time-weighted average occupancy over last minute using samples."""
    stats = _state["stats"]
    window_start = now_ms - WINDOW_MS
    log = stats["occupancy_log"]
    if not log:
        return float(_current_occupancy_now(now_ms))

    count_at_start = None
    for t_ms, count in log:
        if t_ms <= window_start:
            count_at_start = count
        else:
            break
    if count_at_start is None:
        count_at_start = log[0][1] if log else _current_occupancy_now(now_ms)

    area = 0.0
    prev_t = window_start
    prev_count = max(0, count_at_start)

    for t_ms, count in log:
        if t_ms <= window_start:
            continue
        if t_ms > now_ms:
            break
        dt = max(0, t_ms - prev_t)
        area += prev_count * dt
        prev_t = t_ms
        prev_count = max(0, count)

    dt_tail = max(0, now_ms - prev_t)
    area += prev_count * dt_tail
    return area / WINDOW_MS if WINDOW_MS > 0 else 0.0

def _max_concurrent_last_minute(now_ms: int) -> int:
    """Max occupancy observed in last minute (from samples)."""
    stats = _state["stats"]
    window_start = now_ms - WINDOW_MS
    max_count = 0
    for t_ms, count in stats["occupancy_log"]:
        if t_ms >= window_start:
            if count > max_count:
                max_count = count
    return max_count

def _traffic_level_last_minute(now_ms: int) -> str:
    """Traffic indicator based on density thresholds (Sweden context)."""
    avg_1m = _average_concurrent_last_minute(now_ms)
    max_1m = _max_concurrent_last_minute(now_ms)
    if max_1m <= 0 or CAMERA_AREA_M2 <= 0:
        return "low"
    peak_density = max_1m / float(CAMERA_AREA_M2)
    if peak_density <= 0.7:
        return "low"
    if peak_density <= 1.5:
        return "medium"
    if peak_density <= 2.5:
        return "high"
    return "critical"

def _send_stats_to_ui(now_ms: int):
    """Calculate and send statistics to UI."""
    try:
        from younite.messaging_core_extension.message_utils import dispatch_to_events2
        
        current = _current_occupancy_now(now_ms)
        unique_1m = _unique_ids_seen_last_minute(now_ms)
        avg_1m = _average_concurrent_last_minute(now_ms)
        traffic_level = _traffic_level_last_minute(now_ms)
        
        # Ensure avg is non-negative
        avg_1m = max(0.0, avg_1m)
        
        metrics = {
            "current": current,
            "unique_last_1m": unique_1m,
            "avg_concurrent_1m": round(avg_1m, 1),
            "traffic_level": traffic_level,
        }
        
        dispatch_to_events2("cameraDataVisualizationStats", metrics)
    except Exception as e:
        print(f"[Playback] Error sending stats: {e}")
        import traceback
        traceback.print_exc()


# -----------------------------
# Playback state
# -----------------------------
_subscription = None
_state = {
    "timestamps": [],
    "grouped": {},
    "occupancy_by_timestamp": {},
    "occupancy_ts": [],
    "occupancy_match_tolerance_ms": OCCUPANCY_MATCH_TOLERANCE_MS,
    "idx": 0,
    "accum": 0.0,
    "dt_target": 1.0 / FPS,
    "frame_skip": PLAY_EVERY_NTH_TIMESTAMP,
    "spheres": {},
    "sphere_positions": {},
    "sphere_targets": {},
    "detection_map": None,
    "playing": False,
    "loop": True,
    "camera_id": None,
    # Statistics state
    "stats": {
        "latest_occupancy": {},
        "latest_occupancy_t_ms": 0,
        "active_ids": set(),
        "last_seen_ms": {},
        "last_seen_any_ms": {},
        "event_log": deque(),  # (t_ms, id, is_active)
        "occupancy_log": deque(),  # (t_ms, count)
        "last_stats_update": 0.0,
    },
}

def start_playback(rows: List[dict], camera_id: str = "camera_main_entrance_exit", occupancy_by_timestamp: Optional[Dict[int, dict]] = None, footprint: Optional[Dict] = None, detection_map: Optional[Dict] = None):
    global _subscription
    print(f"[Playback] start_playback() called: {len(rows)} rows, camera_id={camera_id}, occupancy={len(occupancy_by_timestamp) if occupancy_by_timestamp else 0} messages")
    stage = omni.usd.get_context().get_stage()
    if not stage:
        print("[Playback] ERROR: No USD stage. Open/create a scene first.")
        raise RuntimeError("No USD stage. Open/create a scene first.")
    print(f"[Playback] Stage: {stage.GetRootLayer().identifier if stage else 'none'}")
    timestamps, grouped = group_by_timestamp(rows)
    print(f"[Playback] Grouped into {len(timestamps)} unique timestamps")
    if not timestamps:
        print("[Playback] ERROR: No usable tracker rows found (id/timestamp/x/y).")
        raise RuntimeError("No usable tracker rows found (id/timestamp/x/y).")
    _state["camera_id"] = camera_id
    _state["detection_map"] = detection_map
    print(f"[Playback] Detection map: {'yes' if detection_map else 'NO (positions will be inaccurate)'}")
    _state["timestamps"] = timestamps
    _state["grouped"] = grouped
    _state["occupancy_by_timestamp"] = occupancy_by_timestamp or {}
    _state["occupancy_ts"] = sorted(_state["occupancy_by_timestamp"].keys())
    _state["occupancy_match_tolerance_ms"] = _estimate_occupancy_tolerance_ms(_state["occupancy_ts"])
    _state["idx"] = 0
    _state["accum"] = 0.0
    _state["spheres"] = {}
    _state["sphere_positions"] = {}
    _state["sphere_targets"] = {}
    _state["playing"] = True
    _state["loop"] = True
    import carb.eventdispatcher
    ed = carb.eventdispatcher.get_eventdispatcher()
    _subscription = ed.observe_event(
        observer_name="younite.camera_data_visualization_extension/playback/update",
        event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
        on_event=_on_update,
        order=0,
    )
    print(f"[Playback] Camera '{camera_id}': Loaded {len(rows)} rows, {len(timestamps)} unique timestamps.")
    print(f"[Playback] Playing at {FPS} fps, looping: {_state['loop']}")
    print("[Playback] Update subscription created - spheres will appear and animate over time")

def stop_playback():
    global _subscription
    _state["playing"] = False
    if _subscription:
        _subscription = None
    
    # Remove all spheres from the stage
    try:
        stage = omni.usd.get_context().get_stage()
        if stage and _state.get("camera_id"):
            camera_id = _state["camera_id"]
            sphere_root_path = get_sphere_root_path(camera_id)
            root_prim = stage.GetPrimAtPath(sphere_root_path)
            if root_prim and root_prim.IsValid():
                # Delete the entire root Xform (this removes all child spheres)
                stage.RemovePrim(sphere_root_path)
                print(f"[Playback] Removed all spheres for camera '{camera_id}' from {sphere_root_path}")
    except Exception as e:
        print(f"[Playback] Error removing spheres: {e}")
    
    # Clear state
    _state["spheres"] = {}
    _state["sphere_positions"] = {}
    _state["sphere_targets"] = {}
    _state["detection_map"] = None
    _state["camera_id"] = None
    # Clear statistics state
    _state["stats"] = {
        "latest_occupancy": {},
        "latest_occupancy_t_ms": 0,
        "active_ids": set(),
        "last_seen_ms": {},
        "last_seen_any_ms": {},
        "event_log": deque(),
        "occupancy_log": deque(),
        "last_stats_update": 0.0,
    }
    _state["occupancy_ts"] = []
    _state["occupancy_match_tolerance_ms"] = OCCUPANCY_MATCH_TOLERANCE_MS
    
    print("[Playback] Stopped.")

def _on_update(e):
    stage = omni.usd.get_context().get_stage()
    if not stage or not _state["playing"]:
        return
    dt = float(getattr(e, "dt", 0.0)) if e else 0.0
    if dt <= 0.0:
        dt = 1.0 / 60.0
    _state["accum"] += dt
    stats = _state["stats"]
    stats["last_stats_update"] += dt
    
    if _state["accum"] >= _state["dt_target"]:
        _state["accum"] = 0.0
        timestamps = _state["timestamps"]
        if _state["idx"] >= len(timestamps):
            if _state["loop"]:
                _state["idx"] = 0
                _state["accum"] = 0.0
                _state["sphere_targets"] = {}
                # Reset stats on loop
                stats["active_ids"] = set()
                stats["last_seen_ms"] = {}
                stats["last_seen_any_ms"] = {}
                stats["event_log"].clear()
                stats["occupancy_log"].clear()
                print("[Playback] Looping back to start...")
            else:
                print("[Playback] Done.")
                stop_playback()
                return
        t = timestamps[_state["idx"]]
        _state["idx"] += _state["frame_skip"]
        batch = _state["grouped"][t]
        
        # Process occupancy for this timestamp
        occupancy_data = _get_occupancy_snapshot_near(t)
        if occupancy_data:
            _process_occupancy_batch(t, occupancy_data)
        
        # Process tracker batch
        _process_tracker_batch(t, batch)
        
        # Expire stale IDs
        _expire_stale(t)
        
        # Trim event log
        _trim_event_log(t)

        # Record occupancy sample after processing this timestamp
        _record_occupancy_sample(t)
        
        # Update sphere positions (existing logic)
        by_id = {}
        for r in batch:
            by_id[r["id"]] = r
        camera_id = _state["camera_id"]
        for human_id, r in by_id.items():
            prim = _state["spheres"].get(human_id)
            if prim is None or not prim.IsValid():
                prim = _create_or_get_sphere(stage, human_id, camera_id)
                _state["spheres"][human_id] = prim
            if not r["active"]:
                _set_visible(prim, False)
                if human_id in _state["sphere_targets"]:
                    del _state["sphere_targets"][human_id]
                continue
            _set_visible(prim, True)
            det_map = _state.get("detection_map")
            if det_map:
                from .camera_footprint import map_detection_to_world
                world_pos = map_detection_to_world(r["x"], r["y"], det_map)
                if world_pos:
                    target_sx, target_sy, target_sz = world_pos
                    target_sy += Y_HEIGHT
                else:
                    continue
            else:
                continue
            _state["sphere_targets"][human_id] = (target_sx, target_sy, target_sz)
        
        # Send stats to UI periodically
        if stats["last_stats_update"] >= STATS_UPDATE_INTERVAL:
            stats["last_stats_update"] = 0.0
            _send_stats_to_ui(t)
    for human_id, prim in _state["spheres"].items():
        if not prim or not prim.IsValid():
            continue
        target_pos = _state["sphere_targets"].get(human_id)
        if target_pos is None:
            continue
        current_pos = _state["sphere_positions"].get(human_id)
        if current_pos is None:
            current_pos = target_pos
            _state["sphere_positions"][human_id] = current_pos
        else:
            cx, cy, cz = current_pos
            tx, ty, tz = target_pos
            new_x = cx + (tx - cx) * LERP_SPEED
            new_y = cy + (ty - cy) * LERP_SPEED
            new_z = cz + (tz - cz) * LERP_SPEED
            current_pos = (new_x, new_y, new_z)
            _state["sphere_positions"][human_id] = current_pos
        translate_op = _ensure_xform_translate(prim)
        translate_op.Set(Gf.Vec3d(current_pos[0], current_pos[1], current_pos[2]))


# -----------------------------
# Public API
# -----------------------------
def main(
    camera_id: str = "camera_main_entrance_exit",
    data_source: Optional[List[Any]] = None,
    default_data_path: Optional[Path] = None,
    footprint: Optional[Dict] = None,
    detection_map: Optional[Dict] = None,
):
    """
    Main entry point for sphere tracker visualization.
    default_data_path: Path to mqtt_messages.json (e.g. extension data dir).
    footprint: Camera ground footprint dict from camera_footprint.compute_camera_footprint().
    """
    print(f"[Playback] main() called: camera_id={camera_id}, data_source={'yes' if data_source else 'no'}, default_data_path={default_data_path}")
    try:
        if data_source is not None:
            print("[Playback] Loading rows from data_source")
            rows, occupancy_by_timestamp = load_tracker_rows_from_data(data_source)
            print(f"[Playback] Loaded {len(rows)} rows, {len(occupancy_by_timestamp)} occupancy messages from data_source")
        else:
            json_path = default_data_path if default_data_path is not None else Path(__file__).parent / "data" / "mqtt_messages.json"
            json_path = Path(json_path)
            print(f"[Playback] Loading from JSON: {json_path}, exists={json_path.exists()}")
            if not json_path.exists():
                print(f"ERROR: JSON file not found: {json_path}")
                return
            rows, occupancy_by_timestamp = load_tracker_rows(str(json_path))
            print(f"[Playback] Loaded {len(rows)} rows, {len(occupancy_by_timestamp)} occupancy messages from JSON")
        if not rows:
            print(f"ERROR: No tracker rows found for camera '{camera_id}'.")
            return
        print(f"[Playback] Calling start_playback(rows={len(rows)}, camera_id={camera_id}, occupancy={len(occupancy_by_timestamp)} messages)")
        start_playback(rows, camera_id=camera_id, occupancy_by_timestamp=occupancy_by_timestamp, footprint=footprint, detection_map=detection_map)
        print("[Playback] main() finished successfully")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
