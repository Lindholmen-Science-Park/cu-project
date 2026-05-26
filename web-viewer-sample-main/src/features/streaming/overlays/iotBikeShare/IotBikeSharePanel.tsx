import React, { useEffect, useCallback, useMemo, useRef } from 'react';
import { sendMessage } from '../../messaging';
import { useControl } from '../../contexts';
import { IotPanelLayout } from '../iotShared';
import '../iotAirQuality/IotAirStationsPanel.css';

/** Dev-only panel: English copy (not in customer i18n). */
const L = {
    title: 'Bike share (Styr & Ställ)',
    listAria: 'Bike dock list',
    bikes: 'Bikes available',
    coords: 'WGS84',
    stationId: 'Station ID',
    close: 'Close',
} as const;

const IotBikeSharePanel: React.FC = () => {
    const ctrl = useControl();
    const open = ctrl.iotBikeSharePanelOpen;
    const stations = ctrl.iotBikeShareStations;
    const selectedId = ctrl.iotBikeShareSelectedStationId;
    const onDismiss = ctrl.dismissIotBikeSharePanel;

    const selected = useMemo(() => {
        if (!stations?.length) return null;
        if (selectedId) {
            const s = stations.find((x) => x.id === selectedId);
            if (s) return s;
        }
        return stations[0];
    }, [stations, selectedId]);

    const setSel = ctrl.setIotBikeShareSelectedStationId;
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

    useEffect(() => {
        if (!open || !stations?.length) return;
        sendMessage('iotBikeShareStations', { stations });
    }, [open, stations]);

    useEffect(() => {
        if (!open || !stations?.length) return undefined;
        const sid = selectedId && stations.some((s) => s.id === selectedId) ? selectedId : stations[0].id;
        sendMessage('iotBikeShareHighlightStation', { id: sid });
        return () => {
            sendMessage('iotBikeShareHighlightStation', { id: null });
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
        <IotPanelLayout open={open} onDismiss={onDismiss} titleId="iot-bike-share-title">
            <div className="iot-air-stations-header">
                <div>
                    <h2 id="iot-bike-share-title" className="iot-air-stations-title">
                        {L.title}
                    </h2>
                </div>
                <button type="button" className="iot-air-stations-close" onClick={onDismiss} aria-label={L.close}>
                    ×
                </button>
            </div>

            <div className="iot-air-stations-body">
                <ul className="iot-air-stations-list" aria-label={L.listAria}>
                    {stations.map((s) => {
                        const isSel = selected?.id === s.id;
                        const right = `${s.bikesAvailable} bikes`;
                        return (
                            <li key={s.id} className="iot-air-stations-li">
                                <button
                                    type="button"
                                    className={`iot-air-stations-row ${isSel ? 'iot-air-stations-row--selected' : ''}`}
                                    aria-pressed={isSel}
                                    onClick={() => {
                                        ctrl.setIotBikeShareSelectedStationId(s.id);
                                        sendMessage('iotBikeShareFocusStation', { lat: s.lat, lon: s.lon });
                                    }}
                                >
                                    <span className="iot-air-stations-row-name">{s.name}</span>
                                    <span className="iot-air-stations-row-aqi">{right}</span>
                                </button>
                            </li>
                        );
                    })}
                </ul>

                {selected ? (
                    <div className="iot-air-stations-detail">
                        <h3 className="iot-air-stations-detail-name">{selected.name}</h3>
                        <dl className="iot-air-stations-dl">
                            <div>
                                <dt>{L.bikes}</dt>
                                <dd>{selected.bikesAvailable}</dd>
                            </div>
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

export default IotBikeSharePanel;
