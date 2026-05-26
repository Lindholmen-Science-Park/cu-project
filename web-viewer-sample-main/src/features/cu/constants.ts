import { CUControlsSearchChipIntent, SettingsLanguageId } from './types';
import searchChipSeatPng from './search-suggestion-icons/search-chip-seat.png';
import searchChipToiletPng from './search-suggestion-icons/search-chip-toilet.png';
import searchChipQuietPng from './search-suggestion-icons/search-chip-quiet.png';

export const THEME_STORAGE_KEY = 'cuThemeMode';

/** General settings — persisted UI preferences */
export const CU_SETTINGS_TEXT_SIZE_KEY = 'cu.settings.textSizePct';
export const CU_SETTINGS_FULLSCREEN_NARRATION_KEY = 'cu.settings.fullScreenNarration';
export const CU_SETTINGS_NARRATE_DEFAULT_KEY = 'cu.settings.narrateTextByDefault';
export const CU_SETTINGS_ENV_VOLUME_KEY = 'cu.settings.environmentVolume';
export const CU_SETTINGS_ENVIRONMENT_SOUND_ENABLED_KEY = 'cu.settings.environmentSoundEnabled';
export const CU_SETTINGS_SOUND_EFFECTS_ENABLED_KEY = 'cu.settings.soundEffectsEnabled';
export const MINUTES_PER_DAY = 24 * 60;
export const DEFAULT_TIME_OF_DAY_MINUTES = 12 * 60;
export const CU_SLIDER_MIN_MINUTES = 8 * 60;   // 08:00
export const CU_SLIDER_MAX_MINUTES = 24 * 60;   // 00:00 (midnight)

/** i18n keys for time-of-day tick labels under the slider (Quick vs Settings → 3D world). */
export const CU_TIME_OF_DAY_TICK_KEYS_QUICK = [
    'people.timeTick08',
    'people.timeTick12',
    'people.timeTick16',
    'people.timeTick19',
    'people.timeTick00',
] as const;

export const CU_TIME_OF_DAY_TICK_KEYS_WORLD3D = [
    'settings.timeOfDay0800',
    'settings.timeOfDay1200',
    'settings.timeOfDay1600',
    'settings.timeOfDay1900',
    'settings.timeOfDay0000',
] as const;

/**
 * Five discrete character heights shown in Quick settings and 3D world settings.
 * Camera height = character height − 15 cm (eye offset); values are what we send to Kit (cm).
 */
export const CU_CAMERA_HEIGHT_STEPS = [
    { labelKey: 'settings.cameraHeightTick1m', cameraHeight: 85 },
    { labelKey: 'settings.cameraHeightTick1m20', cameraHeight: 105 },
    { labelKey: 'settings.cameraHeightTick1m40', cameraHeight: 125 },
    { labelKey: 'settings.cameraHeightTick1m70', cameraHeight: 155 },
    { labelKey: 'settings.cameraHeightTick1m95', cameraHeight: 180 },
] as const;

export function nearestCameraHeightStepIndex(cameraHeightCm: number): number {
    return CU_CAMERA_HEIGHT_STEPS.reduce(
        (best, step, i) =>
            Math.abs(step.cameraHeight - cameraHeightCm) <
            Math.abs(CU_CAMERA_HEIGHT_STEPS[best].cameraHeight - cameraHeightCm)
                ? i
                : best,
        0,
    );
}

export const SEARCH_CHIP_FIND_SEAT = 'search.findSeat';
export const SEARCH_CHIP_FIND_TOILET = 'search.findToilet';
export const SEARCH_CHIP_FIND_QUIET = 'search.findQuietArea';

export const SEARCH_SUGGESTION_CHIPS: ReadonlyArray<{
    labelKey: string;
    intent: CUControlsSearchChipIntent;
    icon: string;
    comingSoon?: boolean;
}> = [
    { labelKey: SEARCH_CHIP_FIND_SEAT, intent: 'seat', icon: searchChipSeatPng },
    { labelKey: SEARCH_CHIP_FIND_TOILET, intent: 'restroom', icon: searchChipToiletPng },
    { labelKey: SEARCH_CHIP_FIND_QUIET, intent: 'quiet', icon: searchChipQuietPng },
];

export const SETTINGS_LANGUAGES: ReadonlyArray<{
    id: SettingsLanguageId;
    label: string;
    code: string;
    i18nCode?: string;
}> = [
    { id: 'english', label: 'English', code: 'EN', i18nCode: 'en' },
    { id: 'french', label: 'Français', code: 'FR', i18nCode: 'fr' },
    { id: 'castellano', label: 'Español', code: 'ES', i18nCode: 'es' },
    { id: 'svenska', label: 'Svenska', code: 'SV', i18nCode: 'sv' },
];

export function formatClockFromMinutes(totalMinutes: number): string {
    const m = Math.max(0, Math.min(MINUTES_PER_DAY - 1, Math.round(totalMinutes)));
    const h = Math.floor(m / 60);
    const min = m % 60;
    return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}

/** e.g. 12h00 — used for time-of-day slider ARIA and Figma-style tick labels */
export function formatTimeOfDayLabelHh(totalMinutes: number): string {
    const m = Math.max(0, Math.min(MINUTES_PER_DAY - 1, Math.round(totalMinutes)));
    const h = Math.floor(m / 60);
    return `${String(h).padStart(2, '0')}h00`;
}

export function getInitialLightMode(): boolean {
    if (typeof window !== 'undefined') {
        try {
            const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
            if (saved === 'light') return true;
            if (saved === 'dark') return false;
        } catch {
            /* ignore */
        }
    }
    return true;
}

export function settingsLanguageLabel(id: SettingsLanguageId): string {
    return SETTINGS_LANGUAGES.find((o) => o.id === id)?.label ?? SETTINGS_LANGUAGES[0].label;
}

export function settingsLanguageCode(id: SettingsLanguageId): string {
    return SETTINGS_LANGUAGES.find((o) => o.id === id)?.code ?? SETTINGS_LANGUAGES[0].code;
}
