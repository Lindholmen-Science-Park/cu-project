import React, { useCallback } from 'react';
import { useEnvironment, useNavigation, useControl, useAppUI } from '../../../streaming/contexts';
import { sendMessage } from '../../../streaming/messaging';

interface Props {
    closeMenu: () => void;
}

const NavigationSubmenu: React.FC<Props> = ({ closeMenu }) => {
    const appUI = useAppUI();
    const env = useEnvironment();
    const nav = useNavigation();
    const ctrl = useControl();

    const navmeshMode = nav.navmeshMode;
    const navmeshBaking = nav.navmeshBaking;
    const onNavmeshModeChange = nav.handleNavmeshModeChange;
    const routeMeasureEnabled = nav.routeMeasureEnabled;
    const onRouteMeasureToggle = nav.handleRouteMeasureToggle;
    const pointClickCostsActive = nav.pointClickCostsActive;
    const onPointClickCostsToggle = nav.handlePointClickCostsToggle;
    const shortcutsActive = nav.shortcutsActive;
    const onShortcutsToggle = nav.handleShortcutsToggle;
    const preferShortcutsActive = nav.preferShortcutsActive;
    const onPreferShortcutsToggle = nav.handlePreferShortcutsToggle;
    const onCalculateRoutesToExits = nav.handleCalculateRoutesToExits;
    const onOpenRestroomWidget = nav.handleOpenRestroomWidget;
    const onOpenQuietZoneWidget = nav.handleOpenQuietZoneWidget;
    const onOpenOsmNavigateWidget = useCallback(() => nav.setOsmNavigateOpen(true), [nav.setOsmNavigateOpen]);
    const osmRouteOverlayVisible = nav.osmRouteOverlayVisible;
    const osmRouteOverlayRoadSnap = nav.osmRouteOverlayRoadSnap;
    const onOsmRouteOverlayToggle = nav.handleOsmRouteOverlayToggle;
    const onOsmRouteOverlayRoadSnapToggle = nav.handleOsmRouteOverlayRoadSnapToggle;
    const controlMode = ctrl.controlMode;
    const onControlModeChange = ctrl.handleControlModeChange;
    const movementSpeed = env.movementSpeed;
    const onSpeedChange = env.handleSpeedChange;

    return (
        <div className="controls-submenu">
            <button className="controls-submenu-back" onClick={() => closeMenu()}>‹ Back</button>
            <h3 className="controls-menu-title">Navigation</h3>

            <h4 className="controls-subtitle">Accessibility Mode</h4>
            <div className="navmesh-mode-toggle">
                <button className={`navmesh-mode-btn ${navmeshMode === 'wheelchair' ? 'active' : ''}`} disabled={navmeshBaking} onClick={() => onNavmeshModeChange?.('wheelchair')}>♿ Wheelchair</button>
                <button className={`navmesh-mode-btn ${navmeshMode === 'walking' ? 'active' : ''}`} disabled={navmeshBaking} onClick={() => onNavmeshModeChange?.('walking')}>🚶 Walking</button>
            </div>
            {navmeshBaking && <div className="navmesh-baking-indicator">Rebaking NavMesh...</div>}

            <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Routes</h4>
            <div className="controls-menu-buttons">
                {onRouteMeasureToggle != null && (
                    <button className={`controls-menu-button ${routeMeasureEnabled ? 'active' : ''}`} onClick={() => { onRouteMeasureToggle(); closeMenu(); }}>
                        <div className="controls-button-icon">{routeMeasureEnabled ? '📏' : '📐'}</div><span>{routeMeasureEnabled ? 'Route measure ON' : 'Route measure OFF'}</span>
                    </button>
                )}
                {onPointClickCostsToggle != null && (
                    <button className={`controls-menu-button ${pointClickCostsActive ? 'active' : ''}`} onClick={() => onPointClickCostsToggle()}>
                        <div className="controls-button-icon">{pointClickCostsActive ? '🔀' : '➡️'}</div><span>{pointClickCostsActive ? 'Areas affect player movement ON' : 'Areas affect player movement OFF'}</span>
                    </button>
                )}
                {onShortcutsToggle != null && (
                    <button className={`controls-menu-button ${shortcutsActive ? 'active' : ''}`} onClick={() => onShortcutsToggle()}>
                        <div className="controls-button-icon">{shortcutsActive ? '🛗' : '🚪'}</div><span>{shortcutsActive ? 'Use shortcuts ON' : 'Use shortcuts OFF'}</span>
                    </button>
                )}
                {onPreferShortcutsToggle != null && (
                    <button
                        className={`controls-menu-button ${preferShortcutsActive ? 'active' : ''}`}
                        onClick={() => onPreferShortcutsToggle()}
                        disabled={!shortcutsActive}
                        title={shortcutsActive ? '' : 'Enable "Use shortcuts" first'}
                    >
                        <div className="controls-button-icon">{preferShortcutsActive ? '⬆️' : '⚖️'}</div>
                        <span>{preferShortcutsActive ? 'Prefer elevators ON' : 'Prefer elevators OFF'}</span>
                    </button>
                )}
                {onCalculateRoutesToExits != null && (
                    <button className="controls-menu-button" onClick={() => { onCalculateRoutesToExits(); closeMenu(); }}>
                        <div className="controls-button-icon">🚪</div><span>Calculate routes to exits</span>
                    </button>
                )}
                {onOpenRestroomWidget != null && (
                    <button className="controls-menu-button" onClick={() => { onOpenRestroomWidget(); closeMenu(); }}>
                        <div className="controls-button-icon">🚻</div><span>Find restrooms</span>
                    </button>
                )}
                {onOpenQuietZoneWidget != null && (
                    <button className="controls-menu-button" onClick={() => { onOpenQuietZoneWidget(); closeMenu(); }}>
                        <div className="controls-button-icon">🧘</div><span>Find quiet zones</span>
                    </button>
                )}
                <button className="controls-menu-button" onClick={() => { appUI.setSeatPanelStickyOpen(true); nav.setSeatWidgetOpen(true); closeMenu(); }}>
                    <div className="controls-button-icon">💺</div><span>Navigate to seat</span>
                </button>
                {onOpenOsmNavigateWidget != null && (
                    <button className="controls-menu-button" onClick={() => { onOpenOsmNavigateWidget(); closeMenu(); }}>
                        <div className="controls-button-icon">🗺️</div><span>City navigate</span>
                    </button>
                )}
                {onOsmRouteOverlayToggle != null && (
                    <button
                        type="button"
                        className={`controls-menu-button ${osmRouteOverlayVisible ? 'active' : ''}`}
                        onClick={() => { onOsmRouteOverlayToggle(); }}
                    >
                        <div className="controls-button-icon">{osmRouteOverlayVisible ? '🔵' : '⚪'}</div>
                        <span>{osmRouteOverlayVisible ? 'OSM walk routes ON' : 'Show OSM walk routes'}</span>
                    </button>
                )}
                {osmRouteOverlayVisible && onOsmRouteOverlayRoadSnapToggle != null && (
                    <button
                        type="button"
                        className={`controls-menu-button ${osmRouteOverlayRoadSnap ? 'active' : ''}`}
                        onClick={() => { onOsmRouteOverlayRoadSnapToggle(); }}
                    >
                        <div className="controls-button-icon">{osmRouteOverlayRoadSnap ? '🛣️' : '📍'}</div>
                        <span>{osmRouteOverlayRoadSnap ? 'Force OSM snap ON' : 'Force OSM snap (dev)'}</span>
                    </button>
                )}
                {osmRouteOverlayVisible && (
                    <p className="controls-menu-hint" style={{ marginTop: 6 }}>
                        Translucent walk-graph routes (filtered to your current mode) drape over the world. Tap on or near a route to bridge onto OSM and walk to the clicked spot — keep tapping further along to keep going. Tap plain ground (NavMesh) to use the regular NavMesh route — that's the &ldquo;jump off&rdquo; gesture.
                    </p>
                )}
            </div>

            <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Control Mode</h4>
            <div className="control-mode-toggle">
                <button className={`control-mode-btn ${controlMode === 'pointClick' ? 'active' : ''}`} onClick={() => { onControlModeChange('pointClick'); closeMenu(); }}>🖱️ Point & Click</button>
                <button className={`control-mode-btn ${controlMode === 'wasd' ? 'active' : ''}`} onClick={() => { onControlModeChange('wasd'); closeMenu(); }}>⌨️ WASD</button>
                <button className={`control-mode-btn ${controlMode === 'joystick' ? 'active' : ''}`} onClick={() => { onControlModeChange('joystick'); closeMenu(); }}>🕹️ Joystick</button>
            </div>

            <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Movement Speed</h4>
            <div className="speed-control">
                <div className="speed-slider-container">
                    <input type="range" min="0.1" max="10.0" step="0.1" value={movementSpeed} onChange={(e) => onSpeedChange?.(parseFloat(e.target.value))} className="speed-slider" />
                    <div className="speed-display">
                        <span className="speed-value">{movementSpeed.toFixed(1)}x</span>
                        <span className="speed-label">
                            {movementSpeed < 0.5 ? 'Very Slow' : movementSpeed < 1.0 ? 'Slow' : movementSpeed < 2.0 ? 'Normal' : movementSpeed < 3.0 ? 'Fast' : movementSpeed < 5.0 ? 'Very Fast' : movementSpeed < 7.0 ? 'Extreme' : 'Ludicrous'}
                        </span>
                    </div>
                </div>
            </div>

            {env.currentCamera === 'bird_eye' && (
                <>
                    <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Bird's Eye Routes</h4>
                    <div className="controls-menu-buttons">
                        <button
                            className="controls-menu-button"
                            onClick={() => {
                                sendMessage('birdEyeRouteRequest', {
                                    startPos: null,
                                    endSpawnPoint: 'PlayerSpawnPoint_Foyer',
                                });
                            }}
                        >
                            <div className="controls-button-icon">🗺️</div>
                            <span>Get directions to Foyer</span>
                        </button>
                        <button
                            className="controls-menu-button"
                            onClick={() => {
                                sendMessage('birdEyeRouteRequest', {
                                    startPos: null,
                                    endSeatNumber: 'P-35-5',
                                    useWaypoints: true,
                                    section: 'P',
                                });
                            }}
                        >
                            <div className="controls-button-icon">💺</div>
                            <span>Get directions to seat P-35-5</span>
                        </button>
                        <button
                            className="controls-menu-button"
                            onClick={() => {
                                sendMessage('birdEyeRouteClear', {});
                                ctrl.setBirdEyeRoutePoints(null);
                            }}
                            disabled={!ctrl.birdEyeRoutePoints}
                        >
                            <div className="controls-button-icon">✖️</div>
                            <span>Clear route</span>
                        </button>
                    </div>
                </>
            )}

            <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Touch Look Direction</h4>
            <div className="control-mode-toggle">
                <button className={`control-mode-btn ${!appUI.invertTouchLook ? 'active' : ''}`} onClick={() => { if (appUI.invertTouchLook) appUI.handleInvertTouchLookToggle(); }}>Direct</button>
                <button className={`control-mode-btn ${appUI.invertTouchLook ? 'active' : ''}`} onClick={() => { if (!appUI.invertTouchLook) appUI.handleInvertTouchLookToggle(); }}>Inverted (mobile)</button>
            </div>
            <p className="controls-menu-hint">Inverted: swipe right to look left (natural mobile scrolling).</p>
        </div>
    );
};

export default NavigationSubmenu;
