import React from 'react';
import {
    CloudSunIcon,
    CloudRainIcon,
    CloudFogIcon,
    CloudSnowIcon,
    SeasonSummerIcon,
    SeasonSpringIcon,
    SeasonAutumnIcon,
    SeasonWinterIcon,
} from '../../cu/WeatherIcons';
import type { WeatherOption, SeasonOption } from '../../cu/types';
import { useEnvironment, useStream } from '../../streaming/contexts';
import './DevWeatherSeasonPicker.css';

const WEATHER_OPTIONS: { key: WeatherOption; label: string; Icon: React.FC }[] = [
    { key: 'sun', label: 'Sun', Icon: CloudSunIcon },
    { key: 'rain', label: 'Rain', Icon: CloudRainIcon },
    { key: 'fog', label: 'Fog', Icon: CloudFogIcon },
    { key: 'snow', label: 'Snow', Icon: CloudSnowIcon },
];

const SEASON_OPTIONS: { key: SeasonOption; label: string; Icon: React.FC }[] = [
    { key: 'summer', label: 'Summer', Icon: SeasonSummerIcon },
    { key: 'spring', label: 'Spring', Icon: SeasonSpringIcon },
    { key: 'autumn', label: 'Autumn', Icon: SeasonAutumnIcon },
    { key: 'winter', label: 'Winter', Icon: SeasonWinterIcon },
];

const DevWeatherSeasonPicker: React.FC = () => {
    const env = useEnvironment();
    const stream = useStream();

    if (!stream.streamReady || !env.showWeatherSeasonPicker) return null;

    return (
        <div className="dev-weather-season-widget">
            <div className="dev-weather-season-header">
                <h3 className="dev-weather-season-title">Weather & Seasons</h3>
                <button
                    className="dev-weather-season-close"
                    onClick={() => env.handleWeatherSeasonPickerToggle()}
                    title="Close"
                >
                    ✕
                </button>
            </div>

            <div className="dev-weather-season-content">
                <span className="dev-weather-season-section-label">Weather</span>
                <div className="dev-weather-season-row">
                    {WEATHER_OPTIONS.map(({ key, label, Icon }) => (
                        <button
                            key={key}
                            className={`dev-weather-season-btn ${env.weather === key ? 'active' : ''}`}
                            onClick={() => env.applyWeather(key)}
                            title={label}
                        >
                            <span className="dev-weather-season-btn-icon"><Icon /></span>
                            {label}
                        </button>
                    ))}
                </div>

                <span className="dev-weather-season-section-label">Season</span>
                <div className="dev-weather-season-row">
                    {SEASON_OPTIONS.map(({ key, label, Icon }) => (
                        <button
                            key={key}
                            className={`dev-weather-season-btn ${env.season === key ? 'active' : ''}`}
                            onClick={() => env.applySeason(key)}
                            title={label}
                        >
                            <span className="dev-weather-season-btn-icon"><Icon /></span>
                            {label}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default DevWeatherSeasonPicker;
