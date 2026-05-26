import React from 'react';
import { useEnvironment, useNavigation, useControl } from '../../../streaming/contexts';

const QuickStatus: React.FC = () => {
    const env = useEnvironment();
    const nav = useNavigation();
    const ctrl = useControl();

    const currentCamera = env.currentCamera;
    const currentPhysics = env.currentPhysics;
    const showWeather = env.showWeather;
    const fogIntensity = env.fogIntensity;
    const showEnvironmentalLight = env.showEnvironmentalLight;
    const peopleVisible = ctrl.peopleVisible;
    const iotAirStationsLoaded = (ctrl.iotAirStations?.length ?? 0) > 0;
    const activeFixedCamera = env.activeFixedCamera;
    const navmeshActive = nav.navmeshActive;
    const navmeshBaking = nav.navmeshBaking;
    const activeSpotRouteId = nav.activeSpotRouteId;
    const movingToSpotId = nav.movingToSpotId;
    const navigationSpots = nav.navigationSpots;
    const controlMode = ctrl.controlMode;
    const cameraDataHeatmapActive = env.cameraDataHeatmapActive;
    const cameraDataTrackerActive = env.cameraDataTrackerActive;
    const cameraDataStats = env.cameraDataStats;

    return (
        <div className="quick-status">
            <div className="status-item">
                <span className="status-icon">👤</span>
                <span className="status-text">{currentCamera === 'first_person' ? '1st Person' : 'Bird Eye'}</span>
            </div>
            <div className="status-item">
                <span className="status-icon">{currentPhysics === 'enabled' ? '🛑' : '▶️'}</span>
                <span className="status-text">{currentPhysics === 'enabled' ? 'Physics On' : 'Physics Off'}</span>
            </div>
            {showWeather && (
                <div className="status-item">
                    <span className="status-icon">🌤️</span>
                    <span className="status-text">Weather On</span>
                </div>
            )}
            {showWeather && fogIntensity > 0 && (
                <div className="status-item">
                    <span className="status-icon">🌫️</span>
                    <span className="status-text">Fog {fogIntensity.toFixed(1)}</span>
                </div>
            )}
            {showEnvironmentalLight && (
                <div className="status-item">
                    <span className="status-icon">🌤️</span>
                    <span className="status-text">Light Settings On</span>
                </div>
            )}
            {peopleVisible && (
                <div className="status-item">
                    <span className="status-icon">🚶</span>
                    <span className="status-text">People ON</span>
                </div>
            )}
            {iotAirStationsLoaded && (
                <div className="status-item status-item--iot-air">
                    <span className="status-icon">🌡️</span>
                    <span className="status-text">WAQI air stations loaded</span>
                </div>
            )}
            {activeFixedCamera && activeFixedCamera !== '' && (
                <div className="status-item">
                    <span className="status-icon">📷</span>
                    <span className="status-text">
                        {activeFixedCamera === 'camera_vip_entrance' ? 'Fixed: VIP Entrance' :
                         activeFixedCamera === 'camera_main_entrance_exit' ? 'Fixed: Main Exit' :
                         activeFixedCamera === 'camera_main_entrance_entry' ? 'Fixed: Main Entry' : `Fixed: ${activeFixedCamera}`}
                    </span>
                </div>
            )}
            {navmeshActive && (
                <div className="status-item">
                    <span className="status-icon">🗺️</span>
                    <span className="status-text">NavMesh Navigation ON</span>
                </div>
            )}
            {navmeshBaking && (
                <div className="status-item baking">
                    <span className="status-icon">⏳</span>
                    <span className="status-text">Rebaking NavMesh...</span>
                </div>
            )}
            {activeSpotRouteId && (
                <div className="status-item">
                    <span className="status-icon">{movingToSpotId ? '🚶' : '📍'}</span>
                    <span className="status-text">
                        {movingToSpotId
                            ? `Moving to ${navigationSpots.find(s => s.id === activeSpotRouteId)?.label ?? activeSpotRouteId}`
                            : `Route: ${navigationSpots.find(s => s.id === activeSpotRouteId)?.label ?? activeSpotRouteId}`}
                    </span>
                </div>
            )}
            <div className="status-item">
                <span className="status-icon">
                    {controlMode === 'pointClick' ? '🖱️' : controlMode === 'wasd' ? '⌨️' : '🕹️'}
                </span>
                <span className="status-text">
                    {controlMode === 'pointClick' ? 'Point & Click' : controlMode === 'wasd' ? 'WASD' : 'Joystick'}
                </span>
            </div>
            {cameraDataHeatmapActive && (
                <div className="status-item">
                    <span className="status-icon">🗺️</span>
                    <span className="status-text">Heatmap ON</span>
                </div>
            )}
            {cameraDataTrackerActive && (
                <>
                    <div className="status-item">
                        <span className="status-icon">📹</span>
                        <span className="status-text">Tracker ON</span>
                    </div>
                    {cameraDataStats && (
                        <>
                            <div className="status-item">
                                <span className="status-icon">👥</span>
                                <span className="status-text">Current: {cameraDataStats.current}</span>
                            </div>
                            <div className="status-item">
                                <span className="status-icon">🔄</span>
                                <span className="status-text">Last 1m: {cameraDataStats.unique_last_1m} unique</span>
                            </div>
                            <div className="status-item">
                                <span className="status-icon">📊</span>
                                <span className="status-text">Avg: {cameraDataStats.avg_concurrent_1m}</span>
                            </div>
                            <div className={`status-item traffic-level traffic-level-${(cameraDataStats.traffic_level || 'low').toLowerCase()}`}>
                                <span className="status-icon">🚦</span>
                                <span className="status-text">Traffic: {(cameraDataStats.traffic_level || 'low').toUpperCase()}</span>
                            </div>
                        </>
                    )}
                </>
            )}
        </div>
    );
};

export default QuickStatus;
