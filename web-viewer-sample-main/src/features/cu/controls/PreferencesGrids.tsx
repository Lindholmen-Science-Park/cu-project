import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import prefEscalator from '@icons/preferences/pref-escalator.svg';
import prefElevator from '@icons/preferences/pref-elevator.svg';
import prefToilet from '@icons/preferences/pref-toilet.svg';
import prefChanging from '@icons/preferences/pref-changing.svg';
import prefCalm from '@icons/preferences/pref-calm.svg';
import prefWheelchair from '@icons/preferences/pref-wheelchair.svg';
import prefCrowded from '@icons/preferences/pref-crowded.svg';
import prefStairs from '@icons/preferences/pref-stairs.svg';
import prefLoud from '@icons/preferences/pref-loud.svg';
import prefStrobe from '@icons/preferences/pref-strobe.svg';

const STORAGE_PREFER = 'cu_settings_prefer_choice';
const STORAGE_AVOID = 'cu_settings_avoid_choices';

type PreferId =
    | 'escalators'
    | 'elevators'
    | 'accessible_toilets'
    | 'changing_tables'
    | 'baby_changing'
    | 'calm_areas'
    | 'wheelchair_access';

type AvoidId = 'crowded_areas' | 'stairs' | 'loud_noises' | 'strobe_lights';

const PREFER_ORDER: PreferId[] = [
    'wheelchair_access',
    'escalators',
    'elevators',
    'accessible_toilets',
    'calm_areas',
    'changing_tables',
    'baby_changing',
];

const AVOID_ORDER: AvoidId[] = ['crowded_areas', 'stairs', 'loud_noises', 'strobe_lights'];

const PREFER_IMG: Record<PreferId, string> = {
    escalators: prefEscalator,
    elevators: prefElevator,
    accessible_toilets: prefToilet,
    changing_tables: prefChanging,
    baby_changing: prefChanging,
    calm_areas: prefCalm,
    wheelchair_access: prefWheelchair,
};

const AVOID_IMG: Record<AvoidId, string> = {
    crowded_areas: prefCrowded,
    stairs: prefStairs,
    loud_noises: prefLoud,
    strobe_lights: prefStrobe,
};

function loadPrefer(): PreferId | null {
    try {
        const r = window.localStorage.getItem(STORAGE_PREFER);
        if (r && PREFER_ORDER.includes(r as PreferId)) return r as PreferId;
    } catch {
        /* ignore */
    }
    return 'elevators';
}

function loadAvoid(): Set<AvoidId> {
    try {
        const r = window.localStorage.getItem(STORAGE_AVOID);
        if (!r) return new Set<AvoidId>(['strobe_lights']);
        const arr = JSON.parse(r) as unknown;
        if (!Array.isArray(arr)) return new Set<AvoidId>(['strobe_lights']);
        return new Set(arr.filter((x): x is AvoidId => AVOID_ORDER.includes(x as AvoidId)));
    } catch {
        return new Set<AvoidId>(['strobe_lights']);
    }
}

const PreferencesGrids: React.FC = () => {
    const { t } = useTranslation();
    const [prefer, setPrefer] = useState<PreferId | null>(loadPrefer);
    const [avoid, setAvoid] = useState<Set<AvoidId>>(loadAvoid);

    useEffect(() => {
        try {
            if (prefer) window.localStorage.setItem(STORAGE_PREFER, prefer);
        } catch {
            /* ignore */
        }
    }, [prefer]);

    useEffect(() => {
        try {
            window.localStorage.setItem(STORAGE_AVOID, JSON.stringify([...avoid]));
        } catch {
            /* ignore */
        }
    }, [avoid]);

    const toggleAvoid = useCallback((id: AvoidId) => {
        setAvoid((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }, []);

    const preferLabel = (id: PreferId) => {
        const keys: Record<PreferId, string> = {
            escalators: 'settings.prefsEscalators',
            elevators: 'settings.prefsElevators',
            accessible_toilets: 'settings.prefsAccessibleToilets',
            changing_tables: 'settings.prefsChangingTables',
            baby_changing: 'settings.prefsBabyChangingTables',
            calm_areas: 'settings.prefsCalmAreas',
            wheelchair_access: 'settings.prefsWheelchairAccess',
        };
        return t(keys[id]);
    };

    const avoidLabel = (id: AvoidId) => {
        const keys: Record<AvoidId, string> = {
            crowded_areas: 'settings.prefsCrowdedAreas',
            stairs: 'settings.prefsStairs',
            loud_noises: 'settings.prefsLoudNoises',
            strobe_lights: 'settings.prefsStrobeLights',
        };
        return t(keys[id]);
    };

    return (
        <div className="cu-settings-prefs-root">
            <section className="cu-settings-prefs-glass" aria-labelledby="cu-settings-prefs-prefer-title">
                <h2 className="cu-settings-prefs-section-title" id="cu-settings-prefs-prefer-title">
                    {t('settings.prefsPreferTitle')}
                </h2>
                <div
                    className="cu-settings-prefs-grid cu-settings-prefs-grid--prefer"
                    role="radiogroup"
                    aria-label={t('settings.prefsPreferTitle')}
                >
                    {PREFER_ORDER.map((id) => {
                        const selected = prefer === id;
                        return (
                            <button
                                key={id}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                className={`cu-settings-prefs-card cu-settings-prefs-card--prefer${selected ? ' cu-settings-prefs-card--selected' : ''}`}
                                onClick={() => setPrefer(id)}
                            >
                                <img
                                    src={PREFER_IMG[id]}
                                    alt=""
                                    width={40}
                                    height={40}
                                    draggable={false}
                                    className="cu-settings-prefs-card-icon-img"
                                />
                                <span className="cu-settings-prefs-card-label">{preferLabel(id)}</span>
                            </button>
                        );
                    })}
                </div>
            </section>

            <section className="cu-settings-prefs-glass" aria-labelledby="cu-settings-prefs-avoid-title">
                <h2 className="cu-settings-prefs-section-title" id="cu-settings-prefs-avoid-title">
                    {t('settings.prefsAvoidTitle')}
                </h2>
                <div className="cu-settings-prefs-grid cu-settings-prefs-grid--avoid" role="group" aria-label={t('settings.prefsAvoidTitle')}>
                    {AVOID_ORDER.map((id) => {
                        const selected = avoid.has(id);
                        return (
                            <button
                                key={id}
                                type="button"
                                aria-pressed={selected}
                                className={`cu-settings-prefs-card cu-settings-prefs-card--avoid${selected ? ' cu-settings-prefs-card--selected' : ''}`}
                                onClick={() => toggleAvoid(id)}
                            >
                                <img
                                    src={AVOID_IMG[id]}
                                    alt=""
                                    width={40}
                                    height={40}
                                    draggable={false}
                                    className="cu-settings-prefs-card-icon-img"
                                />
                                <span className="cu-settings-prefs-card-label">{avoidLabel(id)}</span>
                            </button>
                        );
                    })}
                </div>
            </section>
        </div>
    );
};

export default PreferencesGrids;
