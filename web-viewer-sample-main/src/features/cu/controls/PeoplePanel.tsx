import React, { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import WeatherSeasonPicker from './WeatherSeasonPicker';
import PanelCloseButton from './PanelCloseButton';
import CuCameraHeightSlider from './CuCameraHeightSlider';
import CuTimeOfDaySlider from './CuTimeOfDaySlider';
import EventDropdown from './EventDropdown';
import { useControl } from '../../streaming/contexts';
import { useModalAccessibility } from '../../streaming/hooks/useModalAccessibility';
import { useSeatSheetForeground } from '../../streaming/hooks/useSeatSheetForeground';
import './PeoplePanel.css';

/** Quick settings: optional Weather row (seasons row is always shown when not overview-only). */
const SHOW_WEATHER_IN_QUICK_SETTINGS = false;

/** Quick settings: “Show crowd” row — set `true` to show again. */
const SHOW_DISPLAY_CROWD_IN_QUICK_SETTINGS = false;

interface PeoplePanelProps {
    onClose: () => void;
    /** In bird's-eye (overview), show only time-of-day slider and close — no weather/seasons/crowd. */
    overviewTimeOnly?: boolean;
}

const PeoplePanel: React.FC<PeoplePanelProps> = ({ onClose, overviewTimeOnly = false }) => {
    const { peopleVisible, handlePeopleToggle } = useControl();
    const { t } = useTranslation();

    const dialogRef = useRef<HTMLDivElement>(null);
    const seatSheetForeground = useSeatSheetForeground();
    useModalAccessibility(dialogRef, { enabled: !seatSheetForeground });

    // WCAG 2.1.1 — Escape closes the dialog from anywhere on the page.
    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [onClose]);

    return (
        <div
            className="cu-people-overlay"
            aria-hidden={seatSheetForeground ? true : undefined}
            inert={seatSheetForeground ? true : undefined}
        >
            <button
                type="button"
                className="cu-people-overlay__backdrop"
                tabIndex={-1}
                aria-label={t('common.close')}
                onClick={onClose}
            />
            <div
                ref={dialogRef}
                className={`cu-people-panel cu-people-card cu-world-settings-panel${overviewTimeOnly ? ' cu-people-card--overview-time-only' : ''}`}
                aria-hidden={seatSheetForeground ? true : undefined}
                inert={seatSheetForeground ? true : undefined}
                role="dialog"
                aria-modal="true"
                aria-labelledby="cu-world-settings-title"
                onClick={(e) => e.stopPropagation()}
            >
            <div className="cu-weather-inner">
                <div className="cu-weather-container">
                    <div className="cu-world-settings-header">
                        <h2 className="cu-world-settings-title" id="cu-world-settings-title">
                            {t('people.quickSettingsTitle')}
                        </h2>
                        <div className="cu-world-settings-header-actions">
                            <PanelCloseButton onClick={onClose} />
                        </div>
                    </div>

                    <div className="cu-weather-time-block">
                        <span className="cu-weather-sublabel" id="cu-time-of-day-label">
                            {t('people.timeOfDay')}
                        </span>
                        <div
                            className="cu-time-slider-block"
                            role="group"
                            aria-labelledby="cu-time-of-day-label"
                        >
                            <CuTimeOfDaySlider variant="quick" />
                        </div>
                    </div>

                    {!overviewTimeOnly && (
                        <WeatherSeasonPicker showWeather={SHOW_WEATHER_IN_QUICK_SETTINGS} />
                    )}

                    {!overviewTimeOnly && (
                        <div className="cu-weather-time-block">
                            <span className="cu-weather-sublabel" id="cu-quick-camera-height-label">
                                {t('settings.cameraHeight')}
                            </span>
                            <div
                                className="cu-time-slider-block"
                                role="group"
                                aria-labelledby="cu-quick-camera-height-label"
                            >
                                <CuCameraHeightSlider variant="quick" />
                            </div>
                        </div>
                    )}

                    {!overviewTimeOnly && (
                        <div
                            className="cu-quick-settings-event"
                            role="group"
                            aria-labelledby="cu-quick-settings-event-label"
                        >
                            <span className="cu-weather-sublabel" id="cu-quick-settings-event-label">
                                {t('people.selectEvent')}
                            </span>
                            <EventDropdown labelId="cu-quick-settings-event-label" />
                        </div>
                    )}

                    {!overviewTimeOnly && SHOW_DISPLAY_CROWD_IN_QUICK_SETTINGS && (
                    <div
                        className="cu-display-crowd-box"
                        role="group"
                        aria-labelledby="cu-display-crowd-label"
                    >
                        <span className="cu-weather-sublabel cu-display-crowd-heading" id="cu-display-crowd-label">
                            {t('settings.displayCrowd')}
                        </span>
                        <div className="cu-display-crowd-toggle-wrap">
                            <span className="cu-display-crowd-state" aria-hidden>
                                {peopleVisible ? t('common.on') : t('common.off')}
                            </span>
                            <button
                                type="button"
                                className={`cu-display-crowd-switch${peopleVisible ? ' cu-display-crowd-switch--on' : ''}`}
                                role="switch"
                                aria-checked={peopleVisible}
                                aria-labelledby="cu-display-crowd-label"
                                onClick={handlePeopleToggle}
                            >
                                <span className="cu-display-crowd-thumb" />
                            </button>
                        </div>
                    </div>
                    )}
                </div>
            </div>
            </div>
        </div>
    );
};

export default PeoplePanel;
