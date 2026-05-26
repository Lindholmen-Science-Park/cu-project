import i18n from '../../i18n';
import { sendMessage } from './messaging';
import { beginViewTransition } from './viewTransition';

/** Page `postMessage` payload from `web-plugin` content script (Chrome bridge). */
export const GEO_BRIDGE_POST_SOURCE = 'goteverse-web-plugin' as const;
export const GEO_BRIDGE_POST_TYPE = 'EXPLORE_GEO' as const;

export type GeoTeleportCoords = {
    lat: number;
    lon: number;
    /** WGS84 height in metres (optional; forwarded when set). */
    height?: number;
};

/**
 * Parse ?geo=lat,lon[,height] or ?lat=&lon= (& optional height / altitude) from a URL.
 */
export function peekGeoFromUrl(href: string): GeoTeleportCoords | null {
    let u: URL;
    try {
        u = new URL(href);
    } catch {
        return null;
    }

    const geo = u.searchParams.get('geo');
    if (geo) {
        const parts = geo.split(',').map((s) => s.trim());
        if (parts.length >= 2) {
            const lat = Number(parts[0]);
            const lon = Number(parts[1]);
            const h = parts.length >= 3 ? Number(parts[2]) : NaN;
            if (Number.isFinite(lat) && Number.isFinite(lon)) {
                const out: GeoTeleportCoords = { lat, lon };
                if (Number.isFinite(h)) out.height = h;
                return out;
            }
        }
    }

    // Both required — if only `lat` is present, `Number(null)` would be 0 for lon (false teleport).
    const latS = u.searchParams.get('lat');
    const lonS = u.searchParams.get('lon');
    if (latS != null && lonS != null && latS.trim() !== '' && lonS.trim() !== '') {
        const lat = Number(latS);
        const lon = Number(lonS);
        if (Number.isFinite(lat) && Number.isFinite(lon)) {
            const out: GeoTeleportCoords = { lat, lon };
            const alt = u.searchParams.get('height') ?? u.searchParams.get('altitude');
            if (alt != null && alt !== '') {
                const hv = Number(alt);
                if (Number.isFinite(hv)) out.height = hv;
            }
            return out;
        }
    }

    return null;
}

/**
 * Parse Chrome extension bridge `postMessage` data. Caller must require
 * `event.source === window` so embedded iframes cannot drive teleport.
 */
export function parseExploreGeoBridgePayload(data: unknown): GeoTeleportCoords | null {
    if (data == null || typeof data !== 'object') return null;
    const d = data as Record<string, unknown>;
    if (d.source !== GEO_BRIDGE_POST_SOURCE || d.type !== GEO_BRIDGE_POST_TYPE) return null;
    const lat = typeof d.lat === 'number' ? d.lat : Number(d.lat);
    const lon = typeof d.lon === 'number' ? d.lon : Number(d.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    const out: GeoTeleportCoords = { lat, lon };
    if (d.height != null) {
        const h = typeof d.height === 'number' ? d.height : Number(d.height);
        if (Number.isFinite(h)) out.height = h;
    }
    return out;
}

/** Remove geo-related query keys so refresh does not re-send teleport. */
export function stripGeoQueryParamsFromWindowUrl(): void {
    const u = new URL(window.location.href);
    let changed = false;
    for (const k of ['geo', 'lat', 'lon', 'height', 'altitude']) {
        if (u.searchParams.has(k)) {
            u.searchParams.delete(k);
            changed = true;
        }
    }
    if (!changed) return;
    const next = `${u.pathname}${u.search}${u.hash}`;
    window.history.replaceState(window.history.state, '', next);
}

/**
 * Fade + send geoTeleport to Kit (same UX as POI/seat teleport).
 * Call only when the stream is ready and the scene is usable.
 */
export function beginGeoTeleport(coords: GeoTeleportCoords): void {
    const payload: Record<string, number> = {
        latitude: coords.lat,
        longitude: coords.lon,
    };
    if (coords.height != null && Number.isFinite(coords.height)) {
        payload.height = coords.height;
    }
    console.log('[geoTeleport] spawn request (WGS84 / payload)', { coords, payload });
    beginViewTransition({
        target: 'firstPerson',
        message: i18n.t('streaming.switchingFirstPerson'),
        onFadeOutComplete: () => {
            console.log('[geoTeleport] sending geoTeleport after fade-out', payload);
            try {
                sendMessage('geoTeleport', payload);
            } catch {
                /* stream channel */
            }
        },
    });
}

/**
 * If the data channel is not wired yet, skip (caller should retry when ready).
 */
export function requestGeoTeleportIfReady(streamReady: boolean, coords: GeoTeleportCoords): boolean {
    if (!streamReady) return false;
    beginGeoTeleport(coords);
    return true;
}
