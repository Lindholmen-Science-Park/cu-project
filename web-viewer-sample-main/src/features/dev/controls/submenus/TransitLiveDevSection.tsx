import React from 'react';
import { useControl } from '../../../streaming/contexts';

export interface TransitLiveDevSectionProps {
    closeMenu: () => void;
    /** When true, closing the parent menu after toggle matches legacy Tools behaviour. */
    closeMenuOnToggle?: boolean;
}

/**
 * Dev-only: Västtrafik live transit toggle + status line.
 *
 * Vehicle list selection lives in `IotTransitLivePanel` (overlay) so this section
 * mirrors the AIQ / Bike-share section shape: a primary action button, an "Open
 * list" entry-point, and a status hint. Click → camera focus is performed by the
 * panel via `birdEyePanFocusWorld`, identical to AIQ / Bike-share.
 */
const TransitLiveDevSection: React.FC<TransitLiveDevSectionProps> = ({
    closeMenu,
    closeMenuOnToggle = false,
}) => {
    const ctrl = useControl();
    const status = ctrl.transitLiveOverlayStatus;
    const vehicleCount = status?.vehicles?.length ?? 0;
    const overlayOn = status?.enabled === true;

    const onToggleOverlay = () => {
        ctrl.handleTransitLiveOverlayToggle();
        if (closeMenuOnToggle) {
            closeMenu();
        }
    };

    const openVehiclePanel = () => {
        ctrl.setIotTransitLivePanelOpen(true);
        if (vehicleCount > 0) {
            const sel = ctrl.iotTransitLiveSelectedVehicleToken;
            const list = status?.vehicles ?? [];
            if (!sel || !list.some((v) => v.token === sel)) {
                ctrl.setIotTransitLiveSelectedVehicleToken(list[0]?.token ?? null);
            }
        }
        closeMenu();
    };

    return (
        <>
            <h4 className="controls-subtitle" style={{ marginTop: 14 }}>Live transit (Västtrafik)</h4>
            <div className="controls-menu-buttons">
                <button
                    type="button"
                    className={`controls-menu-button ${overlayOn ? 'active' : ''}`}
                    title="Live transit around the scene center when Kit credentials are set."
                    onClick={onToggleOverlay}
                >
                    <div className="controls-button-icon">{overlayOn ? '🚌' : '🚏'}</div>
                    <span>{overlayOn ? 'Stop live transit overlay' : 'Live transit overlay'}</span>
                </button>
                {(overlayOn || vehicleCount > 0) && (
                    <button type="button" className="controls-menu-button" onClick={openVehiclePanel}>
                        <div className="controls-button-icon">📋</div>
                        <span>Open transit list</span>
                    </button>
                )}
            </div>
            {status && (
                <p className="controls-menu-hint" style={{ marginTop: 6, fontSize: 12 }}>
                    Transit live ({status.transitSource ?? '?'}): {status.vehicleCount} vehicles
                    {status.lastError ? ` — error: ${status.lastError}` : ''}
                    {!status.hasApiKey &&
                        (status.hint
                            ? ` — ${status.hint}`
                            : ' — add VASTTRAFIK_CLIENT_ID and VASTTRAFIK_CLIENT_SECRET to .env')}
                </p>
            )}
        </>
    );
};

export default TransitLiveDevSection;
