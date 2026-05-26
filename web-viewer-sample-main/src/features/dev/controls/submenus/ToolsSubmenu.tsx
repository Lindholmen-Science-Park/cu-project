import React, { useState, useCallback } from 'react';
import { sendMessage } from '../../../streaming/messaging';
import { useEnvironment, useControl, useAppUI, useNavigation } from '../../../streaming/contexts';

interface Props {
    closeMenu: () => void;
}

const ToolsSubmenu: React.FC<Props> = ({ closeMenu }) => {
    const appUI = useAppUI();
    const viewportCaptureStatus = appUI.viewportCaptureStatus;
    const env = useEnvironment();
    const ctrl = useControl();
    const nav = useNavigation();

    const markerPlacementEnabled = ctrl.markerPlacementEnabled;
    const onMarkerPlacementToggle = ctrl.handleMarkerPlacementToggle;
    const incidentPlacementEnabled = ctrl.incidentPlacementEnabled;
    const onIncidentPlacementToggle = ctrl.handleIncidentPlacementToggle;
    const poiMarkersVisible = ctrl.poiMarkersVisible;
    const onPoiMarkersToggle = ctrl.handlePoiMarkersToggle;
    const usdEditMode = ctrl.usdEditMode;
    const onUsdEditToggle = ctrl.handleUsdEditToggle;
    const mediaAdminOpen = ctrl.mediaAdminOpen;
    const setMediaAdminOpen = ctrl.setMediaAdminOpen;
    const cameraDepthStatus = env.cameraDepthStatus;
    const cameraDepthPointCount = env.cameraDepthPointCount;
    const cameraDepthObstacleCount = env.cameraDepthObstacleCount;
    const cameraDepthPointsVisible = env.cameraDepthPointsVisible;
    const cameraDepthAreasVisible = env.cameraDepthAreasVisible;
    const onCameraDepthCapture = env.handleCameraDepthCapture;
    const onCameraDepthDetectObstacles = env.handleCameraDepthDetectObstacles;
    const onCameraDepthClear = env.handleCameraDepthClear;
    const onCameraDepthTogglePoints = env.handleCameraDepthTogglePoints;
    const onCameraDepthToggleAreas = env.handleCameraDepthToggleAreas;

    const [isChatOpen, setIsChatOpen] = useState(false);

    const doSnapshotCapture = useCallback((filePrefix = 'snapshot') => {
        const video = document.getElementById('remote-video') as HTMLVideoElement | null;
        if (!video || video.readyState < 2) return;
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        ctx.drawImage(video, 0, 0);
        const link = document.createElement('a');
        link.download = `${filePrefix}_${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
    }, []);

    const doRenderedCapture = useCallback(() => {
        sendMessage('viewportCaptureRequest', { format: 'jpeg' });
    }, []);

    return (
        <div className="controls-submenu">
            <button className="controls-submenu-back" onClick={() => closeMenu()}>‹ Back</button>
            <h3 className="controls-menu-title">Tools</h3>

            <div className="controls-menu-buttons">
                <button className={`controls-menu-button ${markerPlacementEnabled ? 'active' : ''}`} onClick={() => { onMarkerPlacementToggle(); closeMenu(); }}>
                    <div className="controls-button-icon">{markerPlacementEnabled ? '📍' : '🚫'}</div><span>{markerPlacementEnabled ? 'Disable Markers' : 'Enable Markers'}</span>
                </button>
                {onIncidentPlacementToggle && (
                    <button className={`controls-menu-button ${incidentPlacementEnabled ? 'active' : ''}`} onClick={() => { onIncidentPlacementToggle(); closeMenu(); }}>
                        <div className="controls-button-icon">{incidentPlacementEnabled ? '⚠️' : '🚧'}</div><span>{incidentPlacementEnabled ? 'Disable incidents' : 'Create incident'}</span>
                    </button>
                )}
                <button className={`controls-menu-button ${poiMarkersVisible ? 'active' : ''}`} onClick={() => { onPoiMarkersToggle(); closeMenu(); }}>
                    <div className="controls-button-icon">{poiMarkersVisible ? '🗺️' : '🚫'}</div><span>{poiMarkersVisible ? 'Hide POI Markers' : 'Show POI Markers'}</span>
                </button>
                <button className={`controls-menu-button ${isChatOpen ? 'active' : ''}`} onClick={() => { try { window.dispatchEvent(new CustomEvent('toggleChat')); } catch {} setIsChatOpen(prev => !prev); closeMenu(); }}>
                    <div className="controls-button-icon">💬</div><span>{isChatOpen ? 'Close AI Chat' : 'Open AI Chat'}</span>
                </button>
                {onUsdEditToggle && (
                    <button className={`controls-menu-button ${usdEditMode ? 'active' : ''}`} onClick={() => { onUsdEditToggle(); closeMenu(); }}>
                        <div className="controls-button-icon">{usdEditMode ? '🔴' : '🔵'}</div><span>{usdEditMode ? 'Exit USD Edit' : 'USD Editing'}</span>
                    </button>
                )}
                {setMediaAdminOpen && (
                    <button
                        className={`controls-menu-button ${mediaAdminOpen ? 'active' : ''}`}
                        onClick={() => {
                            setMediaAdminOpen((o) => !o);
                            closeMenu();
                        }}
                    >
                        <div className="controls-button-icon">{mediaAdminOpen ? '📋' : '🎞️'}</div>
                        <span>{mediaAdminOpen ? 'Close media admin' : 'Media content admin'}</span>
                    </button>
                )}
                <button
                    type="button"
                    className={`controls-menu-button ${nav.navmeshDebugOverlayVisible ? 'active' : ''}`}
                    onClick={() => {
                        nav.handleNavmeshDebugOverlayToggle();
                        closeMenu();
                    }}
                    aria-pressed={nav.navmeshDebugOverlayVisible}
                >
                    <div className="controls-button-icon">{nav.navmeshDebugOverlayVisible ? '✅' : '🟦'}</div>
                    <span>{nav.navmeshDebugOverlayVisible ? 'Hide NavMesh' : 'Show NavMesh'}</span>
                </button>
                <button
                    type="button"
                    className={`controls-menu-button ${nav.accessibilityDiffVisible ? 'active' : ''}`}
                    onClick={() => {
                        nav.handleAccessibilityDiffToggle();
                        closeMenu();
                    }}
                    aria-pressed={nav.accessibilityDiffVisible}
                >
                    <div className="controls-button-icon">{nav.accessibilityDiffVisible ? '⛔' : '♿'}</div>
                    <span>{nav.accessibilityDiffVisible ? 'Hide NavMesh difference' : 'NavMesh difference'}</span>
                </button>
            </div>

            <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Viewport Capture</h4>
            <div className="controls-menu-buttons">
                <button className="controls-menu-button" onClick={() => { doSnapshotCapture('snapshot'); closeMenu(); }}>
                    <div className="controls-button-icon">📷</div><span>Snapshot</span>
                </button>
                <button
                    className={`controls-menu-button ${viewportCaptureStatus === 'capturing' ? 'active' : ''}`}
                    disabled={viewportCaptureStatus === 'capturing'}
                    onClick={() => { doRenderedCapture(); closeMenu(); }}
                >
                    <div className="controls-button-icon">{viewportCaptureStatus === 'capturing' ? '⏳' : '🎨'}</div>
                    <span>{viewportCaptureStatus === 'capturing' ? 'Rendering...' : 'Rendered'}</span>
                </button>
            </div>
            <p className="controls-menu-hint">Snapshot: instant stream frame. Rendered: full GPU quality from Kit.</p>

            {onCameraDepthCapture && (<>
                <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Camera Depth Capture</h4>
                <div className="controls-menu-buttons">
                    <button
                        className={`controls-menu-button ${(cameraDepthStatus === 'done' || cameraDepthStatus === 'obstacles_done') ? 'active' : ''}`}
                        disabled={cameraDepthStatus === 'capturing' || cameraDepthStatus === 'detecting'}
                        onClick={() => onCameraDepthCapture()}
                    >
                        <div className="controls-button-icon">{cameraDepthStatus === 'capturing' ? '⏳' : '📡'}</div>
                        <span>{cameraDepthStatus === 'capturing' ? 'Capturing...' : 'Capture Depth'}</span>
                    </button>
                    {(cameraDepthStatus === 'done' || cameraDepthStatus === 'detecting' || cameraDepthStatus === 'obstacles_done') && onCameraDepthDetectObstacles && (
                        <button
                            className={`controls-menu-button ${cameraDepthStatus === 'obstacles_done' ? 'active' : ''}`}
                            disabled={cameraDepthStatus === 'detecting'}
                            onClick={() => onCameraDepthDetectObstacles()}
                        >
                            <div className="controls-button-icon">{cameraDepthStatus === 'detecting' ? '⏳' : '🚧'}</div>
                            <span>{cameraDepthStatus === 'detecting' ? 'Detecting...' : 'Detect Obstacles'}</span>
                        </button>
                    )}
                    {(cameraDepthStatus === 'done' || cameraDepthStatus === 'obstacles_done') && onCameraDepthClear && (
                        <button className="controls-menu-button" onClick={() => onCameraDepthClear()}>
                            <div className="controls-button-icon">🗑️</div><span>Clear All</span>
                        </button>
                    )}
                </div>
                {(cameraDepthStatus === 'done' || cameraDepthStatus === 'obstacles_done') && cameraDepthPointCount > 0 && onCameraDepthTogglePoints && (<>
                    <h4 className="controls-subtitle" style={{ marginTop: 8 }}>Point Cloud ({cameraDepthPointCount.toLocaleString()} pts)</h4>
                    <div className="control-mode-toggle">
                        <button className={`control-mode-btn ${!cameraDepthPointsVisible ? 'active' : ''}`} onClick={() => { if (cameraDepthPointsVisible) onCameraDepthTogglePoints(false); }}>Off</button>
                        <button className={`control-mode-btn ${cameraDepthPointsVisible ? 'active' : ''}`} onClick={() => { if (!cameraDepthPointsVisible) onCameraDepthTogglePoints(true); }}>Show Points</button>
                    </div>
                </>)}
                {cameraDepthStatus === 'obstacles_done' && cameraDepthObstacleCount > 0 && onCameraDepthToggleAreas && (<>
                    <h4 className="controls-subtitle" style={{ marginTop: 8 }}>Obstacle Areas ({cameraDepthObstacleCount})</h4>
                    <div className="control-mode-toggle">
                        <button className={`control-mode-btn ${!cameraDepthAreasVisible ? 'active' : ''}`} onClick={() => { if (cameraDepthAreasVisible) onCameraDepthToggleAreas(false); }}>Off</button>
                        <button className={`control-mode-btn ${cameraDepthAreasVisible ? 'active' : ''}`} onClick={() => { if (!cameraDepthAreasVisible) onCameraDepthToggleAreas(true); }}>Show Areas</button>
                    </div>
                </>)}
                {cameraDepthStatus === 'obstacles_done' && cameraDepthObstacleCount === 0 && (
                    <p className="controls-menu-hint">No obstacles detected</p>
                )}
                {cameraDepthStatus === 'error' && (
                    <p className="controls-menu-hint" style={{ color: '#ff6b6b' }}>Capture failed. Check Kit logs.</p>
                )}
            </>)}
        </div>
    );
};

export default ToolsSubmenu;
