import { sendMessage } from '../../messaging';
import type { InteractionPointDef, InteractionBehavior } from '../../types';
import type { EventStateSetters } from './types';
import { showTriggerNotification } from './helpers';

export function handleInteractionEvents(event: any, s: EventStateSetters): void {
    if (event.event_type === 'uiInteractionBoxesUpdate') {
        if (s.sceneLoadingRef.current) return;
        try {
            const p = event.payload || {};
            s.setUiInteractionBoxes({
                timestampMs: Number(p.timestampMs || Date.now()),
                viewport: p.viewport && p.viewport.width && p.viewport.height ? { width: Number(p.viewport.width), height: Number(p.viewport.height) } : null,
                items: Array.isArray(p.items) ? p.items : [],
            });
        } catch {}
        return;
    }

    if (event.event_type === 'interactionTriggered') {
        try {
            const p = event.payload || {};
            const action = String(p.action || '');
            const interactableId = String(p.interactableId || '');
            const payload = (p.payload && typeof p.payload === 'object') ? p.payload : {};

            if (s.dispatchInteractionAction && s.dispatchInteractionAction(interactableId, action, payload)) {
                console.log(`[interactionTriggered] dispatched: action=${action}`, { interactableId, payload });
            } else if (action === 'debug.consoleLog') {
                console.log(`[interactionTriggered] ${String((payload as any).message || `${interactableId} triggered`)}`, { interactableId, payload });
            } else {
                console.log(`[interactionTriggered] action=${action}`, { interactableId, payload });
            }
        } catch {}
        return;
    }

    if (event.event_type === 'interactionPointsSync') {
        try {
            const p = event.payload || {};
            const points = Array.isArray(p.points) ? p.points : [];
            s.setInteractionPointDefs(points as InteractionPointDef[]);
            console.log(`[interactions] Synced ${points.length} interaction point definitions from Kit`);
        } catch {}
        return;
    }

    if (event.event_type === 'devMediaRegistryResponse') {
        try {
            const p = event.payload || {};
            const items = Array.isArray(p.items) ? p.items : [];
            s.setMediaAdminKitRegistry?.(
                items as Array<{
                    pattern: string;
                    primPath: string;
                    primName: string;
                    worldTranslate: [number, number, number] | null;
                }>,
            );
        } catch {}
        return;
    }

    if (event.event_type === 'devLocaleJsonWriteResult') {
        try {
            const p = event.payload || {};
            const ok = !!p.ok;
            s.setDevLocaleWriteStatus?.({
                ok,
                message: p.message != null ? String(p.message) : undefined,
                error: p.error != null ? String(p.error) : undefined,
            });
        } catch {}
        return;
    }

    if (event.event_type === 'npcNearestUpdate') {
        try {
            const p = event.payload || {};
            const nearest = p.nearest;
            if (nearest && typeof nearest === 'object' && nearest.npcConfig) {
                s.setNearestNpc({
                    id: String(nearest.id || ''),
                    npcConfig: nearest.npcConfig,
                    distanceMeters: Number(nearest.distanceMeters || 0),
                });
            } else {
                s.setNearestNpc(null);
            }
        } catch {}
        return;
    }

    if (event.event_type === 'iconNearestUpdate') {
        try {
            const p = event.payload || {};
            const nearest = p.nearest;
            if (nearest && typeof nearest === 'object' && nearest.iconConfig) {
                s.setNearestIcon({
                    id: String(nearest.id || ''),
                    iconConfig: nearest.iconConfig,
                    distanceMeters: Number(nearest.distanceMeters || 0),
                });
            } else {
                s.setNearestIcon(null);
            }
        } catch {}
        return;
    }

    if (event.event_type === 'birdEyePinSheet') {
        try {
            const p = event.payload || {};
            const wp = p.worldPos || {};
            if (s.openMapMarkerSheet && typeof wp.x === 'number' && typeof wp.z === 'number') {
                s.openMapMarkerSheet({
                    id: String(p.id || `pin_${Date.now()}`),
                    title: String(p.title || 'Pinned location'),
                    spawnPoint: String(p.spawnPoint || ''),
                    primPath: '',
                    isAdHocPin: true,
                    worldPos: { x: Number(wp.x), y: Number(wp.y || 0), z: Number(wp.z) },
                    isInsideNavmesh: !!p.isInsideNavmesh,
                    magnetName: String(p.magnetName || ''),
                });
            }
        } catch {}
        return;
    }

    if (event.event_type === 'birdEyePinError') {
        try {
            const msg = String(event.payload?.error || 'Could not place a pin there.');
            console.warn('[bird-eye pin]', msg);
        } catch {}
        return;
    }

    if (event.event_type === 'birdEyeRouteOverlay') {
        try {
            const p = event.payload || {};
            const points = Array.isArray(p.points) ? p.points : [];
            const osmPoints = Array.isArray(p.osmPoints) ? p.osmPoints : [];
            // `pinMarker` is a single {sx, sy} object emitted while the
            // bird-eye pin sheet is open (before directions are requested).
            // Rendered by BirdEyeRouteOverlay as a solo flag bubble.
            const parseMarker = (raw: any) =>
                raw && typeof raw === 'object' && Number.isFinite(Number(raw.sx)) && Number.isFinite(Number(raw.sy))
                    ? { sx: Number(raw.sx), sy: Number(raw.sy) }
                    : null;
            const pinMarker = parseMarker(p.pinMarker);
            // `startMarker` / `endMarker` pin the composed polyline's
            // true first/last vertex. Without these, the overlay would
            // fall back to ``navPts[0]`` / ``osmPts.last`` heuristics
            // that misplace the start bubble on OSM→NavMesh and cross-
            // island routes (the bridge vertex gets picked instead of
            // the actual user start position).
            const startMarker = parseMarker(p.startMarker);
            const endMarker = parseMarker(p.endMarker);
            const viewport = p.viewport && p.viewport.width && p.viewport.height
                ? { width: Number(p.viewport.width), height: Number(p.viewport.height) }
                : null;
            if (s.setBirdEyeRoutePoints) {
                // Null the state only when polylines AND pin marker are
                // all empty — a solo pin marker (pin sheet before
                // directions) is a valid, renderable state.
                const hasAny = points.length > 0 || osmPoints.length > 0 || pinMarker !== null;
                s.setBirdEyeRoutePoints(
                    hasAny
                        ? { points, osmPoints, pinMarker, startMarker, endMarker, viewport }
                        : null,
                );
            }
        } catch {}
        return;
    }

    if (event.event_type === 'interactionPointTriggered') {
        try {
            const p = event.payload || {};
            const pointId = String(p.pointId || '');
            const triggerType = String(p.triggerType || 'proximity');
            const behaviors: InteractionBehavior[] = Array.isArray(p.behaviors) ? p.behaviors : [];

            console.log(`[interactions] Triggered: ${pointId} (trigger=${triggerType}, behaviors=${behaviors.length})`, behaviors);

            for (const beh of behaviors) {
                const behType = String(beh.type || '');
                if (behType === 'notification') {
                    const soundName = String(beh.sound || 'info');
                    const message = String(beh.message || `Arrived at ${pointId}`);
                    showTriggerNotification(s, message, triggerType);

                    s.setInteractionPointDefs((defs) => {
                        const def = defs.find((d) => d.id === pointId);
                        if (def?.category === 'navigation' && pointId) {
                            try { sendMessage('navmeshRouteStop', { routeId: pointId }); } catch {}
                            s.setActiveSpotRouteId((cur) => (cur === pointId ? null : cur));
                            s.setMovingToSpotId((cur) => (cur === pointId ? null : cur));
                        }
                        return defs;
                    });
                }
            }
        } catch {}
        return;
    }
}
