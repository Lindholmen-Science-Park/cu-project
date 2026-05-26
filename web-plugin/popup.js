/** Base URL of the streaming web app (no trailing slash). */
const VIEWER_ORIGIN = 'http://localhost:5173';

function setStatus(text, cls) {
    const el = document.getElementById('status');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'status' + (cls ? ` ${cls}` : '');
}

function readCoords() {
    const lat = Number(String(document.getElementById('lat').value).replace(',', '.').trim());
    const lon = Number(String(document.getElementById('lon').value).replace(',', '.').trim());
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    return { lat, lon };
}

async function findViewerTab() {
    const pattern = `${VIEWER_ORIGIN}/*`;
    const tabs = await chrome.tabs.query({ url: [pattern] });
    if (tabs && tabs.length > 0) return tabs[0];
    return null;
}

document.getElementById('explore').addEventListener('click', async () => {
    setStatus('');
    const coords = readCoords();
    if (!coords) {
        setStatus('Enter valid latitude and longitude.', 'err');
        return;
    }

    const tab = await findViewerTab();
    if (tab && tab.id != null) {
        try {
            await chrome.tabs.update(tab.id, { active: true });
            await chrome.tabs.sendMessage(tab.id, {
                type: 'EXPLORE_GEO',
                lat: coords.lat,
                lon: coords.lon,
            });
            setStatus('Sent to viewer tab (no reload).', 'ok');
        } catch (e) {
            setStatus(`Could not message viewer: ${e?.message || e}. Open ${VIEWER_ORIGIN} once, then retry.`, 'err');
        }
        return;
    }

    const geo = `${coords.lat},${coords.lon}`;
    const url = `${VIEWER_ORIGIN}/?geo=${encodeURIComponent(geo)}`;
    await chrome.tabs.create({ url });
    setStatus('Opened new viewer tab with ?geo=…', 'ok');
});

chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const t = tabs && tabs[0];
    if (!t || !t.url) return;
    const parsed = typeof parseUrlToGeo === 'function' ? parseUrlToGeo(t.url) : null;
    if (parsed) {
        document.getElementById('lat').value = String(parsed.lat);
        document.getElementById('lon').value = String(parsed.lon);
        setStatus('All systems functional. Ready to explore!', 'ok');
    }
});
