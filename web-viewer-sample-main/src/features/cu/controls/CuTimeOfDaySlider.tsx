import React from 'react';
import { useTranslation } from 'react-i18next';
import RangeTrackWithIcons from './RangeTrackWithIcons';
import CuDiscreteSliderTicks from './CuDiscreteSliderTicks';
import { SettingsIconAssets, SettingsSliderEndIcons } from './settings-icons/SettingsIcons';
import { useEnvironment } from '../../streaming/contexts';
import {
    CU_SLIDER_MAX_MINUTES,
    CU_SLIDER_MIN_MINUTES,
    CU_TIME_OF_DAY_TICK_KEYS_QUICK,
    CU_TIME_OF_DAY_TICK_KEYS_WORLD3D,
    formatTimeOfDayLabelHh,
} from '../constants';

export type CuTimeOfDaySliderVariant = 'quick' | 'world3d';

interface CuTimeOfDaySliderProps {
    variant: CuTimeOfDaySliderVariant;
}

/**
 * Shared time-of-day range for Quick settings and Settings → 3D world.
 * Both use 60-minute steps with midnight at the max end (same behaviour; layout/CSS differs).
 */
const CuTimeOfDaySlider: React.FC<CuTimeOfDaySliderProps> = ({ variant }) => {
    const { timeOfDayMinutes, applyTimeOfDay } = useEnvironment();
    const { t } = useTranslation();

    const timeSliderMinutes =
        timeOfDayMinutes === 0
            ? CU_SLIDER_MAX_MINUTES
            : Math.max(CU_SLIDER_MIN_MINUTES, Math.min(CU_SLIDER_MAX_MINUTES, timeOfDayMinutes));

    const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const raw = Number(e.target.value);
        applyTimeOfDay(raw >= CU_SLIDER_MAX_MINUTES ? 0 : raw);
    };

    const tickKeys = variant === 'quick' ? CU_TIME_OF_DAY_TICK_KEYS_QUICK : CU_TIME_OF_DAY_TICK_KEYS_WORLD3D;
    const tickLabels = tickKeys.map((key) => t(key));

    const rangeInputProps = {
        type: 'range' as const,
        min: CU_SLIDER_MIN_MINUTES,
        max: CU_SLIDER_MAX_MINUTES,
        step: 60,
        value: timeSliderMinutes,
        onChange,
        'aria-valuemin': CU_SLIDER_MIN_MINUTES,
        'aria-valuemax': CU_SLIDER_MAX_MINUTES,
        'aria-valuenow': timeSliderMinutes,
        'aria-valuetext': formatTimeOfDayLabelHh(timeOfDayMinutes),
    };

    if (variant === 'quick') {
        return (
            <div className="cu-time-slider-stack">
                <RangeTrackWithIcons
                    railClassName="cu-time-slider-rail cu-time-slider-rail--quick"
                    startIconClassName="cu-time-slider-end-icon"
                    endIconClassName="cu-time-slider-end-icon"
                    trackWrapClassName="cu-time-slider-track-wrap cu-time-slider-track-wrap--230"
                    trackClassName="cu-time-slider-track-img"
                    trackSrc={SettingsIconAssets.track254}
                    startIcon={SettingsSliderEndIcons.worldTimeStart}
                    endIcon={SettingsSliderEndIcons.worldTimeEnd}
                >
                    <input
                        {...rangeInputProps}
                        id="cu-time-of-day-slider"
                        className="cu-time-slider"
                        aria-label={t('people.timeOfDayAria')}
                    />
                </RangeTrackWithIcons>
                <CuDiscreteSliderTicks labels={tickLabels} className="cu-discrete-slider-ticks--quick" />
            </div>
        );
    }

    return (
        <div className="cu-settings-world3d-time-slider-stack">
            <RangeTrackWithIcons
                railClassName="cu-settings-world3d-slider-block cu-settings-world3d-slider-block--time-of-day"
                startIconClassName="cu-settings-world3d-time-icon"
                endIconClassName="cu-settings-world3d-time-icon cu-settings-world3d-time-icon--moon"
                trackWrapClassName="cu-settings-world3d-slider-rail-inner-time"
                trackClassName="cu-settings-world3d-track-bg"
                trackSrc={SettingsIconAssets.track254}
                startIcon={SettingsSliderEndIcons.worldTimeStart}
                endIcon={SettingsSliderEndIcons.worldTimeEnd}
                trackColumnClassName="cu-settings-world3d-time-track-column cu-settings-world3d-slider-rail--time-of-day"
                belowTrack={
                    <CuDiscreteSliderTicks
                        labels={tickLabels}
                        className="cu-discrete-slider-ticks--under-world3d-time-track"
                    />
                }
            >
                <input
                    {...rangeInputProps}
                    id="cu-w3d-time-of-day-slider"
                    className="cu-settings-world3d-range cu-settings-world3d-range--time-of-day"
                    aria-label={t('settings.timeOfDay')}
                />
            </RangeTrackWithIcons>
        </div>
    );
};

export default CuTimeOfDaySlider;
