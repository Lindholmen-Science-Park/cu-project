import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { sendMessage } from '../../messaging';
import { useControl, useEnvironment } from '../../contexts';
import type { TransitLiveOverlayVehicleRow } from '../../types';
import { IotPanelLayout } from '../iotShared';
import '../iotAirQuality/IotAirStationsPanel.css';

/** Dev-only panel: English copy (not in customer i18n). */
const L = {
    title: 'Live transit (Västtrafik)',
    listAria: 'Live transit vehicle list',
    line: 'Line',
    kind: 'Vehicle type',
    journey: 'Journey',
    direction: 'Direction',
    state: 'State',
    delay: 'Delay (min)',
    speed: 'Speed (m/s)',
    bearing: 'Bearing (°)',
    coords: 'WGS84',
    sceneXyz: 'Scene XYZ (cm)',
    feedToken: 'Feed token',
    licensePlate: 'License plate',
    tripId: 'Trip ID',
    close: 'Close',
    empty: 'No vehicles in the latest snapshot.',
    birdEyeHint: 'Tap a row to pan the bird-eye view to that vehicle.',
    needBirdEye: "Switch to bird's-eye view to use camera focus from this list.",
    na: 'n/a',
} as const;

function vehicleKind(row: TransitLiveOverlayVehicleRow): string {
    return row.isTram === true ? 'Tram' : 'Bus';
}

function vehicleLine(row: TransitLiveOverlayVehicleRow): string {
    const v =
        (typeof row.routeId === 'string' && row.routeId.trim()) ||
        (typeof row.line === 'string' && row.line.trim()) ||
        '';
    return v || L.na;
}

function vehiclePrimaryLabel(row: TransitLiveOverlayVehicleRow): string {
    const line = vehicleLine(row);
    return line === L.na ? vehicleKind(row) : `${vehicleKind(row)} · line ${line}`;
}

function vehicleSecondaryLabel(row: TransitLiveOverlayVehicleRow): string {
    const j =
        (typeof row.journeyName === 'string' && row.journeyName.trim()) ||
        (typeof row.tripId === 'string' && row.tripId.trim()) ||
        '';
    if (j) return j.length > 56 ? `${j.slice(0, 54)}…` : j;
    if (typeof row.lat === 'number' && typeof row.lon === 'number') {
        return `${row.lat.toFixed(4)}°, ${row.lon.toFixed(4)}°`;
    }
    return row.token ? `Scene id ${row.token}` : '';
}

const IotTransitLivePanel: React.FC = () => {
    const ctrl = useControl();
    const env = useEnvironment();
    const open = ctrl.iotTransitLivePanelOpen;
    const status = ctrl.transitLiveOverlayStatus;
    const vehicles = useMemo<TransitLiveOverlayVehicleRow[]>(
        () => status?.vehicles ?? [],
        [status?.vehicles],
    );
    const selectedToken = ctrl.iotTransitLiveSelectedVehicleToken;
    const setSel = ctrl.setIotTransitLiveSelectedVehicleToken;
    const onDismiss = ctrl.dismissIotTransitLivePanel;
    const birdEyeActive = env.currentCamera === 'bird_eye';

    const selected = useMemo<TransitLiveOverlayVehicleRow | null>(() => {
        if (!vehicles.length) return null;
        if (selectedToken) {
            const v = vehicles.find((row) => row.token === selectedToken);
            if (v) return v;
        }
        return vehicles[0];
    }, [vehicles, selectedToken]);

    const vehiclesRef = useRef(vehicles);
    vehiclesRef.current = vehicles;
    useEffect(() => {
        if (!open) return;
        const list = vehiclesRef.current;
        if (!list.length) return;
        const ok = selectedToken && list.some((v) => v.token === selectedToken);
        if (!ok) {
            setSel(list[0].token);
        }
    }, [open, selectedToken, setSel]);

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

    const focusVehicle = useCallback(
        (row: TransitLiveOverlayVehicleRow) => {
            setSel(row.token);
            if (!birdEyeActive) return;
            const [x, y, z] = row.sceneXyzCm ?? [];
            if (![x, y, z].every((n) => typeof n === 'number' && Number.isFinite(n))) return;
            try {
                sendMessage('birdEyeRouteClear', {});
            } catch {
                /* ignore */
            }
            try {
                sendMessage('birdEyePanFocusWorld', { worldPos: [x, y, z] });
            } catch {
                /* ignore */
            }
        },
        [birdEyeActive, setSel],
    );

    if (!open) return null;

    return (
        <IotPanelLayout open={open} onDismiss={onDismiss} titleId="iot-transit-live-title">
            <div className="iot-air-stations-header">
                <div>
                    <h2 id="iot-transit-live-title" className="iot-air-stations-title">
                        {L.title}
                    </h2>
                </div>
                <button type="button" className="iot-air-stations-close" onClick={onDismiss} aria-label={L.close}>
                    ×
                </button>
            </div>

            {vehicles.length === 0 ? (
                <p className="controls-iot-hint" style={{ fontSize: 13, opacity: 0.85, margin: '8px 0 0' }}>
                    {L.empty}
                </p>
            ) : (
                <>
                    <p className="controls-iot-hint" style={{ fontSize: 12, opacity: 0.85, margin: '4px 0 8px' }}>
                        {birdEyeActive ? L.birdEyeHint : L.needBirdEye}
                    </p>
                    <div className="iot-air-stations-body">
                        <ul className="iot-air-stations-list" aria-label={L.listAria}>
                            {vehicles.map((row) => {
                                const isSel = selected?.token === row.token;
                                const right = vehicleLine(row);
                                return (
                                    <li key={row.token} className="iot-air-stations-li">
                                        <button
                                            type="button"
                                            className={`iot-air-stations-row ${isSel ? 'iot-air-stations-row--selected' : ''}`}
                                            aria-pressed={isSel}
                                            onClick={() => focusVehicle(row)}
                                            title={
                                                birdEyeActive
                                                    ? 'Pan bird-eye to center this vehicle'
                                                    : "Switch to bird's-eye view to focus this vehicle"
                                            }
                                        >
                                            <span className="iot-air-stations-row-name">{vehiclePrimaryLabel(row)}</span>
                                            <span className="iot-air-stations-row-aqi">{right}</span>
                                        </button>
                                        {vehicleSecondaryLabel(row) ? (
                                            <span
                                                style={{
                                                    display: 'block',
                                                    padding: '0 12px 8px',
                                                    fontSize: 11,
                                                    opacity: 0.7,
                                                    wordBreak: 'break-word',
                                                }}
                                            >
                                                {vehicleSecondaryLabel(row)}
                                            </span>
                                        ) : null}
                                    </li>
                                );
                            })}
                        </ul>

                        {selected ? (
                            <div className="iot-air-stations-detail">
                                <h3 className="iot-air-stations-detail-name">{vehiclePrimaryLabel(selected)}</h3>
                                <dl className="iot-air-stations-dl">
                                    <div>
                                        <dt>{L.line}</dt>
                                        <dd>{vehicleLine(selected)}</dd>
                                    </div>
                                    <div>
                                        <dt>{L.kind}</dt>
                                        <dd>{vehicleKind(selected)}</dd>
                                    </div>
                                    {selected.journeyName ? (
                                        <div>
                                            <dt>{L.journey}</dt>
                                            <dd>{selected.journeyName}</dd>
                                        </div>
                                    ) : null}
                                    {selected.direction ? (
                                        <div>
                                            <dt>{L.direction}</dt>
                                            <dd>{selected.direction}</dd>
                                        </div>
                                    ) : null}
                                    {selected.state ? (
                                        <div>
                                            <dt>{L.state}</dt>
                                            <dd>{selected.state}</dd>
                                        </div>
                                    ) : null}
                                    {typeof selected.delayMinutes === 'number' &&
                                    Number.isFinite(selected.delayMinutes) ? (
                                        <div>
                                            <dt>{L.delay}</dt>
                                            <dd>{selected.delayMinutes.toFixed(1)}</dd>
                                        </div>
                                    ) : null}
                                    {typeof selected.speedMps === 'number' && Number.isFinite(selected.speedMps) ? (
                                        <div>
                                            <dt>{L.speed}</dt>
                                            <dd>{selected.speedMps.toFixed(2)}</dd>
                                        </div>
                                    ) : null}
                                    {typeof selected.bearing === 'number' && Number.isFinite(selected.bearing) ? (
                                        <div>
                                            <dt>{L.bearing}</dt>
                                            <dd>{Math.round(selected.bearing)}</dd>
                                        </div>
                                    ) : null}
                                    {typeof selected.lat === 'number' && typeof selected.lon === 'number' ? (
                                        <div>
                                            <dt>{L.coords}</dt>
                                            <dd className="iot-air-stations-mono">
                                                {selected.lat.toFixed(5)}, {selected.lon.toFixed(5)}
                                            </dd>
                                        </div>
                                    ) : null}
                                    <div>
                                        <dt>{L.sceneXyz}</dt>
                                        <dd className="iot-air-stations-mono">
                                            {selected.sceneXyzCm
                                                .map((n) => (Number.isFinite(n) ? Math.round(n) : 0))
                                                .join(', ')}
                                        </dd>
                                    </div>
                                    {selected.tripId ? (
                                        <div>
                                            <dt>{L.tripId}</dt>
                                            <dd className="iot-air-stations-mono">{selected.tripId}</dd>
                                        </div>
                                    ) : null}
                                    {selected.licensePlate ? (
                                        <div>
                                            <dt>{L.licensePlate}</dt>
                                            <dd className="iot-air-stations-mono">{selected.licensePlate}</dd>
                                        </div>
                                    ) : null}
                                    <div>
                                        <dt>{L.feedToken}</dt>
                                        <dd className="iot-air-stations-mono">{selected.token}</dd>
                                    </div>
                                </dl>
                            </div>
                        ) : null}
                    </div>
                </>
            )}
        </IotPanelLayout>
    );
};

export default IotTransitLivePanel;
