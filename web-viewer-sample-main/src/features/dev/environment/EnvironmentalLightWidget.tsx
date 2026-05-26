import React from 'react';
import { useEnvironment, useStream } from '../../streaming/contexts';
import './EnvironmentalLightWidget.css';

const WEATHER_PRESET_OPTIONS = [
    { value: 'clearSky', label: 'Clear Sky' },
    { value: 'partlyCloudy', label: 'Partly Cloudy' },
    { value: 'cloudy', label: 'Cloudy' },
    { value: 'overcast', label: 'Overcast' },
    { value: 'lightSnow', label: 'Light Snow' },
    { value: 'heavySnow', label: 'Heavy Snow' },
    { value: 'rainy', label: 'Rainy' },
    { value: 'darkStorm', label: 'Dark Storm' },
];

const EnvironmentalLightWidget: React.FC = () => {
    const env = useEnvironment();
    const stream = useStream();

    if (!stream.streamReady || !env.showEnvironmentalLight) return null;

    return (
        <div className="environmental-light-widget">
            <div className="environmental-light-header">
                <h3 className="environmental-light-title">🌤️ Dynamic Sky Settings</h3>
                <button
                    className="environmental-light-close"
                    onClick={() => env.handleEnvironmentalLightToggle()}
                    title="Close Dynamic Sky Settings"
                >
                    ✕
                </button>
            </div>

            <div className="environmental-light-content">
                <div className="sky-control">
                    <label className="sky-label">Time of Day</label>
                    <div className="sky-slider-container">
                        <input type="range" min="0" max="23" step="1" value={env.timeOfDay} onChange={(e) => env.handleTimeOfDayChange(parseFloat(e.target.value))} className="sky-slider" />
                        <div className="sky-display">
                            <span className="sky-value">{Math.round(env.timeOfDay)}h</span>
                            <span className="sky-label-text">
                                {env.timeOfDay < 6 ? 'Night' : env.timeOfDay < 8 ? 'Dawn' : env.timeOfDay < 18 ? 'Day' : env.timeOfDay < 20 ? 'Dusk' : 'Night'}
                            </span>
                        </div>
                    </div>
                </div>

                <div className="sky-control">
                    <label className="sky-label">Day of Year</label>
                    <div className="sky-slider-container">
                        <input type="range" min="1" max="365" step="1" value={env.dayOfYear} onChange={(e) => env.handleDayOfYearChange(parseInt(e.target.value))} className="sky-slider" />
                        <div className="sky-display">
                            <span className="sky-value">{env.dayOfYear}</span>
                            <span className="sky-label-text">
                                {env.dayOfYear < 80 ? 'Winter' : env.dayOfYear < 172 ? 'Spring' : env.dayOfYear < 266 ? 'Summer' : env.dayOfYear < 355 ? 'Fall' : 'Winter'}
                            </span>
                        </div>
                    </div>
                </div>

                <div className="sky-control-divider" />

                <div className="sky-control">
                    <label className="sky-label">Weather Preset</label>
                    <select className="sky-select" value={env.weatherPreset} onChange={(e) => env.handleWeatherPresetChange(e.target.value)}>
                        {WEATHER_PRESET_OPTIONS.map(opt => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                    </select>
                </div>

                <div className="sky-control">
                    <label className="sky-label">Cloud Coverage</label>
                    <div className="sky-slider-container">
                        <input type="range" min="0" max="1" step="0.01" value={env.cloudCoverage} onChange={(e) => env.handleCloudCoverageChange(parseFloat(e.target.value))} className="sky-slider" />
                        <div className="sky-display">
                            <span className="sky-value">{Math.round(env.cloudCoverage * 100)}%</span>
                            <span className="sky-label-text">
                                {env.cloudCoverage < 0.3 ? 'Blue Sky' : env.cloudCoverage < 0.6 ? 'Default' : 'Overcast'}
                            </span>
                        </div>
                    </div>
                </div>

                <div className="sky-control">
                    <label className="sky-toggle-row">
                        <span className="sky-label" style={{ marginBottom: 0 }}>Cumulus Clouds</span>
                        <input type="checkbox" checked={env.cumulusEnabled} onChange={() => env.handleCumulusToggle()} className="sky-checkbox" />
                    </label>
                </div>
            </div>
        </div>
    );
};

export default EnvironmentalLightWidget;
