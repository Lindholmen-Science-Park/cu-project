import React, { useCallback } from 'react';
import { useEnvironment, useControl } from '../../../streaming/contexts';
import CameraHeightSlider from './CameraHeightSlider';

interface Props {
    onCameraChange?: (cameraType: string) => void;
    closeMenu: () => void;
}

const CamerasSubmenu: React.FC<Props> = ({ onCameraChange: onCameraChangeProp, closeMenu }) => {
    const env = useEnvironment();
    const ctrl = useControl();

    const currentCamera = env.currentCamera;
    const onCameraChange = onCameraChangeProp ?? env.handleCameraChange;
    const activeFixedCamera = env.activeFixedCamera;
    const placedCameras = env.placedCameras ?? [];
    const onRemovePlacedCamera = env.handleRemovePlacedCamera;
    const cameraPlacementEnabled = ctrl.cameraPlacementEnabled;
    const onCameraPlacementToggle = ctrl.handleCameraPlacementToggle;
    const cameraDataHeatmapActive = env.cameraDataHeatmapActive;
    const onCameraDataHeatmapToggle = env.handleCameraDataHeatmapToggle;
    const cameraDataTrackerActive = env.cameraDataTrackerActive;
    const onCameraDataTrackerToggle = env.handleCameraDataTrackerToggle;
    const cameraAreaCubesVisible = env.cameraAreaCubesVisible;
    const onCameraAreaCubesToggle = env.handleCameraAreaCubesToggle;
    const cameraDataCalcActive = env.cameraDataCalcActive;
    const cameraDataCalcBaking = env.cameraDataCalcBaking;
    const onCameraDataCalcToggle = env.handleCameraDataCalcToggle;
    const onOpenCameraPathfindingWidget = useCallback(() => env.setCameraPathfindingWidgetOpen(true), [env.setCameraPathfindingWidgetOpen]);

    const onFixedCameraChange = useCallback(
        (cameraId: string | null) => env.handleFixedCameraChange(cameraId, ctrl.controlMode),
        [env.handleFixedCameraChange, ctrl.controlMode],
    );

    return (
        <div className="controls-submenu">
            <button className="controls-submenu-back" onClick={() => closeMenu()}>‹ Back</button>
            <h3 className="controls-menu-title">Cameras</h3>

            <h4 className="controls-subtitle">Camera View</h4>
            <div className="controls-menu-buttons">
                <button className={`controls-menu-button ${currentCamera === 'first_person' ? 'active' : ''}`} onClick={() => onCameraChange('first_person')}>
                    <div className="controls-button-icon">👤</div><span>First Person</span>
                </button>
                <button className={`controls-menu-button ${currentCamera === 'bird_eye' ? 'active' : ''}`} onClick={() => onCameraChange('bird_eye')}>
                    <div className="controls-button-icon">🦅</div><span>Bird's Eye</span>
                </button>
                <button className={`controls-menu-button ${currentCamera === 'space' ? 'active' : ''}`} onClick={() => onCameraChange('space')}>
                    <div className="controls-button-icon">🌍</div><span>Space</span>
                </button>
            </div>

            {currentCamera === 'first_person' && (
                <CameraHeightSlider />
            )}

            <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Scene Cameras</h4>
            <div className="control-mode-toggle">
                <button className={`control-mode-btn ${!activeFixedCamera || activeFixedCamera === '' ? 'active' : ''}`} onClick={() => { onFixedCameraChange(null); closeMenu(); }}>Off</button>
                <button className={`control-mode-btn ${activeFixedCamera === 'camera_vip_entrance' ? 'active' : ''}`} onClick={() => { onFixedCameraChange('camera_vip_entrance'); closeMenu(); }}>VIP Entrance</button>
                <button className={`control-mode-btn ${activeFixedCamera === 'camera_main_entrance_exit' ? 'active' : ''}`} onClick={() => { onFixedCameraChange('camera_main_entrance_exit'); closeMenu(); }}>Main Exit</button>
                <button className={`control-mode-btn ${activeFixedCamera === 'camera_main_entrance_entry' ? 'active' : ''}`} onClick={() => { onFixedCameraChange('camera_main_entrance_entry'); closeMenu(); }}>Main Entry</button>
            </div>
            <p className="controls-menu-hint">Watch from a fixed camera. Use Prev / Next bar to cycle.</p>

            {placedCameras.length > 0 && (<>
                <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Placed Cameras</h4>
                <div className="control-mode-toggle" style={{ flexDirection: 'column', gap: 4 }}>
                    {placedCameras.map((cam) => (
                        <div key={cam.id} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                            <button
                                className={`control-mode-btn ${activeFixedCamera === cam.id ? 'active' : ''}`}
                                style={{ flex: 1 }}
                                onClick={() => { onFixedCameraChange(activeFixedCamera === cam.id ? null : cam.id); closeMenu(); }}
                            >
                                {cam.label}
                            </button>
                            {onRemovePlacedCamera && (
                                <button
                                    className="control-mode-btn"
                                    style={{ flex: 'none', padding: '4px 8px', fontSize: 12, color: '#ff5555' }}
                                    onClick={() => onRemovePlacedCamera(cam.id)}
                                    title="Remove camera"
                                >
                                    X
                                </button>
                            )}
                        </div>
                    ))}
                </div>
                <p className="controls-menu-hint">Drag to rotate when viewing a placed camera.</p>
            </>)}

            {onCameraPlacementToggle && (
                <div style={{ marginTop: 10 }}>
                    <button
                        className={`controls-menu-button ${cameraPlacementEnabled ? 'active' : ''}`}
                        onClick={() => { onCameraPlacementToggle(); closeMenu(); }}
                    >
                        <div className="controls-button-icon">{cameraPlacementEnabled ? '📹' : '📷'}</div>
                        <span>{cameraPlacementEnabled ? 'Disable Camera Placement' : 'Enable Camera Placement'}</span>
                    </button>
                </div>
            )}

            <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Camera Data Visualization</h4>
            <div className="control-mode-toggle">
                <button className={`control-mode-btn ${cameraDataHeatmapActive ? 'active' : ''}`} onClick={() => onCameraDataHeatmapToggle()}>Heatmap</button>
                <button className={`control-mode-btn ${cameraDataTrackerActive ? 'active' : ''}`} onClick={() => onCameraDataTrackerToggle()}>Sphere Tracker</button>
            </div>

            {onCameraAreaCubesToggle && (<>
                <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Camera Coverage</h4>
                <div className="control-mode-toggle">
                    <button className={`control-mode-btn ${!cameraAreaCubesVisible ? 'active' : ''}`} onClick={() => { if (cameraAreaCubesVisible) onCameraAreaCubesToggle(); closeMenu(); }}>Off</button>
                    <button className={`control-mode-btn ${cameraAreaCubesVisible ? 'active' : ''}`} onClick={() => { if (!cameraAreaCubesVisible) onCameraAreaCubesToggle(); closeMenu(); }}>Show Areas</button>
                </div>
            </>)}

            {onCameraDataCalcToggle && (<>
                <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Camera Data → Pathfinding</h4>
                <div className="control-mode-toggle">
                    <button className={`control-mode-btn ${!cameraDataCalcActive ? 'active' : ''}`} disabled={cameraDataCalcBaking} onClick={() => { if (cameraDataCalcActive) onCameraDataCalcToggle(); }}>Off</button>
                    <button className={`control-mode-btn ${cameraDataCalcActive ? 'active' : ''}`} disabled={cameraDataCalcBaking} onClick={() => { if (!cameraDataCalcActive) onCameraDataCalcToggle(); }}>Active</button>
                </div>
                {cameraDataCalcBaking && <div className="navmesh-baking-indicator">Rebaking NavMesh with camera areas...</div>}
                {cameraDataCalcActive && onOpenCameraPathfindingWidget != null && (
                    <button className="controls-menu-button" onClick={() => { onOpenCameraPathfindingWidget(); closeMenu(); }} style={{ marginTop: 8 }}>
                        <div className="controls-button-icon">📊</div><span>Pathfinding costs…</span>
                    </button>
                )}
            </>)}
        </div>
    );
};

export default CamerasSubmenu;
