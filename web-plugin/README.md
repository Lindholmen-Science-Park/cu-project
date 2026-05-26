# Goteverse — Explore in 3D (Chrome, dev)

Unpacked Manifest V3 extension: read coordinates from Google Maps / OpenStreetMap (URL parsing) or manual entry, then either message an open **Vite** viewer tab or open `?geo=lat,lon`.

## Prerequisites

1. `web-viewer-sample-main` dev server on `http://localhost:5173` (or change `VIEWER_ORIGIN` in `popup.js` and matching `host_permissions` + `content_scripts.matches` in `manifest.json`).
2. Kit streaming session connected from that viewer (same as normal `startstream.bat` workflow).

## Load the extension

1. Chrome → **Extensions** → enable **Developer mode**.
2. **Load unpacked** → select this folder `web-plugin/`.
3. Pin the extension if you want quick access to the popup.

## Use

1. Open a map tab (e.g. Google Maps with `@lat,lon` in the URL, or OSM `#map=zoom/lat/lon`).
2. Open the Goteverse viewer tab and wait until the stream is ready.
3. Click the extension icon → **Explore in 3D**.

If no viewer tab matches `VIEWER_ORIGIN`, a new tab opens with `?geo=…` (cold start).

## Bridge contract

The content script posts to `window` with `source: "goteverse-web-plugin"` and `type: "EXPLORE_GEO"`. The React app validates `event.source === window` and the same `source` / `type` strings — see `web-viewer-sample-main/src/features/streaming/geoTeleport.ts`.
