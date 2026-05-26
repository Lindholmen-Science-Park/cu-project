"""Build ``ShortcutGroup`` objects from JSON config + USD positions."""
from __future__ import annotations

from typing import Dict

from .constants import LOG_PREFIX
from .types import ShortcutGroup, ShortcutNode, Vec3


def build_shortcut_groups(
    cfg: Dict,
    positions: Dict[str, Vec3],
) -> Dict[str, ShortcutGroup]:
    out: Dict[str, ShortcutGroup] = {}
    groups_cfg = cfg.get("groups") or []
    for g in groups_cfg:
        gid = str(g.get("id") or "").strip()
        if not gid:
            continue
        try:
            travel_s = float(g.get("traversalSeconds") or 5.0)
        except Exception:
            travel_s = 5.0
        try:
            wait_s = float(g.get("waitSeconds") or 0.0)
        except Exception:
            wait_s = 0.0
        serves_raw = g.get("servesSections")
        if isinstance(serves_raw, list):
            serves_sections = frozenset(
                str(s).strip().upper() for s in serves_raw if str(s).strip()
            )
        else:
            serves_sections = frozenset()
        grp = ShortcutGroup(
            group_id=gid,
            type_=str(g.get("type") or "shortcut"),
            label=str(g.get("labelEn") or gid),
            i18n_key=g.get("i18nKey"),
            traversal_seconds=travel_s,
            wait_seconds=wait_s,
            edges=g.get("edges", "all"),
            serves_sections=serves_sections,
        )
        for n in g.get("nodes") or []:
            nid = str(n.get("id") or "").strip()
            pp = str(n.get("primPath") or "").strip()
            if not nid or not pp:
                continue
            pos = positions.get(pp)
            if pos is None:
                print(
                    f"{LOG_PREFIX} Node {gid}/{nid} primPath {pp!r} "
                    "not found in USD; skipping"
                )
                continue
            grp.nodes.append(
                ShortcutNode(
                    group_id=gid,
                    node_id=nid,
                    type_=grp.type_,
                    prim_path=pp,
                    label=str(n.get("labelEn") or nid),
                    i18n_key=n.get("i18nKey"),
                    pos=pos,
                )
            )
        if len(grp.nodes) >= 2:
            out[gid] = grp
    return out
