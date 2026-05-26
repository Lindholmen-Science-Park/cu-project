/** Floor hop targets embedded in POI coin metadata by ``coins_loader`` (from ``shortcuts.json``). */
export interface ElevatorRideDestination {
    node_id: string;
    prim_path: string;
    label_en?: string;
    i18n_key?: string;
    level?: number;
}

export interface ElevatorRideMeta {
    group_id: string;
    current_node_id: string;
    destinations: ElevatorRideDestination[];
}

export function parseElevatorRide(metadata: Record<string, unknown> | null | undefined): ElevatorRideMeta | null {
    const raw = metadata?.elevator_ride;
    if (!raw || typeof raw !== 'object') return null;
    const er = raw as Record<string, unknown>;
    const dests = er.destinations;
    if (!Array.isArray(dests) || dests.length === 0) return null;
    const destinations: ElevatorRideDestination[] = [];
    for (const d of dests) {
        if (!d || typeof d !== 'object') continue;
        const row = d as Record<string, unknown>;
        const prim_path = String(row.prim_path || '').trim();
        const node_id = String(row.node_id || '').trim();
        if (!prim_path || !node_id) continue;
        destinations.push({
            node_id,
            prim_path,
            label_en: typeof row.label_en === 'string' ? row.label_en : undefined,
            i18n_key: typeof row.i18n_key === 'string' ? row.i18n_key : undefined,
            level: typeof row.level === 'number' ? row.level : undefined,
        });
    }
    if (!destinations.length) return null;
    const group_id = String(er.group_id || '').trim();
    const current_node_id = String(er.current_node_id || '').trim();
    if (!group_id || !current_node_id) return null;
    return { group_id, current_node_id, destinations };
}
