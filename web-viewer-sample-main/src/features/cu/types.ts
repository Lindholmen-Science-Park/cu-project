import React from 'react';

export type CUControlsSearchChipIntent = 'seat' | 'restroom' | 'quiet';

export type SettingsLanguageId = 'english' | 'french' | 'castellano' | 'svenska';

export type WeatherOption = 'sun' | 'rain' | 'fog' | 'snow';

export type SeasonOption = 'summer' | 'spring' | 'autumn' | 'winter';

export type ControlsMenuCardId = 'explore';

export interface SettingsSwitchProps {
    id: string;
    label: string;
    checked: boolean;
    onChange: (next: boolean) => void;
    leftContent?: React.ReactNode;
    rightContent?: React.ReactNode;
    /** Wide Dark/Light theme control; omit for compact OFF/ON rows */
    variant?: 'default' | 'theme';
    /** Hide OFF/ON text inside the pill (use external label/state only) */
    hideSegmentLabels?: boolean;
}

export type NavmeshMovementMode = 'wheelchair' | 'walking';

