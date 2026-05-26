import React from 'react';

/** Pill track + thumb (Figma): OFF = light purple track, dark thumb left; ON = dark purple track, white thumb right */
export interface SettingsTrackSwitchProps {
    id: string;
    label: string;
    checked: boolean;
    onChange: (next: boolean) => void;
}

const SettingsTrackSwitch: React.FC<SettingsTrackSwitchProps> = ({ id, label, checked, onChange }) => (
    <button
        type="button"
        id={id}
        role="switch"
        aria-checked={checked}
        aria-label={label}
        className={['cu-settings-track-switch', checked && 'cu-settings-track-switch--on'].filter(Boolean).join(' ')}
        onClick={() => onChange(!checked)}
    >
        <span className="cu-settings-track-switch-thumb" aria-hidden />
    </button>
);

export default SettingsTrackSwitch;
