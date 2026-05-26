import React from 'react';
import { useTranslation } from 'react-i18next';
import {
    CloudSunIcon,
    CloudRainIcon,
    CloudFogIcon,
    CloudSnowIcon,
    SeasonSummerIcon,
    SeasonSpringIcon,
    SeasonAutumnIcon,
    SeasonWinterIcon,
} from '../WeatherIcons';
import { WeatherOption, SeasonOption } from '../types';
import { useEnvironment } from '../../streaming/contexts';

const WEATHER_ORDER: WeatherOption[] = ['sun', 'rain', 'fog', 'snow'];
const SEASON_ORDER: SeasonOption[] = ['spring', 'summer', 'autumn', 'winter'];

const WeatherIcon: Record<WeatherOption, React.FC> = {
    sun: CloudSunIcon,
    rain: CloudRainIcon,
    fog: CloudFogIcon,
    snow: CloudSnowIcon,
};

const WEATHER_I18N: Record<WeatherOption, { title: string; aria: string }> = {
    sun: { title: 'people.sun', aria: 'people.weatherSun' },
    rain: { title: 'people.rain', aria: 'people.weatherRain' },
    fog: { title: 'people.fog', aria: 'people.weatherFog' },
    snow: { title: 'people.snow', aria: 'people.weatherSnow' },
};

const SeasonIcon: Record<SeasonOption, React.FC> = {
    summer: SeasonSummerIcon,
    spring: SeasonSpringIcon,
    autumn: SeasonAutumnIcon,
    winter: SeasonWinterIcon,
};

const SEASON_I18N: Record<SeasonOption, { title: string; aria: string }> = {
    summer: { title: 'people.seasonSummer', aria: 'people.seasonAriaSummer' },
    spring: { title: 'people.seasonSpring', aria: 'people.seasonAriaSpring' },
    autumn: { title: 'people.seasonAutumn', aria: 'people.seasonAriaAutumn' },
    winter: { title: 'people.seasonWinter', aria: 'people.seasonAriaWinter' },
};

export interface WeatherSeasonPickerProps {
    /** When false, only the seasons row is shown (Quick settings layout). */
    showWeather?: boolean;
}

const WeatherSeasonPicker: React.FC<WeatherSeasonPickerProps> = ({ showWeather = true }) => {
    const { weather, applyWeather, season, applySeason } = useEnvironment();
    const { t } = useTranslation();

    return (
        <>
            {showWeather ? (
            <div
                className="cu-weather-box cu-env-toggle-row"
                role="group"
                aria-labelledby="cu-weather-panel-title"
            >
                <span className="cu-weather-label" id="cu-weather-panel-title">
                    {t('people.weather')}
                </span>
                {WEATHER_ORDER.map((w) => {
                    const Icon = WeatherIcon[w];
                    const keys = WEATHER_I18N[w];
                    return (
                        <button
                            key={w}
                            type="button"
                            className={`cu-weather-btn ${weather === w ? 'active' : ''}`}
                            title={t(keys.title)}
                            aria-label={t(keys.aria)}
                            aria-pressed={weather === w}
                            onClick={() => applyWeather(w)}
                        >
                            <Icon />
                        </button>
                    );
                })}
            </div>
            ) : null}

            <div
                className="cu-seasons-box cu-env-toggle-row"
                role="group"
                aria-labelledby="cu-seasons-panel-title"
            >
                <span className="cu-weather-label" id="cu-seasons-panel-title">
                    {t('people.seasons')}
                </span>
                <div className="cu-seasons-icons">
                    {SEASON_ORDER.map((s) => {
                        const Icon = SeasonIcon[s];
                        const keys = SEASON_I18N[s];
                        return (
                            <button
                                key={s}
                                type="button"
                                className={`cu-weather-btn ${season === s ? 'active' : ''}`}
                                title={t(keys.title)}
                                aria-label={t(keys.aria)}
                                aria-pressed={season === s}
                                onClick={() => applySeason(s)}
                            >
                                <Icon />
                            </button>
                        );
                    })}
                </div>
            </div>
        </>
    );
};

export default WeatherSeasonPicker;
