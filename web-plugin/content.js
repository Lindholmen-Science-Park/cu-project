/**
 * Must match GEO_BRIDGE_POST_SOURCE / GEO_BRIDGE_POST_TYPE in
 * web-viewer-sample-main/src/features/streaming/geoTeleport.ts
 */
const BRIDGE_SOURCE = 'goteverse-web-plugin';
const BRIDGE_TYPE = 'EXPLORE_GEO';

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.type !== 'EXPLORE_GEO') return;
    const lat = typeof msg.lat === 'number' ? msg.lat : Number(msg.lat);
    const lon = typeof msg.lon === 'number' ? msg.lon : Number(msg.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        sendResponse({ ok: false, error: 'invalid_lat_lon' });
        return;
    }
    const payload = {
        source: BRIDGE_SOURCE,
        type: BRIDGE_TYPE,
        lat,
        lon,
    };
    const h = typeof msg.height === 'number' ? msg.height : Number(msg.height);
    if (Number.isFinite(h)) payload.height = h;

    window.postMessage(payload, '*');
    sendResponse({ ok: true });
});
