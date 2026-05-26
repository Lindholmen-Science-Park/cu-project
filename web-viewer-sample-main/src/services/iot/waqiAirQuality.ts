import type { IotAirQualityStation } from '../../types/iotAirQuality';
import { gothenburgWaqiBoundsLatLngString } from './gothenburgIotMapBounds';

/**
 * Primary dev source: WAQI map bounds (see https://aqicn.org/api/).
 * Token: repo-root `.env` (Vite `envDir` is parent of `web-viewer-sample-main`).
 * Use `VITE_WAQI_TOKEN` so Vite exposes it to the client (https://vitejs.dev/guide/env-and-mode.html).
 */
export function getWaqiToken(): string {
    const env = (import.meta as any).env || {};
    const a = String(env.VITE_WAQI_TOKEN || '').trim();
    if (a) return a;
    return String(env.VITE_WAQI_API_TOKEN || '').trim();
}

function parseAqi(v: unknown): number {
    if (v === null || v === undefined) return -1;
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    const s = String(v).trim();
    if (s === '' || s === '-') return -1;
    const n = parseInt(s, 10);
    return Number.isFinite(n) ? n : -1;
}

function parsePmNumber(v: unknown): number | undefined {
    if (v === null || v === undefined) return undefined;
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    const s = String(v).trim();
    if (s === '' || s === '-') return undefined;
    const n = parseFloat(s);
    return Number.isFinite(n) ? n : undefined;
}

/** WAQI `iaqi` uses short keys: p2 = PM2.5 µg/m³, p = PM10, pm25 sometimes appears. */
/** WAQI `iaqi.t` — temperature (°C) at measurement context. */
function extractTempCFromIaqi(iaqi: unknown): number | undefined {
    if (!iaqi || typeof iaqi !== 'object') return undefined;
    const o = iaqi as Record<string, { v?: unknown } | unknown>;
    for (const k of ['t', 'T', 'temp']) {
        const slot = o[k];
        if (slot && typeof slot === 'object' && 'v' in (slot as object)) {
            const t = parsePmNumber((slot as { v?: unknown }).v);
            if (t !== undefined) return t;
        }
    }
    return undefined;
}

function extractPm25FromIaqi(iaqi: unknown): number | undefined {
    if (!iaqi || typeof iaqi !== 'object') return undefined;
    const o = iaqi as Record<string, { v?: unknown } | unknown>;
    const keys = ['p2', 'pm25', 'PM25', 'P2'];
    for (const k of keys) {
        const slot = o[k];
        if (slot && typeof slot === 'object' && 'v' in (slot as object)) {
            const p = parsePmNumber((slot as { v?: unknown }).v);
            if (p !== undefined) return p;
        }
    }
    return undefined;
}

function extractPm25FromRow(row: Record<string, unknown>): number | undefined {
    const direct = parsePmNumber(row.pm25) ?? parsePmNumber(row.pm2_5);
    if (direct !== undefined) return direct;
    return extractPm25FromIaqi(row.iaqi);
}

function extractTempCFromRow(row: Record<string, unknown>): number | undefined {
    const direct = parsePmNumber(row.temp) ?? parsePmNumber(row.temperature);
    if (direct !== undefined) return direct;
    return extractTempCFromIaqi(row.iaqi);
}

function delay(ms: number): Promise<void> {
    return new Promise((r) => {
        window.setTimeout(r, ms);
    });
}

/**
 * WAQI map/bounds often omits `iaqi` fields; per-station feed fills PM2.5 and temperature when available.
 */
export async function enrichStationsMissingPm25(
    stations: IotAirQualityStation[],
    token: string,
    signal?: AbortSignal,
    opts?: { maxFeeds?: number; staggerMs?: number },
): Promise<IotAirQualityStation[]> {
    const maxFeeds = opts?.maxFeeds ?? 28;
    const staggerMs = opts?.staggerMs ?? 90;
    const need = stations.filter(
        (s) =>
            /^waqi_\d+$/u.test(s.id) &&
            ((s.pm25 == null || Number.isNaN(s.pm25)) ||
                s.tempC == null ||
                Number.isNaN(s.tempC as number)),
    );
    if (need.length === 0) return stations;

    const uidFromId = (id: string) => (id.startsWith('waqi_') ? id.slice(5) : '');
    const outMap = new Map<string, IotAirQualityStation>(stations.map((s) => [s.id, { ...s }]));

    let done = 0;
    for (const st of need) {
        if (done >= maxFeeds) break;
        if (signal?.aborted) break;
        const uid = uidFromId(st.id);
        if (!uid) continue;
        try {
            const url = `https://api.waqi.info/feed/@${encodeURIComponent(uid)}/?token=${encodeURIComponent(token)}`;
            const res = await fetch(url, { signal });
            if (!res.ok) continue;
            const json = (await res.json()) as {
                status?: string;
                data?: { iaqi?: unknown; time?: { s?: string; iso?: string } };
            };
            if (json?.status !== 'ok' || !json.data) continue;
            const pm = extractPm25FromIaqi(json.data.iaqi);
            const tc = extractTempCFromIaqi(json.data.iaqi);
            const cur = outMap.get(st.id);
            if (!cur) continue;
            if (pm !== undefined) cur.pm25 = pm;
            if (tc !== undefined) cur.tempC = tc;
            const t = json.data.time?.s ?? json.data.time?.iso;
            if (t && !cur.time) cur.time = String(t);
            outMap.set(st.id, cur);
        } catch {
            /* ignore per-station */
        }
        done += 1;
        if (staggerMs > 0) await delay(staggerMs);
    }

    return stations.map((s) => outMap.get(s.id) ?? s);
}

/**
 * Fetches station points inside the Gothenburg bbox from the WAQI v2 map API.
 */
export async function fetchGothenburgStationsFromWaqi(
    token: string,
    signal?: AbortSignal,
): Promise<IotAirQualityStation[]> {
    if (!token) {
        throw new Error('VITE_WAQI_TOKEN is not set');
    }
    const bounds = gothenburgWaqiBoundsLatLngString();
    const url = `https://api.waqi.info/v2/map/bounds/?latlng=${encodeURIComponent(bounds)}&token=${encodeURIComponent(token)}`;
    const res = await fetch(url, { signal });
    if (!res.ok) {
        throw new Error(`WAQI HTTP ${res.status}`);
    }
    const json = await res.json();
    if (json?.status !== 'ok') {
        throw new Error(typeof json?.data === 'string' ? json.data : 'WAQI status not ok');
    }
    const data = Array.isArray(json.data) ? json.data : [];
    const out: IotAirQualityStation[] = [];
    for (const row of data) {
        if (!row || typeof row !== 'object') continue;
        const lat = parseFloat((row as any).lat);
        const lon = parseFloat((row as any).lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
        const uid = (row as any).uid;
        const id = uid != null ? `waqi_${String(uid)}` : `waqi_${lat.toFixed(4)}_${lon.toFixed(4)}`;
        const r = row as Record<string, unknown>;
        const aqi = parseAqi(r.aqi);
        const stName = (r.station as { name?: string } | undefined)?.name;
        const name = typeof stName === 'string' && stName.trim() ? stName : `AQI site ${id}`;
        const st: IotAirQualityStation = { id, name, lat, lon, aqi };
        const pm = extractPm25FromRow(r);
        if (pm !== undefined) st.pm25 = pm;
        const tc = extractTempCFromRow(r);
        if (tc !== undefined) st.tempC = tc;
        const rt = r.time as { s?: string; iso?: string } | undefined;
        if (rt?.s) st.time = String(rt.s);
        else if (rt?.iso) st.time = String(rt.iso);
        out.push(st);
    }
    return out;
}
