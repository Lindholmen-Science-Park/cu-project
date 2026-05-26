# Younite NavMesh Route Extension

This extension computes shortest paths on a baked NavMesh and (optionally) visualizes them as a `UsdGeom.BasisCurves` line in the stage.

It is designed to be controlled from the web UI via Kit events, and can also be reused from Python (or other extensions) for AI/navigation by consuming the computed waypoint list.

## What it does

- **Compute route**: shortest path between a **start** and **end** reference using `omni.anim.navigation.core` NavMesh `query_shortest_path`.
- **Multi-route**: supports multiple concurrent routes keyed by `routeId` (player + multiple NPCs).
- **Optional visualization**: draws/updates a curve prim per route.
- **Traffic / crowdness**: supports per-area costs (e.g. camera areas) to bias the route.
- **Reusable inputs**:
  - **Prim paths** (e.g. `"/World/PlayerCharacter"`, `"/World/Seats/Seat_42"`)
  - **World positions** (e.g. `[100, 0, 200]`)

## Web UI API (events)

### `navmeshRouteCalculate`

Send this event to start a route, or update an existing one (changing start/end is supported).

#### Payload fields

- **route identity**:
  - `routeId` (or `route_id`): string
  - Default: `"default"` (legacy single-route behavior)
- **start**:
  - `startpointPath` or `start`: USD prim path string
  - OR `startPos` / `startPosition` / `startWorldPos`: `[x,y,z]` or `{x,y,z}`
  - Default: `"/World/PlayerCharacter"`
- **end**:
  - `endpointPath` or `end`: USD prim path string
  - OR `endPos` / `endPosition` / `endWorldPos` / `targetPos`: `[x,y,z]` or `{x,y,z}`
  - Default: `"/World/EndPoint_Cube"`
- **draw / show debug line**:
  - `drawPath` (or `showPath`) boolean
  - Default:
    - `true` for `routeId == "default"`
    - `false` for any other routeId (NPC-safe default)
- **visualization options**:
  - `pathPrim`: curve prim path
    - Default:
      - `"/World/ShortestPathCurve"` for `routeId == "default"`
      - `"/World/NavmeshRoutes/<routeId>"` (sanitized) for other routeIds
  - `curveWidth`: float (default `10.0`)
- **behavior options**:
  - `enablePeriodicRecalc`: boolean (default `true`)
  - `startUseGround`: boolean (default `true`)
    - When `start` is a prim path, start position is resolved using a downward raycast to the ground (useful for capsule-based player characters whose origin is not at the feet).
- **traffic/crowdness**:
  - `cameraAreaCosts`: `{ "<area_name>": <cost>, ... }`
    - Higher cost = the route prefers to avoid that area when possible.

#### Examples

**1) Default route (legacy, player → endpoint)**

```json
{
  "startpointPath": "/World/PlayerCharacter",
  "endpointPath": "/World/EndPoint_Cube"
}
```

**2) Seat selection (player routeId → chosen seat prim)**

```json
{
  "routeId": "player",
  "endpointPath": "/World/Seats/Seat_42"
}
```

**3) Free A → B (bird’s eye / maps style), using world positions**

```json
{
  "routeId": "planner:ab_test",
  "startPos": [100, 0, 200],
  "endPos": [500, 0, 900]
}
```

**4) Update endpoint while route is already active**

```json
{
  "routeId": "player",
  "endpointPath": "/World/Seats/Seat_99"
}
```

**5) Compute route but hide the debug line**

```json
{
  "routeId": "player",
  "endpointPath": "/World/Seats/Seat_42",
  "drawPath": false
}
```

**6) Apply traffic/crowdness (camera area costs)**

```json
{
  "routeId": "player",
  "endpointPath": "/World/Seats/Seat_42",
  "cameraAreaCosts": {
    "cctv1_navmesh_area": 10.0,
    "cctv2_navmesh_area": 1.0
  }
}
```

### `navmeshRouteWaypoints`

Emitted after a route is computed (and on updates). Use this to consume the path from other extensions (e.g. NPC AI).

Payload:
- `routeId`: string
- `success`: boolean
- `points`: `[[x,y,z], ...]`
- `error`: optional string (when `success=false`)

### `navmeshRouteStop`

Stops periodic recalculation and clears the curve prim (if any).
Supports stopping one route or all routes:
- Stop one: `{ "routeId": "player" }`
- Stop all: `{ "all": true }`

```json
{ "routeId": "player" }
```

### `navmeshCameraAreaCostUpdate`

Update a single area cost while the route is active.

```json
{
  "areaName": "cctv1_navmesh_area",
  "cost": 7.5
}
```

## Python usage (AI movement / path consumption)

The service computes routes and stores the last computed waypoint list per `routeId` as world positions.

Example usage from another extension:

```python
from younite.navmesh_route_extension.services.kit_services.navmesh_route_service import NavMeshRouteService

svc = NavMeshRouteService()

# Plan a path for AI without drawing (single-shot), using a dedicated routeId
svc.set_route_for_id(
    "npc:npc_01",
    "/World/AICharacter",
    "/World/Seats/Seat_42",
    draw_path=False,
    enable_periodic_recalc=False,
)

waypoints = svc.get_last_path_points("npc:npc_01")  # [(x,y,z), ...]
```

Notes:
- If you want continuous replanning (e.g. moving target), set `enable_periodic_recalc=True` and update `start_ref`/`end_ref` as needed.
- If you pass explicit positions for both endpoints, periodic recalculation will only happen when something changes (e.g. costs change or you call `set_route` again).

## Implementation notes / edge cases

- **NavMesh baking in progress**:
  - Initial calculation waits for baking to finish (up to a time limit), then attempts anyway.
  - Direct path queries while baking can return an error; this is expected behavior.
- **Start/end not on the NavMesh**:
  - If the shortest-path query returns \(0\) or \(1\) points, the code treats it as a failure and reports that start/end are likely not on/near the navmesh.
  - Fix by moving points onto walkable surfaces inside the NavMesh volume.
- **Ground projection for player start**:
  - `startUseGround=true` raycasts down from the start prim to find ground. This avoids “floating” starts for capsule characters.
  - For non-character starts (or if raycast is unavailable), you can set `startUseGround=false`.
- **Visualization on/off**:
  - `drawPath=false` removes any previously drawn curve and keeps computing waypoint lists.
- **Route updates**:
  - Re-sending `navmeshRouteCalculate` while active updates the current route (no stop/restart required).
- **Performance**:
  - Periodic replanning runs every 5 seconds by default. If your target moves frequently, you can keep this enabled; otherwise disable it to reduce work.

## Code structure

- `younite/navmesh_route_extension/extension.py`
  - Subscribes to Kit events and forwards requests to the service.
- `younite/navmesh_route_extension/services/kit_services/navmesh_route_service/` (`service.py`, `constants.py`, `waypoint_dispatch.py`, `refs.py`)
  - Route manager: handles per-route lifecycle, periodic recalculation, optional drawing, stores last waypoint list per routeId.
- `younite/navmesh_route_extension/scripts/navmesh_shortest_path/` (package)
  - Low-level NavMesh query, metrics, FP sphere trail, route-end flag (`calculate_path_points`, `draw_path_curve`, …). See `.cursor/rules/topics/navmesh-shortest-path-package.mdc`.

