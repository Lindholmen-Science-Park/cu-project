import React from 'react';
import { useTranslation } from 'react-i18next';
import { SettingsSwitchProps } from '../types';

/** OFF/ON segmented toggle */
const SettingsSwitch: React.FC<SettingsSwitchProps> = ({
    id,
    label,
    checked,
    onChange,
    leftContent,
    rightContent,
    variant = 'default',
    hideSegmentLabels = false,
}) => {
    const { t } = useTranslation();
    const rich = !hideSegmentLabels && Boolean(leftContent ?? rightContent);
    const segClass = hideSegmentLabels
        ? 'cu-settings-switch-seg cu-settings-switch-seg--blank'
        : rich
          ? 'cu-settings-switch-seg cu-settings-switch-seg--rich'
          : 'cu-settings-switch-seg';
    return (
        <button
            type="button"
            id={id}
            role="switch"
            aria-checked={checked}
            aria-label={label}
            className={[
                'cu-settings-switch',
                variant === 'theme' && 'cu-settings-switch--theme',
                hideSegmentLabels && 'cu-settings-switch--no-seg-text',
                checked && 'cu-settings-switch--on',
            ]
                .filter(Boolean)
                .join(' ')}
            onClick={() => onChange(!checked)}
        >
            <span className="cu-settings-switch-highlight" aria-hidden="true" />
            <span className={segClass} aria-hidden="true">
                {hideSegmentLabels ? '\u00A0' : leftContent ?? t('common.off')}
            </span>
            <span className={segClass} aria-hidden="true">
                {hideSegmentLabels ? '\u00A0' : rightContent ?? t('common.on')}
            </span>
        </button>
    );
};

export default SettingsSwitch;
