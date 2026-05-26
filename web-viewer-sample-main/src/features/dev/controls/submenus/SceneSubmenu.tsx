import React from 'react';
import { useEnvironment, useNavigation, useAppUI } from '../../../streaming/contexts';

interface Props {
    onSceneSwitch?: (sceneId: string) => void;
    closeMenu: () => void;
}

const SceneSubmenu: React.FC<Props> = ({ onSceneSwitch, closeMenu }) => {
    const appUI = useAppUI();
    const availableScenes = appUI.availableScenes;
    const env = useEnvironment();
    const nav = useNavigation();

    const showWeather = env.showWeather;
    const onWeatherToggle = env.handleWeatherToggle;
    const showEnvironmentalLight = env.showEnvironmentalLight;
    const onEnvironmentalLightToggle = env.handleEnvironmentalLightToggle;
    const showWeatherSeasonPicker = env.showWeatherSeasonPicker;
    const onWeatherSeasonPickerToggle = env.handleWeatherSeasonPickerToggle;
    const fogIntensity = env.fogIntensity;
    const onFogIntensityChange = env.handleFogIntensityChange;
    const seatingLayout = nav.seatingLayout ?? null;
    const availableSeatingLayouts = nav.availableSeatingLayouts ?? [];
    const onSeatingLayoutChange = nav.handleSeatingLayoutChange;
    const seatedCrowdLayout = nav.seatedCrowdLayout ?? null;
    const availableSeatedCrowdLayouts = nav.availableSeatedCrowdLayouts ?? [];
    const onSeatedCrowdLayoutChange = nav.handleSeatedCrowdLayoutChange;

    // Friendly labels for the crowd_density USD variants emitted by
    // generate_seated_pointinstancer.py. Order matches the empty -> full ramp.
    const CROWD_LABELS: Record<string, string> = {
        none:   'hidden',
        sparse: '60%',
        medium: '75%',
        dense:  '90%',
        full:   '100%',
    };
    const CROWD_ORDER = ['none', 'sparse', 'medium', 'dense', 'full'];
    const sortedCrowdLayouts = [...availableSeatedCrowdLayouts].sort(
        (a, b) => CROWD_ORDER.indexOf(a) - CROWD_ORDER.indexOf(b),
    );

    return (
        <div className="controls-submenu">
            <button className="controls-submenu-back" onClick={() => closeMenu()}>‹ Back</button>
            <h3 className="controls-menu-title">Scene</h3>

            {onSceneSwitch && availableScenes.length > 0 && (
            <>
                <h4 className="controls-subtitle">Switch Scene</h4>
                <select
                    className="controls-menu-select"
                    value=""
                    onChange={(e) => { const id = e.target.value; if (id) { try { onSceneSwitch(id); } catch {} closeMenu(); } }}
                    aria-label="Select scene"
                >
                    <option value="">Select scene…</option>
                    {availableScenes.map((s) => (<option key={s.id} value={s.id}>{s.label}</option>))}
                </select>
            </>
            )}

            <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Environment</h4>
            <div className="controls-menu-buttons">
                <button className={`controls-menu-button weather-button ${showWeather ? 'active' : ''}`} onClick={() => onWeatherToggle()}>
                    <div className="controls-button-icon">{showWeather ? '🌤️' : '☀️'}</div><span>Weather UI</span>
                </button>
                <button className={`controls-menu-button environmental-light-button ${showEnvironmentalLight ? 'active' : ''}`} onClick={() => onEnvironmentalLightToggle()}>
                    <div className="controls-button-icon">{showEnvironmentalLight ? '🌥️' : '☀️'}</div><span>Dynamic Sky UI</span>
                </button>
                <button className={`controls-menu-button weather-button ${showWeatherSeasonPicker ? 'active' : ''}`} onClick={() => onWeatherSeasonPickerToggle()}>
                    <div className="controls-button-icon">{showWeatherSeasonPicker ? '🌦️' : '🌿'}</div><span>Weather & Seasons</span>
                </button>
            </div>

            <div className="controls-menu-subsection" style={{ marginTop: 6 }}>
                <h4 className="controls-subtitle fog-title">Fog</h4>
                <div className="fog-control">
                    <div className="fog-slider-container">
                        <input type="range" min="0" max="1" step="0.1" value={fogIntensity} onChange={(e) => onFogIntensityChange(parseFloat(e.target.value))} className="fog-slider" />
                        <div className="fog-display">
                            <span className="fog-value">{fogIntensity.toFixed(1)}</span>
                            <span className="fog-label">{fogIntensity === 0 ? 'Disabled' : fogIntensity < 0.3 ? 'Light' : fogIntensity < 0.6 ? 'Medium' : fogIntensity < 0.8 ? 'Heavy' : 'Dense'}</span>
                        </div>
                    </div>
                </div>
            </div>

            {onSeatingLayoutChange && availableSeatingLayouts.length > 1 && (<>
                <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Seating Layout</h4>
                <div className="navmesh-mode-toggle">
                    {availableSeatingLayouts.map((variant) => (
                        <button key={variant} className={`navmesh-mode-btn ${seatingLayout === variant ? 'active' : ''}`} onClick={() => onSeatingLayoutChange(variant)}>{variant.replace(/_/g, ' ')}</button>
                    ))}
                </div>
            </>)}

            {onSeatedCrowdLayoutChange && sortedCrowdLayouts.length > 1 && (<>
                <h4 className="controls-subtitle" style={{ marginTop: 10 }}>Crowd Density</h4>
                <div className="navmesh-mode-toggle">
                    {sortedCrowdLayouts.map((variant) => (
                        <button
                            key={variant}
                            className={`navmesh-mode-btn ${seatedCrowdLayout === variant ? 'active' : ''}`}
                            onClick={() => onSeatedCrowdLayoutChange(variant)}
                        >
                            {CROWD_LABELS[variant] ?? variant}
                        </button>
                    ))}
                </div>
            </>)}
        </div>
    );
};

export default SceneSubmenu;
