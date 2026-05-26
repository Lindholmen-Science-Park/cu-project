import React, { useEffect, useCallback, useMemo, useRef } from 'react';
import { sendMessage } from '../../messaging';
import { useControl } from '../../contexts';
import {
    IOT_OSM_POI_CATEGORY_LABELS,
    IOT_OSM_POI_CATEGORY_ORDER,
    type IotOsmPoiCategory,
    type IotOsmPoiStation,
} from '../../../../types/iotOsmPois';
import { IotPanelLayout } from '../iotShared';
import '../iotAirQuality/IotAirStationsPanel.css';

const L = {
    title: 'OSM places (baked)',
    listAria: 'OSM place list',
    categoryGroup: 'Category',
    coords: 'WGS84',
    placeId: 'OSM id',
    close: 'Close',
    emptyCategory: 'No places in this category in the baked extract.',
    detail: 'Tags',
    hours: 'Opening hours',
    attr: '© OpenStreetMap contributors',
    /** Explains: full POI list is bundled in this app; only a capped subset is sent to Kit for 3D poles (WebRTC JSON size). */
    markersFooter: (totalInCategory: number, cap: number) =>
        totalInCategory > cap
            ? `3D poles in the video stream: up to ${cap} nearest of ${totalInCategory} in this category (WebRTC message size cap for Kit). This list is the full baked set already shipped with the app.`
            : `3D poles in the video stream: all ${totalInCategory} in this category.`,
} as const;

/**
 * WebRTC → Kit custom messages hit a tight size limit (~12kB inner JSON has been observed to truncate).
 * Send only ASCII-safe scalars: no `name` (Swedish / apostrophes / mojibake), no `opening_hours`, no `detail`.
 * Kit labels prims from `id` when `name` is absent. Full strings stay in the web list only.
 */
const MAX_OSM_STATIONS_PER_KIT_MESSAGE = 100;

function stationsForKit(stations: IotOsmPoiStation[]): Record<string, unknown>[] {
    const slice = stations.slice(0, MAX_OSM_STATIONS_PER_KIT_MESSAGE);
    return slice.map((s) => ({
        id: s.id,
        lat: s.lat,
        lon: s.lon,
        category: s.category,
    }));
}

const IotOsmPoisPanel: React.FC = () => {
    const ctrl = useControl();
    const open = ctrl.iotOsmPoisPanelOpen;
    const all = ctrl.iotOsmPoisAll;
    const category = ctrl.iotOsmPoisCategory;
    const setCategory = ctrl.setIotOsmPoisCategory;
    const selectedId = ctrl.iotOsmPoisSelectedStationId;
    const onDismiss = ctrl.dismissIotOsmPoisPanel;

    const filtered = useMemo(() => {
        if (!all?.length) return [];
        return all.filter((p) => p.category === category);
    }, [all, category]);

    const selected = useMemo(() => {
        if (!filtered.length) return null;
        if (selectedId) {
            const s = filtered.find((x) => x.id === selectedId);
            if (s) return s;
        }
        return filtered[0];
    }, [filtered, selectedId]);

    const setSel = ctrl.setIotOsmPoisSelectedStationId;
    const filteredRef = useRef(filtered);
    filteredRef.current = filtered;
    const prevCategoryRef = useRef(category);
    useEffect(() => {
        if (!open) return;
        const list = filteredRef.current;
        if (!list.length) {
            setSel(null);
            return;
        }
        const ok = selectedId && list.some((s) => s.id === selectedId);
        if (!ok) {
            setSel(list[0].id);
        }
    }, [open, category, selectedId, setSel]);

    // Kit must receive station prims before highlight; keep this effect above highlight.
    useEffect(() => {
        if (!open) return;
        sendMessage('iotOsmPoisStations', { stations: stationsForKit(filtered) });
    }, [open, filtered]);

    useEffect(() => {
        if (!open || !filtered.length) {
            return undefined;
        }
        const sid =
            selectedId && filtered.some((s) => s.id === selectedId) ? selectedId : filtered[0].id;
        sendMessage('iotOsmPoisHighlightStation', { id: sid });
        return () => {
            sendMessage('iotOsmPoisHighlightStation', { id: null });
        };
    }, [open, selectedId, filtered]);

    // Match list-row click: pan bird-eye / teleport when switching category so new poles are in view.
    useEffect(() => {
        if (!open || !filtered.length) return;
        if (prevCategoryRef.current === category) return;
        prevCategoryRef.current = category;
        const first = filtered[0];
        sendMessage('iotOsmPoisFocusStation', { lat: first.lat, lon: first.lon });
    }, [open, category, filtered]);

    const handleKey = useCallback(
        (e: KeyboardEvent) => {
            if (e.key === 'Escape') onDismiss();
        },
        [onDismiss],
    );

    useEffect(() => {
        if (!open) return undefined;
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [open, handleKey]);

    if (!open || !all || all.length === 0) return null;

    return (
        <IotPanelLayout open={open} onDismiss={onDismiss} titleId="iot-osm-pois-title">
            <div className="iot-air-stations-header">
                <div>
                    <h2 id="iot-osm-pois-title" className="iot-air-stations-title">
                        {L.title}
                    </h2>
                </div>
                <button type="button" className="iot-air-stations-close" onClick={onDismiss} aria-label={L.close}>
                    ×
                </button>
            </div>

            <div className="iot-air-metric-toggle" role="group" aria-label={L.categoryGroup}>
                {IOT_OSM_POI_CATEGORY_ORDER.map((cat) => (
                    <button
                        key={cat}
                        type="button"
                        aria-pressed={category === cat}
                        onClick={() => {
                            if (cat === category) return;
                            setSel(null);
                            setCategory(cat);
                        }}
                    >
                        {IOT_OSM_POI_CATEGORY_LABELS[cat]}
                    </button>
                ))}
            </div>

            <div className="iot-air-stations-body">
                {filtered.length === 0 ? (
                    <p style={{ padding: '12px 16px', margin: 0, opacity: 0.85 }}>{L.emptyCategory}</p>
                ) : (
                    <ul className="iot-air-stations-list" aria-label={L.listAria}>
                        {filtered.map((s) => {
                            const isSel = selected?.id === s.id;
                            const dist =
                                typeof s.distance_m === 'number' && Number.isFinite(s.distance_m)
                                    ? `${Math.round(s.distance_m)} m`
                                    : '';
                            return (
                                <li key={s.id} className="iot-air-stations-li">
                                    <button
                                        type="button"
                                        className={`iot-air-stations-row ${isSel ? 'iot-air-stations-row--selected' : ''}`}
                                        aria-pressed={isSel}
                                        onClick={() => {
                                            ctrl.setIotOsmPoisSelectedStationId(s.id);
                                            sendMessage('iotOsmPoisFocusStation', { lat: s.lat, lon: s.lon });
                                        }}
                                    >
                                        <span className="iot-air-stations-row-name">{s.name}</span>
                                        <span className="iot-air-stations-row-aqi">{dist}</span>
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                )}

                {selected && filtered.length > 0 ? (
                    <div className="iot-air-stations-detail">
                        <h3 className="iot-air-stations-detail-name">{selected.name}</h3>
                        <dl className="iot-air-stations-dl">
                            <div>
                                <dt>{L.categoryGroup}</dt>
                                <dd>{IOT_OSM_POI_CATEGORY_LABELS[selected.category as IotOsmPoiCategory]}</dd>
                            </div>
                            {selected.detail ? (
                                <div>
                                    <dt>{L.detail}</dt>
                                    <dd className="iot-air-stations-mono">{selected.detail}</dd>
                                </div>
                            ) : null}
                            {selected.opening_hours ? (
                                <div>
                                    <dt>{L.hours}</dt>
                                    <dd>{selected.opening_hours}</dd>
                                </div>
                            ) : null}
                            <div>
                                <dt>{L.coords}</dt>
                                <dd className="iot-air-stations-mono">
                                    {selected.lat.toFixed(5)}, {selected.lon.toFixed(5)}
                                </dd>
                            </div>
                            <div>
                                <dt>{L.placeId}</dt>
                                <dd className="iot-air-stations-mono">{selected.id}</dd>
                            </div>
                        </dl>
                    </div>
                ) : null}
            </div>
            <p
                style={{
                    fontSize: 11,
                    opacity: 0.65,
                    padding: '8px 16px 12px',
                    margin: 0,
                    borderTop: '1px solid rgba(255,255,255,0.08)',
                }}
            >
                {L.markersFooter(filtered.length, MAX_OSM_STATIONS_PER_KIT_MESSAGE)}
                <br />
                {L.attr}
            </p>
        </IotPanelLayout>
    );
};

export default IotOsmPoisPanel;
