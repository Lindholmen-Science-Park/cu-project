import type { IotBikeShareStation } from '../../types/iotBikeShare';
import { gothenburgBikeShareClipBBox, isInsideLatLonBBox } from './gothenburgIotMapBounds';

/** Default: Styr & Ställ (nextbike_zg) GBFS root — override with VITE_GBFS_BIKE_URL if the feed moves. */
export const DEFAULT_GBFS_BIKE_ROOT =
    'https://api.nextbike.net/maps/gbfs/v1/nextbike_zg/gbfs.json';

export function getGbfsBikeRootUrl(): string {
    const u = import.meta.env.VITE_GBFS_BIKE_URL;
    if (typeof u === 'string' && u.trim().length > 0) {
        return u.trim();
    }
    return DEFAULT_GBFS_BIKE_ROOT;
}

interface GbfsFeed {
    name: string;
    url: string;
}

interface GbfsRoot {
    data?: Record<string, { feeds?: GbfsFeed[] }>;
}

interface StationInformation {
    station_id: string;
    name?: string;
    lat?: number;
    lon?: number;
    /** GBFS optional; nextbike_zg often omits it. */
    capacity?: number;
}

interface StationInformationResponse {
    data?: { stations?: StationInformation[] };
}

interface StationStatus {
    station_id: string;
    num_bikes_available?: number;
    num_docks_available?: number;
}

interface StationStatusResponse {
    data?: { stations?: StationStatus[] };
}

function pickFeeds(root: GbfsRoot): GbfsFeed[] | null {
    const d = root?.data;
    if (!d || typeof d !== 'object') return null;
    const en = d.en?.feeds;
    if (Array.isArray(en) && en.length) return en;
    const sv = d.sv?.feeds;
    if (Array.isArray(sv) && sv.length) return sv;
    const first = Object.values(d).find((v) => Array.isArray(v?.feeds) && v.feeds!.length);
    return first?.feeds ?? null;
}

function feedUrl(feeds: GbfsFeed[], name: string): string | null {
    const f = feeds.find((x) => x.name === name);
    return f?.url && typeof f.url === 'string' ? f.url : null;
}

function parseStationCapacity(s: StationInformation): number | undefined {
    const c = s.capacity;
    if (typeof c === 'number' && Number.isFinite(c) && c > 0) {
        return Math.floor(c);
    }
    return undefined;
}

/**
 * Fetch dock list + availability for Göteborg Styr & Ställ (nextbike_zg GBFS).
 */
export async function fetchGothenburgBikeShareStations(
    signal?: AbortSignal,
    rootUrl: string = getGbfsBikeRootUrl(),
): Promise<IotBikeShareStation[]> {
    const rootRes = await fetch(rootUrl, { signal });
    if (!rootRes.ok) {
        throw new Error(`GBFS root HTTP ${rootRes.status}`);
    }
    const rootJson = (await rootRes.json()) as GbfsRoot;
    const feeds = pickFeeds(rootJson);
    if (!feeds?.length) {
        throw new Error('GBFS root: no language feeds');
    }
    const infoUrl = feedUrl(feeds, 'station_information');
    const statusUrl = feedUrl(feeds, 'station_status');
    if (!infoUrl || !statusUrl) {
        throw new Error('GBFS root: missing station_information or station_status');
    }

    const [infoRes, statusRes] = await Promise.all([
        fetch(infoUrl, { signal }),
        fetch(statusUrl, { signal }),
    ]);
    if (!infoRes.ok) {
        throw new Error(`station_information HTTP ${infoRes.status}`);
    }
    if (!statusRes.ok) {
        throw new Error(`station_status HTTP ${statusRes.status}`);
    }

    const infoJson = (await infoRes.json()) as StationInformationResponse;
    const statusJson = (await statusRes.json()) as StationStatusResponse;

    const stations = infoJson?.data?.stations;
    if (!Array.isArray(stations) || !stations.length) {
        return [];
    }

    const statusById = new Map<string, StationStatus>();
    for (const s of statusJson?.data?.stations ?? []) {
        if (s?.station_id) {
            statusById.set(String(s.station_id), s);
        }
    }

    const clipBox = gothenburgBikeShareClipBBox();

    const out: IotBikeShareStation[] = [];
    for (const s of stations) {
        if (!s?.station_id) continue;
        const lat = typeof s.lat === 'number' ? s.lat : Number(s.lat);
        const lon = typeof s.lon === 'number' ? s.lon : Number(s.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
        if (!isInsideLatLonBBox(lat, lon, clipBox)) {
            continue;
        }

        const st = statusById.get(String(s.station_id));
        const bikes = Math.max(0, Math.floor(Number(st?.num_bikes_available ?? 0)));
        const apiDocks = Math.max(0, Math.floor(Number(st?.num_docks_available ?? 0)));
        const cap = parseStationCapacity(s);
        let docks = apiDocks;
        if (docks === 0 && cap != null && cap >= bikes) {
            docks = Math.max(0, cap - bikes);
        }

        out.push({
            id: `gbfs_${s.station_id}`,
            lat,
            lon,
            name: typeof s.name === 'string' && s.name.trim() ? s.name.trim() : `Station ${s.station_id}`,
            bikesAvailable: bikes,
            docksAvailable: docks,
        });
    }

    out.sort((a, b) => a.name.localeCompare(b.name, 'sv'));
    return out;
}
