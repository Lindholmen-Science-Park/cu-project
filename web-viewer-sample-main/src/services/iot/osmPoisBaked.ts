import type { IotOsmPoiStation } from '../../types/iotOsmPois';

interface OsmPoisPayload {
    meta?: Record<string, unknown>;
    pois: IotOsmPoiStation[];
}

// Bundled via Vite; path is repo-relative to web-viewer-sample-main/src/services/iot
import raw from '../../../../kit-app-template-main/source/data/osm/osm_pois_gbg.json';

const payload = raw as OsmPoisPayload;

export function getBakedOsmPois(): IotOsmPoiStation[] {
    const list = payload.pois;
    return Array.isArray(list) ? list : [];
}
