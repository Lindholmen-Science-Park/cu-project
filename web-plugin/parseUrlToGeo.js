/**
 * Best-effort lat/lon from common map URLs. Prefer URL over DOM scraping.
 * @param {string} url
 * @returns {{ lat: number, lon: number } | null}
 */
function parseUrlToGeo(url) {
    let u;
    try {
        u = new URL(url);
    } catch {
        return null;
    }
    const host = (u.hostname || '').toLowerCase();

    // OpenStreetMap: /#map=zoom/lat/lon
    if (host.includes('openstreetmap.org')) {
        const hash = u.hash || '';
        const m = hash.match(/[#&]map=\d+\/(-?\d+\.?\d*)\/(-?\d+\.?\d*)/);
        if (m) {
            const lat = Number(m[1]);
            const lon = Number(m[2]);
            if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon };
        }
        const mlat = u.searchParams.get('mlat');
        const mlon = u.searchParams.get('mlon');
        if (mlat != null && mlon != null) {
            const lat = Number(mlat);
            const lon = Number(mlon);
            if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon };
        }
    }

    // Google Maps / google.com/maps
    if (host.includes('google')) {
        const path = u.pathname + u.search + u.hash;
        const at = path.match(/@(-?\d+\.?\d*),(-?\d+\.?\d*)(?:,|\/|\?|&|$)/);
        if (at) {
            const lat = Number(at[1]);
            const lon = Number(at[2]);
            if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon };
        }
        const ll = u.searchParams.get('ll');
        if (ll) {
            const parts = ll.split(',').map((s) => s.trim());
            if (parts.length >= 2) {
                const lat = Number(parts[0]);
                const lon = Number(parts[1]);
                if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon };
            }
        }
        const q = u.searchParams.get('q');
        if (q && /^-?\d+\.?\d*\s*,\s*-?\d+\.?\d*$/.test(q.trim())) {
            const parts = q.split(',').map((s) => s.trim());
            const lat = Number(parts[0]);
            const lon = Number(parts[1]);
            if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon };
        }
    }

    return null;
}
