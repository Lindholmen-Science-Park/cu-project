import React from 'react';
import { useTranslation } from 'react-i18next';
import SettingsTrackSwitch from './SettingsTrackSwitch';
import CuCameraHeightSlider from './CuCameraHeightSlider';
import CuTimeOfDaySlider from './CuTimeOfDaySlider';
import { SettingsIconAssets } from './settings-icons/SettingsIcons';
import { useControl, useNavigation } from '../../streaming/contexts';

const World3dSettings: React.FC = () => {
    const { peopleVisible, handlePeopleToggle, poiMarkersVisible, handlePoiMarkersToggle } = useControl();
    const { t } = useTranslation();

    // "Exploring mode" is the user-facing label for the NavMesh walking /
    // wheelchair mode owned by `useNavmeshCore`. Reading + writing through
    // the shared `useNavigation` context keeps the CU radio in lockstep with
    // the dev sidebar's Walking/Wheelchair button group, the seat-navigate
    // CU bottom-sheet tabs, and Kit's NavMesh state. Kit persists the mode
    // for the lifetime of its process and rehydrates the browser via the
    // `worldStateSync` snapshot on connect/reconnect, so this control needs
    // no localStorage of its own (see `world-state-sync.mdc`).
    const { navmeshMode, handleNavmeshModeChange } = useNavigation();

    return (
        <div className="cu-settings-world3d">
            <section
                className="cu-settings-world3d-card cu-settings-world3d-card--time-of-day"
                aria-labelledby="cu-w3d-time-title"
            >
                <h3 className="cu-settings-world3d-card-title" id="cu-w3d-time-title">
                    {t('settings.timeOfDay')}
                </h3>
                <CuTimeOfDaySlider variant="world3d" />
            </section>

            <section className="cu-settings-world3d-card cu-settings-world3d-card--camera-height" aria-labelledby="cu-w3d-camera-title">
                <h3 className="cu-settings-world3d-card-title" id="cu-w3d-camera-title">
                    {t('settings.cameraHeight')}
                </h3>
                <div className="cu-settings-world3d-camera-slider-block" role="group" aria-labelledby="cu-w3d-camera-title">
                    <div className="cu-settings-world3d-camera-slider-row">
                        <CuCameraHeightSlider variant="world3d" />
                    </div>
                </div>
            </section>

            <section
                className="cu-settings-world3d-card cu-settings-world3d-card--display"
                aria-labelledby="cu-w3d-display-title"
            >
                <h3 className="cu-settings-world3d-card-title" id="cu-w3d-display-title">
                    {t('settings.display')}
                </h3>
                <div className="cu-settings-world3d-toggle-stack">
                    <div className="cu-settings-toggle-row">
                        <span className="cu-settings-toggle-row-label" id="cu-w3d-crowd-lbl">
                            {t('settings.displayCrowd')}
                        </span>
                        <span className="cu-settings-toggle-row-state" aria-hidden={true}>
                            {peopleVisible ? t('common.on') : t('common.off')}
                        </span>
                        <SettingsTrackSwitch
                            id="cu-w3d-crowd"
                            label={t('settings.displayCrowd')}
                            checked={peopleVisible}
                            onChange={(next) => {
                                if (next !== peopleVisible) handlePeopleToggle();
                            }}
                        />
                    </div>
                    <div className="cu-settings-toggle-row">
                        <span className="cu-settings-toggle-row-label" id="cu-w3d-signs-lbl">
                            {t('settings.showSigns')}
                        </span>
                        <span className="cu-settings-toggle-row-state" aria-hidden={true}>
                            {poiMarkersVisible ? t('common.on') : t('common.off')}
                        </span>
                        <SettingsTrackSwitch
                            id="cu-w3d-signs"
                            label={t('settings.showSigns')}
                            checked={poiMarkersVisible}
                            onChange={(next) => {
                                if (next !== poiMarkersVisible) handlePoiMarkersToggle();
                            }}
                        />
                    </div>
                </div>
            </section>

            <section
                className="cu-settings-world3d-card cu-settings-world3d-card--exploring-mode"
                aria-labelledby="cu-w3d-explore-title"
            >
                <h3 className="cu-settings-world3d-card-title" id="cu-w3d-explore-title">
                    {t('settings.exploringMode')}
                </h3>
                <div className="cu-settings-world3d-explore" role="radiogroup" aria-label={t('settings.exploringMode')}>
                    <button
                        type="button"
                        role="radio"
                        aria-checked={navmeshMode === 'walking'}
                        className={`cu-settings-world3d-explore-btn${navmeshMode === 'walking' ? ' cu-settings-world3d-explore-btn--active' : ''}`}
                        onClick={() => handleNavmeshModeChange('walking')}
                    >
                        <img src={SettingsIconAssets.personWalkExplore} alt="" width={22} height={22} className="cu-settings-world3d-explore-btn-icon" draggable={false} />
                        <span className="cu-settings-world3d-explore-btn-label">{t('settings.walking')}</span>
                    </button>
                    <button
                        type="button"
                        role="radio"
                        aria-checked={navmeshMode === 'wheelchair'}
                        className={`cu-settings-world3d-explore-btn${navmeshMode === 'wheelchair' ? ' cu-settings-world3d-explore-btn--active' : ''}`}
                        onClick={() => handleNavmeshModeChange('wheelchair')}
                    >
                        <img src={SettingsIconAssets.wheelchairAccessible} alt="" width={22} height={22} className="cu-settings-world3d-explore-btn-icon" draggable={false} />
                        <span className="cu-settings-world3d-explore-btn-label">{t('settings.wheelchair')}</span>
                    </button>
                </div>
            </section>
        </div>
    );
};

export default World3dSettings;
