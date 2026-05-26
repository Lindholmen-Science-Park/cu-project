import i18n from '../../../../i18n';
import { sendMessage } from '../../messaging';
import { beginViewTransition, notifyViewTransitionKitReady } from '../../viewTransition';
import type { TransitLiveOverlayVehicleRow } from '../../types';
import type { EventStateSetters } from './types';

function parseTransitLiveOverlayVehicles(raw: unknown): TransitLiveOverlayVehicleRow[] {
    if (!Array.isArray(raw)) {
        return [];
    }
    const out: TransitLiveOverlayVehicleRow[] = [];
    for (const item of raw) {
        if (!item || typeof item !== 'object') continue;
        const r = item as Record<string, unknown>;
        const token = r.token != null && String(r.token).trim() !== '' ? String(r.token) : '';
        if (!token) continue;
        const sx = r.sceneXyzCm;
        const sceneXyzCm: [number, number, number] =
            Array.isArray(sx) && sx.length >= 3
                ? [Number(sx[0]) || 0, Number(sx[1]) || 0, Number(sx[2]) || 0]
                : [0, 0, 0];
        const yRaw = r.yawDeg;
        const yawDeg = typeof yRaw === 'number' && !Number.isNaN(yRaw) ? yRaw : Number(yRaw) || 0;
        const base: TransitLiveOverlayVehicleRow = { token, sceneXyzCm, yawDeg };
        const extras: Partial<TransitLiveOverlayVehicleRow> = {};
        for (const [k, v] of Object.entries(r)) {
            if (k === 'token' || k === 'sceneXyzCm' || k === 'yawDeg') continue;
            if (v === null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
                (extras as Record<string, string | number | boolean | null>)[k] = v;
            }
        }
        out.push({ ...base, ...extras });
    }
    return out;
}

export function handleSceneEvents(event: any, s: EventStateSetters): void {
    if (event.event_type === 'viewTransitionReady') {
        notifyViewTransitionKitReady();
        return;
    }

    if (event.event_type === 'scene.loaded') {
        const vt = String((event.payload || {}).viewType || '');
        // Don't overwrite the web-only 'space' mode (see worldStateHandlers).
        if (vt === 'firstPerson') s.setCurrentCamera((cur) => (cur === 'space' ? cur : 'first_person'));
        else if (vt === 'birdEye') s.setCurrentCamera((cur) => (cur === 'space' ? cur : 'bird_eye'));
        return;
    }

    if (event.event_type === 'sceneListSync') {
        const list = event.payload?.scenes;
        if (Array.isArray(list)) {
            s.setAvailableScenes(list.map((sc: any) => ({ id: String(sc.id || ''), label: String(sc.label || sc.id || '') })));
        }
        return;
    }

    if (event.event_type === 'stadiumLodResponse') {
        const p = event.payload || {};
        if (p.result === 'success' && p.lod) {
            s.setStadiumLodLight(p.lod === 'full');
        }
        return;
    }

    if (event.event_type === 'peopleToggleStatus') {
        s.setPeopleVisible(event.payload.enabled === true);
        console.log(`People: enabled=${event.payload.enabled}`);
        return;
    }

    if (event.event_type === 'lightCullingToggleStatus') {
        s.setLightCullingEnabled(event.payload.enabled === true);
        console.log(`Light culling: enabled=${event.payload.enabled}`);
        return;
    }

    if (event.event_type === 'tileCullingToggleStatus') {
        s.setTileCullingEnabled(event.payload.enabled === true);
        console.log(`Tile culling: enabled=${event.payload.enabled}`);
        return;
    }

    if (event.event_type === 'npcStatus') {
        const p = event.payload || {};
        const id = String(p.npcId || '');
        if (id.startsWith('test_npc_')) s.setNpcTestActive(p.active === true);
        return;
    }

    if (event.event_type === 'npcArrived') {
        const p = event.payload || {};
        const id = String(p.npcId || '');
        if (id.startsWith('test_npc_')) s.setNpcTestActive(false);
        return;
    }

    if (event.event_type === 'maintenanceBotStatus') {
        s.setMaintenanceBotsActive((event.payload || {}).active === true);
        return;
    }

    if (event.event_type === 'maintenanceBotIncidentUpdate') {
        const p = event.payload || {};
        const eta = p.eta != null ? ` ETA=${p.eta}s` : '';
        console.log(`[MaintenanceBot] ${p.action || ''}: bot=${p.botId || '?'} incident=${p.incidentId || '?'} severity=${p.severity ?? '?'} status=${p.status || ''}${eta}`);
        return;
    }

    if (event.event_type === 'soundDataCalcStatus') {
        const p = event.payload || {};
        const status = String(p.status || '');
        const active = Boolean(p.active);
        if (status === 'baking') { s.setSoundDataCalcBaking(true); }
        else { s.setSoundDataCalcBaking(false); s.setSoundDataCalcActive(active); }
        return;
    }

    if (event.event_type === 'transitLiveOverlayStatus') {
        const p = event.payload || {};
        s.setTransitLiveOverlayStatus({
            enabled: p.enabled === true,
            vehicleCount: typeof p.vehicleCount === 'number' ? p.vehicleCount : 0,
            lastError: p.lastError != null ? String(p.lastError) : null,
            lastFetchEpochMs: typeof p.lastFetchEpochMs === 'number' ? p.lastFetchEpochMs : 0,
            hasApiKey: p.hasApiKey === true,
            transitSource: p.transitSource != null ? String(p.transitSource) : undefined,
            hint: p.hint != null ? String(p.hint) : undefined,
            vehicles: parseTransitLiveOverlayVehicles(p.vehicles),
        });
        return;
    }

    if (event.event_type === 'shortcutTraversalBegin') {
        // Kit says the player has reached an elevator entrance: fade to
        // black, and once the fade-out animation is done tell Kit it's
        // safe to teleport. Kit will dispatch `viewTransitionReady`
        // post-teleport (handled at the top of this function) to fade
        // back in.
        const p = event.payload || {};
        const routeId = String(p.routeId || '');
        const message =
            (i18n.exists('streaming.shortcutTraversal') ? i18n.t('streaming.shortcutTraversal') : null) ||
            (i18n.exists('streaming.switchingFirstPerson') ? i18n.t('streaming.switchingFirstPerson') : null) ||
            'Taking elevator…';
        beginViewTransition({
            target: 'firstPerson',
            message,
            onFadeOutComplete: () => {
                try { sendMessage('shortcutTraversalProceed', { routeId }); } catch {}
            },
        });
        return;
    }

    if (event.event_type === 'shortcutTraversalComplete' || event.event_type === 'shortcutTraversalError') {
        return;
    }

    if (event.event_type === 'shortcutsStatus') {
        const active = (event.payload || {}).active === true;
        if (s.setShortcutsActive) s.setShortcutsActive(active);
        return;
    }

    if (event.event_type === 'viewportCaptureResult') {
        const p = event.payload || {};
        const status = String(p.status || '');
        if (status === 'capturing') {
            s.setViewportCaptureStatus('capturing');
        } else if (status === 'ready') {
            const port = Number(p.port);
            const captureId = String(p.captureId || '');
            const filename = String(p.filename || 'capture.jpg');
            const host = window.location.hostname || '127.0.0.1';
            const url = `http://${host}:${port}/${captureId}`;
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            link.click();
            s.setViewportCaptureStatus('idle');
            console.log(`[viewport_capture] Downloading rendered capture ${p.width}x${p.height} from ${url}`);
        } else if (status === 'error') {
            console.error(`[viewport_capture] Error: ${p.error}`);
            s.setViewportCaptureStatus('idle');
        }
        return;
    }
}
