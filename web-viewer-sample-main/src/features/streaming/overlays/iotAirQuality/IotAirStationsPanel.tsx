import React, { useEffect, useCallback, useMemo, useRef, useState } from 'react';
import { sendMessage } from '../../messaging';
import { useControl } from '../../contexts';
import IotAqiEducational from './IotAqiEducational';
import IotTempEducational from './IotTempEducational';
import { IotPanelLayout } from '../iotShared';
import './IotAirStationsPanel.css';

/** Dev-only panel: English copy (not in customer i18n). */
const L = {
    title: 'Air quality stations',
    listAria: 'Air quality station list',
    metricGroup: 'Values shown in list and scale',
    metricAqi: 'AQI',
    metricTemp: 'Temperature',
    na: 'n/a',
    aqi: 'AQI (US)',
    temp: 'Temperature (°C)',
    pm25: 'PM2.5 (µg/m³)',
    time: 'Observation time',
    coords: 'WGS84',
    stationId: 'Station ID',
    close: 'Close',
} as const;

type DetailMetric = 'aqi' | 'temp';

const IotAirStationsPanel: React.FC = () => {
    const [detailMetric, setDetailMetric] = useState<DetailMetric>('aqi');
    const ctrl = useControl();
    const open = ctrl.iotAirStationsPanelOpen;
    const stations = ctrl.iotAirStations;
    const selectedId = ctrl.iotAirSelectedStationId;
    const onDismiss = ctrl.dismissIotAirStationsPanel;

    const selected = useMemo(() => {
        if (!stations?.length) return null;
        if (selectedId) {
            const s = stations.find((x) => x.id === selectedId);
            if (s) return s;
        }
        return stations[0];
    }, [stations, selectedId]);

    const setSel = ctrl.setIotAirSelectedStationId;
    const stationsRef = useRef(stations);
    stationsRef.current = stations;
    useEffect(() => {
        if (!open) return;
        const list = stationsRef.current;
        if (!list?.length) return;
        const ok = selectedId && list.some((s) => s.id === selectedId);
        if (!ok) {
            setSel(list[0].id);
        }
    }, [open, selectedId, setSel]);

    /** Kit receives prims before highlight (same ordering as OSM — avoids stale highlight on WebRTC). */
    useEffect(() => {
        if (!open || !stations?.length) return;
        sendMessage('iotAirQualityStations', { stations });
    }, [open, stations]);

    useEffect(() => {
        if (!open || !stations?.length) return undefined;
        const sid = selectedId && stations.some((s) => s.id === selectedId) ? selectedId : stations[0].id;
        sendMessage('iotAirQualityHighlightStation', { id: sid });
        return () => {
            sendMessage('iotAirQualityHighlightStation', { id: null });
        };
    }, [open, selectedId, stations]);

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

    if (!open || !stations || stations.length === 0) return null;

    return (
        <IotPanelLayout open={open} onDismiss={onDismiss} titleId="iot-air-stations-title">
            <div className="iot-air-stations-header">
                <div>
                    <h2 id="iot-air-stations-title" className="iot-air-stations-title">
                        {L.title}
                    </h2>
                </div>
                <button type="button" className="iot-air-stations-close" onClick={onDismiss} aria-label={L.close}>
                    ×
                </button>
            </div>

            <div className="iot-air-metric-toggle" role="group" aria-label={L.metricGroup}>
                <button type="button" aria-pressed={detailMetric === 'aqi'} onClick={() => setDetailMetric('aqi')}>
                    {L.metricAqi}
                </button>
                <button type="button" aria-pressed={detailMetric === 'temp'} onClick={() => setDetailMetric('temp')}>
                    {L.metricTemp}
                </button>
            </div>

            <div className="iot-air-stations-body">
                <ul className="iot-air-stations-list" aria-label={L.listAria}>
                    {stations.map((s) => {
                        const isSel = selected?.id === s.id;
                        const aqi =
                            typeof s.aqi === 'number' && s.aqi >= 0 ? String(Math.round(s.aqi)) : L.na;
                        const tC = s.tempC;
                        const hasTemp = typeof tC === 'number' && Number.isFinite(tC);
                        const tempStr = hasTemp ? `${tC.toFixed(1)} °C` : L.na;
                        const rightLabel = detailMetric === 'aqi' ? `AQI ${aqi}` : tempStr;
                        return (
                            <li key={s.id} className="iot-air-stations-li">
                                <button
                                    type="button"
                                    className={`iot-air-stations-row ${isSel ? 'iot-air-stations-row--selected' : ''}`}
                                    aria-pressed={isSel}
                                    onClick={() => {
                                        ctrl.setIotAirSelectedStationId(s.id);
                                        sendMessage('iotAirQualityFocusStation', { lat: s.lat, lon: s.lon });
                                    }}
                                >
                                    <span className="iot-air-stations-row-name">{s.name}</span>
                                    <span className="iot-air-stations-row-aqi">{rightLabel}</span>
                                </button>
                            </li>
                        );
                    })}
                </ul>

                {selected ? (
                    <div className="iot-air-stations-detail">
                        <h3 className="iot-air-stations-detail-name">{selected.name}</h3>
                        {detailMetric === 'aqi' ? (
                            <IotAqiEducational aqi={selected.aqi} />
                        ) : (
                            <IotTempEducational tempC={selected.tempC} />
                        )}
                        <dl className="iot-air-stations-dl">
                            {detailMetric === 'temp' ? (
                                <div>
                                    <dt>{L.temp}</dt>
                                    <dd>
                                        {selected.tempC != null &&
                                        typeof selected.tempC === 'number' &&
                                        Number.isFinite(selected.tempC)
                                            ? selected.tempC.toFixed(1)
                                            : L.na}
                                    </dd>
                                </div>
                            ) : null}
                            <div>
                                <dt>{L.aqi}</dt>
                                <dd>
                                    {typeof selected.aqi === 'number' && selected.aqi >= 0
                                        ? String(Math.round(selected.aqi))
                                        : L.na}
                                </dd>
                            </div>
                            {detailMetric === 'aqi' ? (
                                <div>
                                    <dt>{L.temp}</dt>
                                    <dd>
                                        {selected.tempC != null &&
                                        typeof selected.tempC === 'number' &&
                                        Number.isFinite(selected.tempC)
                                            ? selected.tempC.toFixed(1)
                                            : L.na}
                                    </dd>
                                </div>
                            ) : null}
                            <div>
                                <dt>{L.pm25}</dt>
                                <dd>
                                    {selected.pm25 != null && !Number.isNaN(selected.pm25)
                                        ? selected.pm25.toFixed(1)
                                        : L.na}
                                </dd>
                            </div>
                            {selected.time ? (
                                <div>
                                    <dt>{L.time}</dt>
                                    <dd>{selected.time}</dd>
                                </div>
                            ) : null}
                            <div>
                                <dt>{L.coords}</dt>
                                <dd className="iot-air-stations-mono">
                                    {selected.lat.toFixed(5)}, {selected.lon.toFixed(5)}
                                </dd>
                            </div>
                            <div>
                                <dt>{L.stationId}</dt>
                                <dd className="iot-air-stations-mono">{selected.id}</dd>
                            </div>
                        </dl>
                    </div>
                ) : null}
            </div>
        </IotPanelLayout>
    );
};

export default IotAirStationsPanel;
