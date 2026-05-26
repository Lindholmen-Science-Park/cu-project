/**
 * Göteborg map extent for dev IoT overlays (WGS84).
 * Keep in sync with WAQI map bounds in `waqiAirQuality.ts` (same corners).
 */
export const GOTHENBURG_IOT_MAP_SW = { lat: 57.64, lon: 11.75 } as const;
export const GOTHENBURG_IOT_MAP_NE = { lat: 57.80, lon: 12.12 } as const;

/** `latlng` string for WAQI v2 map/bounds API: south-west then north-east. */
export function gothenburgWaqiBoundsLatLngString(): string {
    const { lat: lat1, lon: lon1 } = GOTHENBURG_IOT_MAP_SW;
    const { lat: lat2, lon: lon2 } = GOTHENBURG_IOT_MAP_NE;
    return `${lat1},${lon1},${lat2},${lon2}`;
}

export interface LatLonBBox {
    minLat: number;
    maxLat: number;
    minLon: number;
    maxLon: number;
}

/** Full WAQI-aligned rectangle (axis-aligned in lat/lon). */
export function gothenburgIotMapBBox(): LatLonBBox {
    const minLat = Math.min(GOTHENBURG_IOT_MAP_SW.lat, GOTHENBURG_IOT_MAP_NE.lat);
    const maxLat = Math.max(GOTHENBURG_IOT_MAP_SW.lat, GOTHENBURG_IOT_MAP_NE.lat);
    const minLon = Math.min(GOTHENBURG_IOT_MAP_SW.lon, GOTHENBURG_IOT_MAP_NE.lon);
    const maxLon = Math.max(GOTHENBURG_IOT_MAP_SW.lon, GOTHENBURG_IOT_MAP_NE.lon);
    return { minLat, maxLat, minLon, maxLon };
}

/**
 * Shrinks the bbox toward its centre by `inset` (0…1) on each half-axis.
 * E.g. inset 0.15 → keep ~85% of lat span and ~85% of lon span (trim outer ~7.5% per side).
 */
export function insetLatLonBBox(box: LatLonBBox, inset: number): LatLonBBox {
    const t = Math.max(0, Math.min(0.45, inset));
    const cLat = (box.minLat + box.maxLat) / 2;
    const cLon = (box.minLon + box.maxLon) / 2;
    const hLat = ((box.maxLat - box.minLat) / 2) * (1 - t);
    const hLon = ((box.maxLon - box.minLon) / 2) * (1 - t);
    return {
        minLat: cLat - hLat,
        maxLat: cLat + hLat,
        minLon: cLon - hLon,
        maxLon: cLon + hLon,
    };
}

/**
 * GBFS dock clip — much smaller than WAQI bounds: stadium / central authored tiles only.
 * Anchor matches `globe-locations.json` gothenburg; trims Mölndal, harbour west, distant suburbs.
 */
export function gothenburgBikeShareClipBBox(): LatLonBBox {
    return {
        minLat: 57.678,
        maxLat: 57.722,
        minLon: 11.964,
        maxLon: 12.015,
    };
}

export function isInsideLatLonBBox(lat: number, lon: number, box: LatLonBBox): boolean {
    return lat >= box.minLat && lat <= box.maxLat && lon >= box.minLon && lon <= box.maxLon;
}
