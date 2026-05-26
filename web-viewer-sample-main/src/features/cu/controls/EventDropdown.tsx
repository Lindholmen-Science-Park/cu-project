import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import './LanguageDropdown.css';
import './EventDropdown.css';
import { SettingsEventCalendarIcon, SettingsLangCaretIcon } from './settings-icons/SettingsIcons';

/** Placeholder IDs until Kit / world-state wiring exists */
export type QuickSettingsEventId = 'none' | 'horse_show_2026' | 'hockey';

const QUICK_SETTINGS_EVENT_IDS: readonly QuickSettingsEventId[] = ['none', 'horse_show_2026', 'hockey'];

function eventLabelKey(id: QuickSettingsEventId): string {
    switch (id) {
        case 'none':
            return 'people.eventNone';
        case 'horse_show_2026':
            return 'people.eventHorseShow2026';
        case 'hockey':
            return 'people.eventHockey';
        default:
            return 'people.eventNone';
    }
}

/**
 * Quick settings event selector — listbox with Tab between options (and arrow keys).
 * Selection is local UI state only until backend integration is added.
 */
interface EventDropdownProps {
    /** Visible label id from parent (WCAG 3.3.2). */
    labelId?: string;
}

const EventDropdown: React.FC<EventDropdownProps> = ({ labelId }) => {
    const [open, setOpen] = useState(false);
    const [value, setValue] = useState<QuickSettingsEventId>('none');
    const { t } = useTranslation();
    const triggerRef = useRef<HTMLButtonElement>(null);
    const anchorRef = useRef<HTMLDivElement>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);

    const reactId = useId();
    const listId = `cu-quick-event-listbox-${reactId}`;
    const triggerId = `cu-quick-event-trigger-${reactId}`;
    const optionId = (id: string) => `cu-quick-event-opt-${reactId}-${id}`;

    const selectedIdx = Math.max(0, QUICK_SETTINGS_EVENT_IDS.indexOf(value));
    const [activeIdx, setActiveIdx] = useState<number>(selectedIdx);

    const focusOption = useCallback((idx: number) => {
        const clamped = Math.max(0, Math.min(QUICK_SETTINGS_EVENT_IDS.length - 1, idx));
        setActiveIdx(clamped);
        optionRefs.current[clamped]?.focus({ preventScroll: true });
    }, []);

    useEffect(() => {
        if (!open) return;
        const raf = requestAnimationFrame(() => focusOption(selectedIdx));
        return () => cancelAnimationFrame(raf);
    }, [open, selectedIdx, focusOption]);

    useEffect(() => {
        if (!open) return;
        const onClickAway = (e: MouseEvent) => {
            const target = e.target as Node | null;
            if (
                target &&
                !triggerRef.current?.contains(target) &&
                !listRef.current?.contains(target)
            ) {
                setOpen(false);
            }
        };
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                setOpen(false);
                triggerRef.current?.focus();
            }
        };
        window.addEventListener('mousedown', onClickAway);
        window.addEventListener('keydown', onKey, true);
        return () => {
            window.removeEventListener('mousedown', onClickAway);
            window.removeEventListener('keydown', onKey, true);
        };
    }, [open]);

    useEffect(() => {
        if (!open) return;
        const anchor = anchorRef.current;
        if (!anchor) return;
        const onFocusOut = (e: FocusEvent) => {
            const next = e.relatedTarget as Node | null;
            if (next && anchor.contains(next)) return;
            setOpen(false);
        };
        anchor.addEventListener('focusout', onFocusOut);
        return () => anchor.removeEventListener('focusout', onFocusOut);
    }, [open]);

    const commit = (idx: number) => {
        const opt = QUICK_SETTINGS_EVENT_IDS[idx];
        if (!opt) return;
        setValue(opt);
        setOpen(false);
        triggerRef.current?.focus();
    };

    const onTriggerKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (!open) {
                setOpen(true);
            } else {
                focusOption(selectedIdx);
            }
            return;
        }
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (!open) {
                setOpen(true);
            } else {
                focusOption(selectedIdx);
            }
        }
    };

    const onOptionKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, idx: number) => {
        const last = QUICK_SETTINGS_EVENT_IDS.length - 1;
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                focusOption(idx + 1);
                return;
            case 'ArrowUp':
                e.preventDefault();
                focusOption(idx - 1);
                return;
            case 'Home':
                e.preventDefault();
                focusOption(0);
                return;
            case 'End':
                e.preventDefault();
                focusOption(last);
                return;
            case 'Enter':
            case ' ':
                e.preventDefault();
                commit(idx);
                return;
            case 'Escape':
                e.preventDefault();
                e.stopPropagation();
                setOpen(false);
                triggerRef.current?.focus();
                return;
            default:
                return;
        }
    };

    const triggerDisplayLabel =
        value === 'none' ? t('people.selectEvent') : t(eventLabelKey(value));
    const triggerAriaLabel =
        value === 'none'
            ? t('people.selectEvent')
            : `${t('people.selectEvent')}: ${t(eventLabelKey(value))}`;
    const options = QUICK_SETTINGS_EVENT_IDS.map((id) => ({
        id,
        label: t(eventLabelKey(id)),
    }));

    return (
        <div className="Dropdown_Language_LIGHT cu-event-dropdown-wrap">
            <div
                ref={anchorRef}
                className={`cu-lang-dropdown-anchor${open ? ' cu-lang-dropdown-anchor--open' : ''}`}
            >
                <button
                    ref={triggerRef}
                    type="button"
                    id={triggerId}
                    className="cu-lang-dropdown-trigger"
                    tabIndex={0}
                    aria-label={labelId ? undefined : triggerAriaLabel}
                    aria-labelledby={labelId}
                    aria-haspopup="listbox"
                    aria-expanded={open}
                    aria-controls={open ? listId : undefined}
                    onClick={() => setOpen((v) => !v)}
                    onKeyDown={onTriggerKeyDown}
                >
                    <span className="cu-lang-dropdown-trigger-main">
                        <SettingsEventCalendarIcon />
                        <span className="cu-lang-dropdown-value-row cu-event-dropdown-value-row">
                            <span className="cu-lang-dropdown-value">{triggerDisplayLabel}</span>
                        </span>
                    </span>
                    <SettingsLangCaretIcon open={open} />
                </button>
                {open ? (
                    <div
                        ref={listRef}
                        id={listId}
                        role="listbox"
                        className="cu-lang-dropdown-list"
                        aria-label={t('people.selectEvent')}
                    >
                        {options.map((opt, idx) => {
                            const selected = value === opt.id;
                            const active = idx === activeIdx;
                            return (
                                <button
                                    key={opt.id}
                                    ref={(el) => {
                                        optionRefs.current[idx] = el;
                                    }}
                                    type="button"
                                    id={optionId(opt.id)}
                                    role="option"
                                    tabIndex={0}
                                    aria-selected={selected}
                                    className={`cu-lang-dropdown-option cu-event-dropdown-option${selected ? ' cu-lang-dropdown-option--selected' : ''}${active ? ' cu-lang-dropdown-option--active' : ''}`}
                                    aria-label={opt.label}
                                    onFocus={() => setActiveIdx(idx)}
                                    onMouseEnter={() => setActiveIdx(idx)}
                                    onClick={() => commit(idx)}
                                    onKeyDown={(e) => onOptionKeyDown(e, idx)}
                                >
                                    <span className="cu-lang-dropdown-option-name">{opt.label}</span>
                                </button>
                            );
                        })}
                    </div>
                ) : null}
            </div>
        </div>
    );
};

export default EventDropdown;
