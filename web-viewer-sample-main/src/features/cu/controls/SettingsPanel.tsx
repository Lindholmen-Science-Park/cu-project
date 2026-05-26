import React, { useState, useCallback, useEffect, useLayoutEffect, useRef } from 'react';
import { SettingsLanguageId } from '../types';
import {
    THEME_STORAGE_KEY,
    SETTINGS_LANGUAGES,
    getInitialLightMode,
    CU_SETTINGS_TEXT_SIZE_KEY,
    CU_SETTINGS_FULLSCREEN_NARRATION_KEY,
    CU_SETTINGS_NARRATE_DEFAULT_KEY,
    CU_SETTINGS_ENV_VOLUME_KEY,
    CU_SETTINGS_ENVIRONMENT_SOUND_ENABLED_KEY,
    CU_SETTINGS_SOUND_EFFECTS_ENABLED_KEY,
} from '../constants';
import SettingsSwitch from './SettingsSwitch';
import SettingsTrackSwitch from './SettingsTrackSwitch';
import LanguageDropdown from './LanguageDropdown';
import PreferencesGrids from './PreferencesGrids';
import { ThemeCloudSunIcon, ThemeMoonIcon } from '../ThemeAppearanceIcons';
import { useTranslation } from 'react-i18next';
import { sendMessage } from '../../streaming/messaging';
import { aiLanguageFor } from '../../../services/aiLanguage';
import {
    SettingsAboutChevronIcon,
    SettingsEnvTrackDotIcon,
    SettingsMenuListIcon,
    SettingsSpeakerHighIcon,
    SettingsSpeakerLowIcon,
} from './settings-icons/SettingsIcons';
import World3dSettings from './World3dSettings';
import { useModalAccessibility } from '../../streaming/hooks/useModalAccessibility';
import { useSeatSheetForeground } from '../../streaming/hooks/useSeatSheetForeground';
import './SettingsPanel.css';

interface SettingsPanelProps {
    onClose: () => void;
    onBackToMenu: () => void;
}

type SettingsTab = 'general' | 'preferences' | 'world3d';

function readNum(key: string, fallback: number): number {
    if (typeof window === 'undefined') return fallback;
    try {
        const s = window.localStorage.getItem(key);
        if (s == null) return fallback;
        const n = Number(s);
        return Number.isFinite(n) ? n : fallback;
    } catch {
        return fallback;
    }
}

function readBool(key: string, fallback: boolean): boolean {
    if (typeof window === 'undefined') return fallback;
    try {
        const s = window.localStorage.getItem(key);
        if (s === 'true') return true;
        if (s === 'false') return false;
        return fallback;
    } catch {
        return fallback;
    }
}

function persist(key: string, value: string) {
    try {
        window.localStorage.setItem(key, value);
    } catch {
        /* ignore */
    }
}

const SettingsPanel: React.FC<SettingsPanelProps> = ({
    onClose,
    onBackToMenu,
}) => {
    const { t, i18n } = useTranslation();
    const [activeTab, setActiveTab] = useState<SettingsTab>('general');
    const [settingsLightMode, setSettingsLightMode] = useState(getInitialLightMode);
    const isSettingsLightMode = settingsLightMode;
    const [settingsLanguage, setSettingsLanguage] = useState<SettingsLanguageId>(
        () => SETTINGS_LANGUAGES.find((o) => o.i18nCode === i18n.language)?.id ?? 'english',
    );
    const [isAboutExpanded, setIsAboutExpanded] = useState(false);

    const [textSizePct, setTextSizePct] = useState(() =>
        Math.min(115, Math.max(85, readNum(CU_SETTINGS_TEXT_SIZE_KEY, 100))),
    );
    const [fullScreenNarration, setFullScreenNarration] = useState(() =>
        readBool(CU_SETTINGS_FULLSCREEN_NARRATION_KEY, false),
    );
    const [narrateByDefault, setNarrateByDefault] = useState(() =>
        readBool(CU_SETTINGS_NARRATE_DEFAULT_KEY, true),
    );
    const [environmentSoundEnabled, setEnvironmentSoundEnabled] = useState(() =>
        readBool(CU_SETTINGS_ENVIRONMENT_SOUND_ENABLED_KEY, true),
    );
    const [soundEffectsEnabled, setSoundEffectsEnabled] = useState(() =>
        readBool(CU_SETTINGS_SOUND_EFFECTS_ENABLED_KEY, true),
    );
    const [envVolume, setEnvVolume] = useState(() =>
        Math.min(100, Math.max(0, readNum(CU_SETTINGS_ENV_VOLUME_KEY, 70))),
    );

    const dialogRef = useRef<HTMLDivElement>(null);
    const seatSheetForeground = useSeatSheetForeground();
    useModalAccessibility(dialogRef, { enabled: !seatSheetForeground });

    // WCAG 2.1.1 — Escape closes the modal Settings dialog.
    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [onClose]);

    const handleLanguageChange = useCallback(
        (id: SettingsLanguageId) => {
            setSettingsLanguage(id);
            const lang = SETTINGS_LANGUAGES.find((o) => o.id === id);
            sendMessage('ai.agent.setLanguage', { language: aiLanguageFor(lang?.i18nCode) });
            if (lang?.i18nCode) i18n.changeLanguage(lang.i18nCode);
        },
        [i18n],
    );

    useLayoutEffect(() => {
        if (typeof document === 'undefined') return;
        document.documentElement.setAttribute('data-theme', settingsLightMode ? 'light' : 'dark');
        document.documentElement.style.setProperty('--cu-app-font-scale', String(textSizePct / 100));
    }, [settingsLightMode, textSizePct]);

    useEffect(() => {
        try {
            window.localStorage.setItem(THEME_STORAGE_KEY, settingsLightMode ? 'light' : 'dark');
        } catch {
            /* ignore */
        }
    }, [settingsLightMode]);

    useEffect(() => {
        persist(CU_SETTINGS_TEXT_SIZE_KEY, String(textSizePct));
    }, [textSizePct]);

    useEffect(() => {
        persist(CU_SETTINGS_FULLSCREEN_NARRATION_KEY, String(fullScreenNarration));
    }, [fullScreenNarration]);

    useEffect(() => {
        persist(CU_SETTINGS_NARRATE_DEFAULT_KEY, String(narrateByDefault));
    }, [narrateByDefault]);

    useEffect(() => {
        persist(CU_SETTINGS_ENV_VOLUME_KEY, String(envVolume));
    }, [envVolume]);

    useEffect(() => {
        persist(CU_SETTINGS_ENVIRONMENT_SOUND_ENABLED_KEY, String(environmentSoundEnabled));
    }, [environmentSoundEnabled]);

    useEffect(() => {
        persist(CU_SETTINGS_SOUND_EFFECTS_ENABLED_KEY, String(soundEffectsEnabled));
    }, [soundEffectsEnabled]);

    const onTextSizeInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        const v = Number(e.target.value);
        if (Number.isFinite(v)) setTextSizePct(Math.min(115, Math.max(85, v)));
    };

    const onEnvVolumeInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        const v = Number(e.target.value);
        if (Number.isFinite(v)) setEnvVolume(Math.min(100, Math.max(0, v)));
    };

    const useDarkFrost = !isSettingsLightMode && activeTab !== 'world3d';

    return (
        <div
            ref={dialogRef}
            id="cu-settings-dialog"
            className={`cu-settings-frost${useDarkFrost ? ' cu-settings-frost--dark' : ''}${
                activeTab === 'world3d' ? ' cu-settings-frost--world3d-tab' : ''
            }`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="cu-settings-panel-title"
            aria-label={t('settings.title')}
            aria-hidden={seatSheetForeground ? true : undefined}
            inert={seatSheetForeground ? true : undefined}
            onClick={onClose}
        >
            <header className="cu-settings-header-bar" onClick={(e) => e.stopPropagation()}>
                <div className="cu-settings-header-inner">
                    <h1 className="cu-settings-page-title" id="cu-settings-panel-title">
                        {t('settings.title')}
                    </h1>
                    <button
                        type="button"
                        className="cu-hamburger cu-settings-header-hamburger"
                        title={t('settings.backToQuickActions')}
                        aria-label={t('settings.backToControlsMenu')}
                        onClick={(e) => {
                            e.stopPropagation();
                            onBackToMenu();
                        }}
                    >
                        <SettingsMenuListIcon />
                    </button>
                </div>
                <nav className="cu-settings-tabs-wrap" aria-label={t('settings.title')}>
                    <div
                        className="cu-settings-tabs"
                        role="tablist"
                        aria-label={t('settings.title')}
                        // WCAG 2.1.1 — all tabs stay in Tab order; Arrow Left/Right
                        // (and Home/End) also move the selected tab when focus is on the tablist.
                        onKeyDown={(e) => {
                            const order: SettingsTab[] = ['general', 'preferences', 'world3d'];
                            const currentIdx = order.indexOf(activeTab);
                            if (currentIdx < 0) return;
                            let nextIdx = currentIdx;
                            if (e.key === 'ArrowRight') nextIdx = (currentIdx + 1) % order.length;
                            else if (e.key === 'ArrowLeft') nextIdx = (currentIdx - 1 + order.length) % order.length;
                            else if (e.key === 'Home') nextIdx = 0;
                            else if (e.key === 'End') nextIdx = order.length - 1;
                            else return;
                            e.preventDefault();
                            setActiveTab(order[nextIdx]);
                            const target = e.currentTarget.querySelector<HTMLButtonElement>(
                                `[data-tab-id="${order[nextIdx]}"]`,
                            );
                            target?.focus();
                        }}
                    >
                        <button
                            type="button"
                            role="tab"
                            id="cu-settings-tab-general"
                            data-tab-id="general"
                            aria-selected={activeTab === 'general'}
                            aria-controls="cu-settings-panel-general"
                            className={`cu-settings-tab${activeTab === 'general' ? ' cu-settings-tab--active' : ''}`}
                            onClick={() => setActiveTab('general')}
                        >
                            {t('settings.tabGeneral')}
                        </button>
                        <button
                            type="button"
                            role="tab"
                            id="cu-settings-tab-preferences"
                            data-tab-id="preferences"
                            aria-selected={activeTab === 'preferences'}
                            aria-controls="cu-settings-panel-preferences"
                            className={`cu-settings-tab${activeTab === 'preferences' ? ' cu-settings-tab--active' : ''}`}
                            onClick={() => setActiveTab('preferences')}
                        >
                            {t('settings.tabPreferences')}
                        </button>
                        <button
                            type="button"
                            role="tab"
                            id="cu-settings-tab-world3d"
                            data-tab-id="world3d"
                            aria-selected={activeTab === 'world3d'}
                            aria-controls="cu-settings-panel-world3d"
                            className={`cu-settings-tab${activeTab === 'world3d' ? ' cu-settings-tab--active' : ''}`}
                            onClick={() => setActiveTab('world3d')}
                        >
                            {t('settings.tabWorld3d')}
                        </button>
                    </div>
                </nav>
            </header>

            <div className="cu-settings-frost-body" onClick={(e) => e.stopPropagation()}>
                <div
                    className="cu-settings-stack"
                >
                    {activeTab === 'general' && (
                        <div
                            role="tabpanel"
                            id="cu-settings-panel-general"
                            className="cu-settings-tab-panel"
                            aria-labelledby="cu-settings-tab-general"
                        >
                            <section className="cu-settings-section" aria-labelledby="cu-settings-grp-global">
                                <div className="cu-settings-switch-host cu-settings-switch-host--global">
                                    <h2
                                        className="cu-settings-card-title cu-settings-switch-host-title"
                                        id="cu-settings-grp-global"
                                    >
                                        {t('settings.global')}
                                    </h2>
                                    <div className="cu-settings-global-theme-lang">
                                        <SettingsSwitch
                                            id="cu-settings-theme"
                                            label={t('settings.themeAppearance')}
                                            checked={settingsLightMode}
                                            onChange={setSettingsLightMode}
                                            variant="theme"
                                            leftContent={
                                                <>
                                                    <ThemeMoonIcon className="cu-settings-switch-seg-icon" />
                                                    <span className="cu-settings-switch-seg-text">{t('settings.dark')}</span>
                                                </>
                                            }
                                            rightContent={
                                                <>
                                                    <ThemeCloudSunIcon className="cu-settings-switch-seg-icon" />
                                                    <span className="cu-settings-switch-seg-text">{t('settings.light')}</span>
                                                </>
                                            }
                                        />
                                        <LanguageDropdown value={settingsLanguage} onChange={handleLanguageChange} />
                                    </div>
                                </div>
                            </section>

                            <section
                                className="cu-settings-section cu-settings-section--visual"
                                aria-labelledby="cu-settings-grp-visual"
                            >
                                <div className="cu-settings-switch-host cu-settings-switch-host--visual">
                                    <h2 className="cu-settings-card-title cu-settings-switch-host-title" id="cu-settings-grp-visual">
                                        {t('settings.visualSettings')}
                                    </h2>
                                    <div className="cu-settings-slider-block">
                                        <div className="cu-settings-slider-label-row">
                                            <span className="cu-settings-slider-label">{t('settings.textSize')}</span>
                                        </div>
                                        <div className="cu-settings-slider-rail cu-settings-slider-rail--text-size">
                                            <span
                                                className="cu-settings-slider-icon-a cu-settings-slider-icon-a--track-start"
                                                aria-hidden
                                            >
                                                Aa
                                            </span>
                                            <input
                                                type="range"
                                                className="cu-settings-range cu-settings-range--text-size"
                                                min={85}
                                                max={115}
                                                step={1}
                                                value={textSizePct}
                                                onChange={onTextSizeInput}
                                                aria-valuemin={85}
                                                aria-valuemax={115}
                                                aria-valuenow={textSizePct}
                                                aria-valuetext={t('settings.textSizeAria', { pct: textSizePct })}
                                                aria-label={t('settings.textSize')}
                                            />
                                            <span
                                                className="cu-settings-slider-icon-a cu-settings-slider-icon-a--lg cu-settings-slider-icon-a--track-end"
                                                aria-hidden
                                            >
                                                Aa
                                            </span>
                                            <div className="cu-settings-env-track-dots" aria-hidden="true">
                                                <span className="cu-settings-env-track-dot-wrap">
                                                    <SettingsEnvTrackDotIcon />
                                                </span>
                                                <span className="cu-settings-env-track-dot-wrap">
                                                    <SettingsEnvTrackDotIcon />
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="cu-settings-toggle-row">
                                        <span className="cu-settings-toggle-row-label" id="cu-settings-fs-narr-label">
                                            {t('settings.fullScreenNarration')}
                                        </span>
                                        <span className="cu-settings-toggle-row-state" aria-hidden={true}>
                                            {fullScreenNarration ? t('common.on') : t('common.off')}
                                        </span>
                                        <SettingsTrackSwitch
                                            id="cu-settings-fullscreen-narration"
                                            label={t('settings.fullScreenNarration')}
                                            checked={fullScreenNarration}
                                            onChange={setFullScreenNarration}
                                        />
                                    </div>
                                    <div className="cu-settings-toggle-row">
                                        <span className="cu-settings-toggle-row-label" id="cu-settings-narr-default-label">
                                            {t('settings.narrateTextByDefault')}
                                        </span>
                                        <span className="cu-settings-toggle-row-state" aria-hidden={true}>
                                            {narrateByDefault ? t('common.on') : t('common.off')}
                                        </span>
                                        <SettingsTrackSwitch
                                            id="cu-settings-narrate-default"
                                            label={t('settings.narrateTextByDefault')}
                                            checked={narrateByDefault}
                                            onChange={setNarrateByDefault}
                                        />
                                    </div>
                                </div>
                            </section>

                            <section
                                className="cu-settings-section cu-settings-section--audio"
                                aria-labelledby="cu-settings-grp-audio"
                            >
                                <div className="cu-settings-switch-host cu-settings-switch-host--audio">
                                    <h2 className="cu-settings-card-title cu-settings-switch-host-title" id="cu-settings-grp-audio">
                                        {t('settings.audioSettings')}
                                    </h2>
                                    <div
                                        className={`cu-settings-slider-block${
                                            !environmentSoundEnabled ? ' cu-settings-slider-block--disabled' : ''
                                        }`}
                                    >
                                        <div className="cu-settings-slider-label-row">
                                            <span className="cu-settings-slider-label">{t('settings.volume')}</span>
                                        </div>
                                        <div className="cu-settings-slider-rail cu-settings-slider-rail--volume">
                                            <span
                                                className="cu-settings-volume-icon cu-settings-volume-icon--env-start"
                                                aria-hidden
                                            >
                                                <SettingsSpeakerLowIcon />
                                            </span>
                                            <input
                                                type="range"
                                                className="cu-settings-range cu-settings-range--volume"
                                                min={0}
                                                max={100}
                                                step={1}
                                                value={envVolume}
                                                onChange={onEnvVolumeInput}
                                                disabled={!environmentSoundEnabled}
                                                aria-valuemin={0}
                                                aria-valuemax={100}
                                                aria-valuenow={envVolume}
                                                aria-valuetext={t('settings.environmentSoundsAria', { pct: envVolume })}
                                                aria-label={t('settings.environmentSounds')}
                                            />
                                            <span
                                                className="cu-settings-volume-icon cu-settings-volume-icon--env-end"
                                                aria-hidden
                                            >
                                                <SettingsSpeakerHighIcon />
                                            </span>
                                        </div>
                                    </div>
                                    <div className="cu-settings-toggle-row">
                                        <span className="cu-settings-toggle-row-label">{t('settings.environmentSound')}</span>
                                        <span className="cu-settings-toggle-row-state" aria-hidden={true}>
                                            {environmentSoundEnabled ? t('common.on') : t('common.off')}
                                        </span>
                                        <SettingsTrackSwitch
                                            id="cu-settings-environment-sound"
                                            label={t('settings.environmentSound')}
                                            checked={environmentSoundEnabled}
                                            onChange={setEnvironmentSoundEnabled}
                                        />
                                    </div>
                                    <div className="cu-settings-toggle-row">
                                        <span className="cu-settings-toggle-row-label">{t('settings.soundEffects')}</span>
                                        <span className="cu-settings-toggle-row-state" aria-hidden={true}>
                                            {soundEffectsEnabled ? t('common.on') : t('common.off')}
                                        </span>
                                        <SettingsTrackSwitch
                                            id="cu-settings-sound-effects"
                                            label={t('settings.soundEffects')}
                                            checked={soundEffectsEnabled}
                                            onChange={setSoundEffectsEnabled}
                                        />
                                    </div>
                                </div>
                            </section>

                            <section
                                className="cu-settings-section cu-settings-section--about"
                                aria-labelledby="cu-settings-grp-about"
                            >
                                <div className="cu-settings-switch-host cu-settings-about-host">
                                    <button
                                        type="button"
                                        className={`cu-settings-about-trigger${isAboutExpanded ? ' cu-settings-about-trigger--open' : ''}`}
                                        aria-expanded={isAboutExpanded}
                                        aria-controls="cu-settings-about-content"
                                        onClick={() => setIsAboutExpanded((v) => !v)}
                                    >
                                        <span className="cu-settings-about-trigger-label">{t('settings.about')}</span>
                                        <SettingsAboutChevronIcon expanded={isAboutExpanded} />
                                    </button>
                                    {isAboutExpanded && (
                                        <div
                                            id="cu-settings-about-content"
                                            className="cu-settings-about-body"
                                            role="region"
                                            aria-labelledby="cu-settings-grp-about"
                                        >
                                            <dl className="cu-settings-about-list">
                                                <div className="cu-settings-about-row">
                                                    <dt className="cu-settings-about-dt">{t('settings.version')}</dt>
                                                    <dd className="cu-settings-about-dd">0.1</dd>
                                                </div>
                                            </dl>
                                        </div>
                                    )}
                                </div>
                            </section>
                        </div>
                    )}

                    {activeTab === 'preferences' && (
                        <div
                            role="tabpanel"
                            id="cu-settings-panel-preferences"
                            className="cu-settings-tab-panel"
                            aria-labelledby="cu-settings-tab-preferences"
                        >
                            <section className="cu-settings-section cu-settings-section--prefs" aria-labelledby="cu-settings-prefs-heading">
                                <h2 className="cu-settings-sr-only" id="cu-settings-prefs-heading">
                                    {t('settings.tabPreferences')}
                                </h2>
                                <PreferencesGrids />
                            </section>
                        </div>
                    )}

                    {activeTab === 'world3d' && (
                        <div
                            role="tabpanel"
                            id="cu-settings-panel-world3d"
                            className="cu-settings-tab-panel"
                            aria-labelledby="cu-settings-tab-world3d"
                        >
                            <section className="cu-settings-section cu-settings-section--world3d" aria-labelledby="cu-settings-world-heading">
                                <h2 className="cu-settings-sr-only" id="cu-settings-world-heading">
                                    {t('settings.tabWorld3d')}
                                </h2>
                                <World3dSettings />
                            </section>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default SettingsPanel;
