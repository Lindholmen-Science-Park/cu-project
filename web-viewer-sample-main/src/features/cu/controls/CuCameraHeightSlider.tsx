import React from 'react';
import { useTranslation } from 'react-i18next';
import RangeTrackWithIcons from './RangeTrackWithIcons';
import CuDiscreteSliderTicks from './CuDiscreteSliderTicks';
import { SettingsIconAssets, SettingsSliderEndIcons } from './settings-icons/SettingsIcons';
import { useEnvironment } from '../../streaming/contexts';
import { CU_CAMERA_HEIGHT_STEPS, nearestCameraHeightStepIndex } from '../constants';

export type CuCameraHeightSliderVariant = 'quick' | 'world3d';

interface CuCameraHeightSliderProps {
    variant: CuCameraHeightSliderVariant;
}

/**
 * Shared camera-height discrete slider for Quick settings and Settings → 3D world.
 * Quick: ticks stack below the icon rail (same width as track). World3d: ticks under track column.
 */
const CuCameraHeightSlider: React.FC<CuCameraHeightSliderProps> = ({ variant }) => {
    const { cameraHeight, handleCameraHeightChange } = useEnvironment();
    const { t } = useTranslation();
    const idx = nearestCameraHeightStepIndex(cameraHeight);
    const labels = CU_CAMERA_HEIGHT_STEPS.map((s) => t(s.labelKey));

    const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const i = Number(e.target.value);
        if (i >= 0 && i < CU_CAMERA_HEIGHT_STEPS.length) {
            handleCameraHeightChange(CU_CAMERA_HEIGHT_STEPS[i].cameraHeight);
        }
    };

    if (variant === 'quick') {
        return (
            <div className="cu-time-slider-stack">
                <RangeTrackWithIcons
                    railClassName="cu-time-slider-rail cu-time-slider-rail--quick cu-time-slider-rail--camera-height"
                    startIconClassName="cu-time-slider-end-icon cu-time-slider-end-icon--camera-low"
                    endIconClassName="cu-time-slider-end-icon cu-time-slider-end-icon--camera-high"
                    trackWrapClassName="cu-time-slider-track-wrap cu-time-slider-track-wrap--230"
                    trackClassName="cu-time-slider-track-img"
                    trackSrc={SettingsIconAssets.track254}
                    startIcon={SettingsSliderEndIcons.cameraHeightStart}
                    endIcon={SettingsSliderEndIcons.cameraHeightEnd}
                >
                    <input
                        id="cu-quick-camera-height-slider"
                        type="range"
                        className="cu-time-slider cu-time-slider--camera-height"
                        min={0}
                        max={CU_CAMERA_HEIGHT_STEPS.length - 1}
                        step={1}
                        value={idx}
                        onChange={onChange}
                        aria-label={t('settings.cameraHeight')}
                        aria-valuemin={0}
                        aria-valuemax={CU_CAMERA_HEIGHT_STEPS.length - 1}
                        aria-valuenow={idx}
                        aria-valuetext={t(CU_CAMERA_HEIGHT_STEPS[idx].labelKey)}
                    />
                </RangeTrackWithIcons>
                <CuDiscreteSliderTicks labels={labels} className="cu-discrete-slider-ticks--quick" />
            </div>
        );
    }

    return (
        <RangeTrackWithIcons
            railClassName="cu-settings-world3d-camera-slider-rail"
            startIconClassName="cu-settings-world3d-camera-end-icon cu-settings-world3d-camera-end-icon--left"
            endIconClassName="cu-settings-world3d-camera-end-icon cu-settings-world3d-camera-end-icon--right"
            trackWrapClassName="cu-settings-world3d-camera-track-wrap"
            trackClassName="cu-settings-world3d-track-bg"
            trackSrc={SettingsIconAssets.track254}
            startIcon={SettingsSliderEndIcons.cameraHeightStart}
            endIcon={SettingsSliderEndIcons.cameraHeightEnd}
            trackColumnClassName="cu-settings-world3d-camera-track-column"
            belowTrack={
                <CuDiscreteSliderTicks labels={labels} className="cu-discrete-slider-ticks--under-world3d-camera-track" />
            }
        >
            <input
                type="range"
                id="cu-w3d-camera-height-slider"
                className="cu-settings-world3d-range cu-settings-world3d-range--camera-height"
                min={0}
                max={CU_CAMERA_HEIGHT_STEPS.length - 1}
                step={1}
                value={idx}
                onChange={onChange}
                aria-label={t('settings.cameraHeight')}
                aria-valuemin={0}
                aria-valuemax={CU_CAMERA_HEIGHT_STEPS.length - 1}
                aria-valuenow={idx}
                aria-valuetext={t(CU_CAMERA_HEIGHT_STEPS[idx].labelKey)}
            />
        </RangeTrackWithIcons>
    );
};

export default CuCameraHeightSlider;
