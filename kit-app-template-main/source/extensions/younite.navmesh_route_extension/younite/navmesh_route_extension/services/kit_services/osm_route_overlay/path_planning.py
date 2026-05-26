"""Dijkstra + polyline assembly over the cached visible OSM subgraph."""

from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Set, Tuple

from .constants import (
    AT_JUNCTION_RADIUS_CM,
    MAX_AUTO_ADVANCE_HOPS,
    NEAR_ROUTE_RADIUS_CM,
)
from .polyline_math import dedupe_polyline, projection_is_forward, xz_dist
from .spatial_queries import closest_visible_edge_endpoints


def node_world_pos(
    nid: str,
    visible_node_pos: Dict[str, Tuple[float, float, float]],
    ox: float,
    oz: float,
) -> Optional[Tuple[float, float, float]]:
    pos = visible_node_pos.get(nid)
    if pos is None:
        return None
    return (pos[0] + ox, pos[1], pos[2] + oz)


def node_degree(nid: str, visible_adj: Dict[str, List[Tuple[str, float]]]) -> int:
    return len(visible_adj.get(nid, ()))


def dijkstra_visible(
    src: str,
    dsts: Set[str],
    visible_adj: Dict[str, List[Tuple[str, float]]],
) -> Dict[str, Tuple[float, Optional[str]]]:
    dist: Dict[str, float] = {src: 0.0}
    prev: Dict[str, Optional[str]] = {src: None}
    pq: List[Tuple[float, str]] = [(0.0, src)]
    remaining = set(dsts)
    remaining.discard(src)
    while pq and remaining:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, float("inf")):
            continue
        if u in remaining:
            remaining.discard(u)
        for v, w in visible_adj.get(u, ()):
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return {n: (dist[n], prev.get(n)) for n in dist}


def player_chain_edges(
    player_xyz: Tuple[float, float, float],
    *,
    visible_adj: Dict[str, List[Tuple[str, float]]],
    visible_node_pos: Dict[str, Tuple[float, float, float]],
    ox: float,
    oz: float,
) -> Set[frozenset]:
    if not visible_adj:
        return set()
    proj = closest_visible_edge_endpoints(
        player_xyz[0],
        player_xyz[2],
        visible_adj=visible_adj,
        visible_node_pos=visible_node_pos,
        ox=ox,
        oz=oz,
    )
    if proj is None:
        return set()
    _, _, na, nb, _ = proj
    edges: Set[frozenset] = {frozenset((na, nb))}

    for came_from, start in ((nb, na), (na, nb)):
        prev = came_from
        cur = start
        for _ in range(MAX_AUTO_ADVANCE_HOPS):
            deg = node_degree(cur, visible_adj)
            if deg >= 3 or deg == 1:
                break
            nxt: Optional[str] = None
            for nb_id, _w in visible_adj.get(cur, ()):
                if nb_id != prev:
                    nxt = nb_id
                    break
            if nxt is None:
                break
            edges.add(frozenset((cur, nxt)))
            prev = cur
            cur = nxt
    return edges


def is_same_chain_as_player(
    player_xyz: Tuple[float, float, float],
    click_xyz: Tuple[float, float, float],
    *,
    visible_adj: Dict[str, List[Tuple[str, float]]],
    visible_node_pos: Dict[str, Tuple[float, float, float]],
    ox: float,
    oz: float,
) -> bool:
    chain_edges = player_chain_edges(
        player_xyz,
        visible_adj=visible_adj,
        visible_node_pos=visible_node_pos,
        ox=ox,
        oz=oz,
    )
    if not chain_edges:
        return False
    proj = closest_visible_edge_endpoints(
        click_xyz[0],
        click_xyz[2],
        visible_adj=visible_adj,
        visible_node_pos=visible_node_pos,
        ox=ox,
        oz=oz,
    )
    if proj is None:
        return False
    _, _, ca, cb, _ = proj
    return frozenset((ca, cb)) in chain_edges


def plan_visible_polyline(
    player_xyz: Tuple[float, float, float],
    target_xyz: Tuple[float, float, float],
    *,
    visible_adj: Dict[str, List[Tuple[str, float]]],
    visible_node_pos: Dict[str, Tuple[float, float, float]],
    ox: float,
    oz: float,
) -> Optional[List[Tuple[float, float, float]]]:
    if not visible_adj:
        return None

    entry = closest_visible_edge_endpoints(
        player_xyz[0],
        player_xyz[2],
        visible_adj=visible_adj,
        visible_node_pos=visible_node_pos,
        ox=ox,
        oz=oz,
    )
    exit_ = closest_visible_edge_endpoints(
        target_xyz[0],
        target_xyz[2],
        visible_adj=visible_adj,
        visible_node_pos=visible_node_pos,
        ox=ox,
        oz=oz,
    )
    if entry is None or exit_ is None:
        return None

    entry_proj, _, ea, eb, _ = entry
    exit_proj, _, xa, xb, _ = exit_

    same_edge = {ea, eb} == {xa, xb}
    if same_edge:
        return dedupe_polyline([player_xyz, entry_proj, exit_proj, target_xyz])

    targets = {xa, xb}

    best_total = float("inf")
    best_nodes: Optional[List[str]] = None
    best_entry_node: Optional[str] = None
    best_exit_node: Optional[str] = None

    for src in (ea, eb):
        if src not in visible_adj:
            continue
        src_world = node_world_pos(src, visible_node_pos, ox, oz)
        if src_world is None:
            continue
        player_to_entry = xz_dist(player_xyz, src_world)
        settled = dijkstra_visible(src, targets, visible_adj)
        for tgt in targets:
            rec = settled.get(tgt)
            if rec is None:
                continue
            tgt_world = node_world_pos(tgt, visible_node_pos, ox, oz)
            if tgt_world is None:
                continue
            exit_to_target = xz_dist(tgt_world, target_xyz)
            total = player_to_entry + rec[0] + exit_to_target
            if total < best_total:
                path: List[str] = []
                cur: Optional[str] = tgt
                while cur is not None:
                    path.append(cur)
                    cur = settled.get(cur, (0.0, None))[1]
                path.reverse()
                if path and path[0] == src:
                    best_total = total
                    best_nodes = path
                    best_entry_node = src
                    best_exit_node = tgt

    if best_nodes is None:
        print(
            "[osm_route_overlay] visible subgraph: no path between"
            f" entry={ea}/{eb} and exit={xa}/{xb}"
        )
        return dedupe_polyline([player_xyz, entry_proj, exit_proj, target_xyz])

    node_pts: List[Tuple[float, float, float]] = []
    for nid in best_nodes:
        np_ = node_world_pos(nid, visible_node_pos, ox, oz)
        if np_ is not None:
            node_pts.append(np_)

    entry_node_world = (
        node_world_pos(best_entry_node, visible_node_pos, ox, oz)
        if best_entry_node
        else None
    )
    exit_node_world = (
        node_world_pos(best_exit_node, visible_node_pos, ox, oz)
        if best_exit_node
        else None
    )

    polyline: List[Tuple[float, float, float]] = [player_xyz]
    if entry_node_world is not None and projection_is_forward(
        player_xyz, entry_proj, entry_node_world
    ):
        polyline.append(entry_proj)
    polyline.extend(node_pts)
    if exit_node_world is not None and projection_is_forward(
        exit_node_world, exit_proj, target_xyz
    ):
        polyline.append(exit_proj)
    polyline.append(target_xyz)
    return dedupe_polyline(polyline)


def traverse_chain_to_junction(
    prev_node: str,
    cur_node: str,
    *,
    visible_adj: Dict[str, List[Tuple[str, float]]],
    visible_node_pos: Dict[str, Tuple[float, float, float]],
    ox: float,
    oz: float,
) -> List[Tuple[float, float, float]]:
    out: List[Tuple[float, float, float]] = []
    visited: Set[str] = {prev_node}
    prev = prev_node
    cur = cur_node
    for _ in range(MAX_AUTO_ADVANCE_HOPS):
        cw = node_world_pos(cur, visible_node_pos, ox, oz)
        if cw is None:
            break
        out.append(cw)
        deg = node_degree(cur, visible_adj)
        if deg >= 3 or deg == 1:
            break
        if cur in visited:
            break
        visited.add(cur)
        nxt: Optional[str] = None
        for nb, _w in visible_adj.get(cur, ()):
            if nb != prev:
                nxt = nb
                break
        if nxt is None:
            break
        prev = cur
        cur = nxt
    return out


def plan_auto_advance_polyline(
    player_xyz: Tuple[float, float, float],
    forward_xz: Tuple[float, float],
    *,
    visible_adj: Dict[str, List[Tuple[str, float]]],
    visible_node_pos: Dict[str, Tuple[float, float, float]],
    ox: float,
    oz: float,
) -> Optional[List[Tuple[float, float, float]]]:
    if not visible_adj or not visible_node_pos:
        return None
    fx, fz = forward_xz

    nearest_node: Optional[str] = None
    nearest_d2 = float("inf")
    for nid in visible_node_pos:
        nw = node_world_pos(nid, visible_node_pos, ox, oz)
        if nw is None:
            continue
        dx = nw[0] - player_xyz[0]
        dz = nw[2] - player_xyz[2]
        d2 = dx * dx + dz * dz
        if d2 < nearest_d2:
            nearest_d2 = d2
            nearest_node = nid

    radius2 = AT_JUNCTION_RADIUS_CM * AT_JUNCTION_RADIUS_CM
    at_junction = (
        nearest_node is not None
        and nearest_d2 <= radius2
        and node_degree(nearest_node, visible_adj) >= 3
    )

    if at_junction:
        assert nearest_node is not None
        jw = node_world_pos(nearest_node, visible_node_pos, ox, oz)
        if jw is None:
            return None
        best_nb: Optional[str] = None
        best_dot = -2.0
        for nb, _w in visible_adj.get(nearest_node, ()):
            nbw = node_world_pos(nb, visible_node_pos, ox, oz)
            if nbw is None:
                continue
            dx = nbw[0] - jw[0]
            dz = nbw[2] - jw[2]
            ln = math.hypot(dx, dz)
            if ln < 1.0:
                continue
            dot = (dx / ln) * fx + (dz / ln) * fz
            if dot > best_dot:
                best_dot = dot
                best_nb = nb
        if best_nb is None:
            return None
        chain = traverse_chain_to_junction(
            nearest_node,
            best_nb,
            visible_adj=visible_adj,
            visible_node_pos=visible_node_pos,
            ox=ox,
            oz=oz,
        )
        if not chain:
            return None
        return dedupe_polyline([player_xyz, *chain])

    proj = closest_visible_edge_endpoints(
        player_xyz[0],
        player_xyz[2],
        visible_adj=visible_adj,
        visible_node_pos=visible_node_pos,
        ox=ox,
        oz=oz,
    )
    if proj is None:
        return None
    proj_xyz, proj_dist, na, nb, _t = proj
    if proj_dist > NEAR_ROUTE_RADIUS_CM:
        return None
    naw = node_world_pos(na, visible_node_pos, ox, oz)
    nbw = node_world_pos(nb, visible_node_pos, ox, oz)
    if naw is None or nbw is None:
        return None

    dot_a = (naw[0] - proj_xyz[0]) * fx + (naw[2] - proj_xyz[2]) * fz
    dot_b = (nbw[0] - proj_xyz[0]) * fx + (nbw[2] - proj_xyz[2]) * fz
    if dot_a >= dot_b:
        prev_node, next_node = nb, na
    else:
        prev_node, next_node = na, nb

    polyline: List[Tuple[float, float, float]] = [player_xyz]
    next_world = node_world_pos(next_node, visible_node_pos, ox, oz)
    if next_world is not None and projection_is_forward(player_xyz, proj_xyz, next_world):
        polyline.append(proj_xyz)
    chain = traverse_chain_to_junction(
        prev_node,
        next_node,
        visible_adj=visible_adj,
        visible_node_pos=visible_node_pos,
        ox=ox,
        oz=oz,
    )
    polyline.extend(chain)
    return dedupe_polyline(polyline)
