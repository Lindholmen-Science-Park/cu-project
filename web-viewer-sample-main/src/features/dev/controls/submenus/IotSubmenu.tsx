import React, { useState, useCallback } from 'react';
import { useControl } from '../../../streaming/contexts';
import TransitLiveDevSection from './TransitLiveDevSection';
import {
    fetchGothenburgStationsFromWaqi,
    getWaqiToken,
    enrichStationsMissingPm25,
} from '../../../../services/iot/waqiAirQuality';
import { fetchGothenburgBikeShareStations } from '../../../../services/iot/styrStallGbfs';
import { getBakedOsmPois } from '../../../../services/iot/osmPoisBaked';
import { IOT_OSM_POI_CATEGORY_ORDER, type IotOsmPoiStation } from '../../../../types/iotOsmPois';

interface Props {
    closeMenu: () => void;
}

/**
 * Single IoT drawer shared by the three open-data features (all backed by
 * `younite.open_data_live_extension` services in Kit: air quality, bike share,
 * live transit).
 *
 * Each feature follows the same shape: a primary action button (Refresh / Toggle),
 * then (when data exists) an "Open list" entry-point. Selecting an item in the
 * resulting overlay panel pans the bird-eye camera to that location and shows
 * its details. Panels:
 * - AIQ → `IotAirStationsPanel`
 * - Bike → `IotBikeSharePanel`
 * - Transit → `IotTransitLivePanel` (rendered from `SharedOverlayLayer`,
 *   mounted/state lives in `useControlHandlers`)
 * - OSM → `IotOsmPoisPanel` (baked JSON from `export_osm_pois.py`)
 */
function firstCategoryWithData(list: IotOsmPoiStation[]) {
    for (const cat of IOT_OSM_POI_CATEGORY_ORDER) {
        if (list.some((p) => p.category === cat)) return cat;
    }
    return IOT_OSM_POI_CATEGORY_ORDER[0];
}

const IotSubmenu: React.FC<Props> = ({ closeMenu }) => {
    const ctrl = useControl();

    // Air quality
    const stations = ctrl.iotAirStations;
    const stationCount = stations?.length ?? 0;
    const [airLoading, setAirLoading] = useState(false);
    const [airError, setAirError] = useState<string | null>(null);

    // Bike share
    const bikeStations = ctrl.iotBikeShareStations;
    const bikeCount = bikeStations?.length ?? 0;
    const [bikeLoading, setBikeLoading] = useState(false);
    const [bikeError, setBikeError] = useState<string | null>(null);

    const osmAll = ctrl.iotOsmPoisAll;
    const osmCount = osmAll?.length ?? 0;
    const [osmError, setOsmError] = useState<string | null>(null);

    const openAirPanel = useCallback(() => {
        if (!stations?.length) return;
        ctrl.setIotAirStationsPanelOpen(true);
        const sid = ctrl.iotAirSelectedStationId;
        if (!sid || !stations.some((s) => s.id === sid)) {
            ctrl.setIotAirSelectedStationId(stations[0].id);
        }
    }, [ctrl, stations]);

    const openBikePanel = useCallback(() => {
        if (!bikeStations?.length) return;
        ctrl.setIotBikeSharePanelOpen(true);
        const sid = ctrl.iotBikeShareSelectedStationId;
        if (!sid || !bikeStations.some((s) => s.id === sid)) {
            ctrl.setIotBikeShareSelectedStationId(bikeStations[0].id);
        }
    }, [ctrl, bikeStations]);

    const onFetchWaqi = useCallback(async () => {
        setAirLoading(true);
        setAirError(null);
        try {
            const token = getWaqiToken();
            if (!token) {
                setAirError(
                    'Set VITE_WAQI_TOKEN in the repo-root .env (folder with startstream.bat), then restart Vite — see .env.example',
                );
                setAirLoading(false);
                return;
            }
            const ac = new AbortController();
            const timeoutHandle = window.setTimeout(() => ac.abort(), 45000);
            let list = await fetchGothenburgStationsFromWaqi(token, ac.signal);
            list = await enrichStationsMissingPm25(list, token, ac.signal, { maxFeeds: 28, staggerMs: 85 });
            window.clearTimeout(timeoutHandle);
            ctrl.setIotAirStations(list);
            if (list.length > 0) {
                ctrl.setIotAirSelectedStationId(list[0].id);
                ctrl.setIotAirStationsPanelOpen(true);
                closeMenu();
            }
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : String(e);
            setAirError(msg);
        } finally {
            setAirLoading(false);
        }
    }, [closeMenu, ctrl]);

    const openOsmPoisPanel = useCallback(() => {
        setOsmError(null);
        let list = ctrl.iotOsmPoisAll;
        if (!list?.length) {
            try {
                list = getBakedOsmPois();
            } catch (e: unknown) {
                const msg = e instanceof Error ? e.message : String(e);
                setOsmError(msg);
                return;
            }
            if (!list.length) {
                setOsmError('No POIs in osm_pois_gbg.json — run export_osm_pois.py in kit source/data/osm.');
                return;
            }
            ctrl.setIotOsmPoisAll(list);
        }
        const cat = firstCategoryWithData(list);
        ctrl.setIotOsmPoisCategory(cat);
        const first = list.find((p) => p.category === cat) ?? list[0];
        ctrl.setIotOsmPoisSelectedStationId(first.id);
        ctrl.setIotOsmPoisPanelOpen(true);
        closeMenu();
    }, [closeMenu, ctrl]);

    const onFetchBikeGbfs = useCallback(async () => {
        setBikeLoading(true);
        setBikeError(null);
        try {
            const ac = new AbortController();
            const timeoutHandle = window.setTimeout(() => ac.abort(), 60000);
            const list = await fetchGothenburgBikeShareStations(ac.signal);
            window.clearTimeout(timeoutHandle);
            ctrl.setIotBikeShareStations(list);
            if (list.length > 0) {
                ctrl.setIotBikeShareSelectedStationId(list[0].id);
                ctrl.setIotBikeSharePanelOpen(true);
                closeMenu();
            }
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : String(e);
            setBikeError(msg);
        } finally {
            setBikeLoading(false);
        }
    }, [closeMenu, ctrl]);

    return (
        <div className="controls-submenu">
            <button type="button" className="controls-submenu-back" onClick={() => closeMenu()}>‹ Back</button>
            <h3 className="controls-menu-title">IoT / open data</h3>

            <h4 className="controls-subtitle" style={{ marginTop: 6 }}>Air quality (WAQI)</h4>
            <div className="controls-menu-buttons">
                <button
                    type="button"
                    className="controls-menu-button"
                    onClick={() => { void onFetchWaqi(); }}
                    disabled={airLoading}
                >
                    <div className="controls-button-icon">{airLoading ? '⏳' : '🌡️'}</div>
                    <span>{airLoading ? 'Fetching…' : 'Refresh stations (Göteborg)'}</span>
                </button>
                {stationCount > 0 && (
                    <button type="button" className="controls-menu-button" onClick={() => { openAirPanel(); closeMenu(); }}>
                        <div className="controls-button-icon">📋</div>
                        <span>Open stations list</span>
                    </button>
                )}
            </div>
            {airError && (
                <p className="controls-iot-err" style={{ fontSize: 12, color: '#f88', marginTop: 6 }} role="alert">
                    {airError}
                </p>
            )}

            <h4 className="controls-subtitle" style={{ marginTop: 14 }}>Bike share (Styr & Ställ)</h4>
            <div className="controls-menu-buttons">
                <button
                    type="button"
                    className="controls-menu-button"
                    onClick={() => { void onFetchBikeGbfs(); }}
                    disabled={bikeLoading}
                >
                    <div className="controls-button-icon">{bikeLoading ? '⏳' : '🚲'}</div>
                    <span>{bikeLoading ? 'Fetching…' : 'Refresh docks (Göteborg)'}</span>
                </button>
                {bikeCount > 0 && (
                    <button type="button" className="controls-menu-button" onClick={() => { openBikePanel(); closeMenu(); }}>
                        <div className="controls-button-icon">📋</div>
                        <span>Open docks list</span>
                    </button>
                )}
            </div>
            {bikeError && (
                <p className="controls-iot-err" style={{ fontSize: 12, color: '#f88', marginTop: 6 }} role="alert">
                    {bikeError}
                </p>
            )}

            <h4 className="controls-subtitle" style={{ marginTop: 14 }}>OSM places (baked)</h4>
            <p style={{ fontSize: 11, opacity: 0.75, margin: '4px 0 8px' }}>
                Static extract from OpenStreetMap — re-run{' '}
                <code style={{ fontSize: 10 }}>export_osm_pois.py</code> in{' '}
                <code style={{ fontSize: 10 }}>kit-app-template-main/source/data/osm</code> to refresh.
            </p>
            <div className="controls-menu-buttons">
                <button type="button" className="controls-menu-button" onClick={() => { openOsmPoisPanel(); }}>
                    <div className="controls-button-icon">🗺️</div>
                    <span>{osmCount > 0 ? 'Open places list' : 'Load places list'}</span>
                </button>
            </div>
            {osmError && (
                <p className="controls-iot-err" style={{ fontSize: 12, color: '#f88', marginTop: 6 }} role="alert">
                    {osmError}
                </p>
            )}

            <TransitLiveDevSection closeMenu={closeMenu} />
        </div>
    );
};

export default IotSubmenu;
