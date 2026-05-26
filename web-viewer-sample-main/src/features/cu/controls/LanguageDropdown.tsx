import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { SettingsLanguageId } from '../types';
import { SETTINGS_LANGUAGES, settingsLanguageLabel, settingsLanguageCode } from '../constants';
import { useTranslation } from 'react-i18next';
import './LanguageDropdown.css';
import { SettingsGlobeIcon, SettingsLangCaretIcon } from './settings-icons/SettingsIcons';

interface LanguageDropdownProps {
    value: SettingsLanguageId;
    onChange: (id: SettingsLanguageId) => void;
}

/**
 * WCAG 2.1.1 — listbox combobox: Tab reaches trigger and each option when open;
 * ↑/↓ also move highlight. Used in onboarding and settings.
 */
const LanguageDropdown: React.FC<LanguageDropdownProps> = ({ value, onChange }) => {
    const [open, setOpen] = useState(false);
    const { t } = useTranslation();
    const triggerRef = useRef<HTMLButtonElement>(null);
    const anchorRef = useRef<HTMLDivElement>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);

    const reactId = useId();
    const listId = `cu-settings-lang-listbox-${reactId}`;
    const triggerId = `cu-settings-lang-trigger-${reactId}`;
    const optionId = (id: string) => `cu-lang-opt-${reactId}-${id}`;

    const selectedIdx = Math.max(0, SETTINGS_LANGUAGES.findIndex((o) => o.id === value));
    const [activeIdx, setActiveIdx] = useState<number>(selectedIdx);

    const focusOption = useCallback((idx: number) => {
        const last = SETTINGS_LANGUAGES.length - 1;
        const clamped = Math.max(0, Math.min(last, idx));
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
        const opt = SETTINGS_LANGUAGES[idx];
        if (!opt) return;
        onChange(opt.id);
        setOpen(false);
        triggerRef.current?.focus();
    };

    const onTriggerKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            e.stopPropagation();
            if (!open) {
                setOpen(true);
            } else {
                focusOption(selectedIdx);
            }
            return;
        }
        if (e.key === 'ArrowUp' && open) {
            e.preventDefault();
            e.stopPropagation();
            focusOption(selectedIdx);
            return;
        }
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            e.stopPropagation();
            if (!open) {
                setOpen(true);
            } else {
                focusOption(selectedIdx);
            }
        }
    };

    const onOptionKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, idx: number) => {
        const last = SETTINGS_LANGUAGES.length - 1;
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                e.stopPropagation();
                focusOption(idx + 1);
                return;
            case 'ArrowUp':
                e.preventDefault();
                e.stopPropagation();
                focusOption(idx - 1);
                return;
            case 'Home':
                e.preventDefault();
                e.stopPropagation();
                focusOption(0);
                return;
            case 'End':
                e.preventDefault();
                e.stopPropagation();
                focusOption(last);
                return;
            case 'Enter':
            case ' ':
                e.preventDefault();
                e.stopPropagation();
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

    return (
        <div className="Dropdown_Language_LIGHT">
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
                    aria-label={`${t('onboarding.selectLanguage')}: ${settingsLanguageLabel(value)} (${settingsLanguageCode(value)})`}
                    aria-haspopup="listbox"
                    aria-expanded={open}
                    aria-controls={open ? listId : undefined}
                    onClick={() => setOpen((v) => !v)}
                    onKeyDown={onTriggerKeyDown}
                >
                    <span className="cu-lang-dropdown-trigger-main">
                        <SettingsGlobeIcon />
                        <span className="cu-lang-dropdown-value-row">
                            <span className="cu-lang-dropdown-value">{settingsLanguageLabel(value)}</span>
                            <span className="cu-lang-dropdown-code" aria-hidden>
                                {settingsLanguageCode(value)}
                            </span>
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
                        aria-label={t('onboarding.selectLanguage')}
                    >
                        {SETTINGS_LANGUAGES.map((opt, idx) => {
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
                                    className={`cu-lang-dropdown-option${selected ? ' cu-lang-dropdown-option--selected' : ''}${active ? ' cu-lang-dropdown-option--active' : ''}`}
                                    title={opt.label}
                                    onFocus={() => setActiveIdx(idx)}
                                    onMouseEnter={() => setActiveIdx(idx)}
                                    onClick={() => commit(idx)}
                                    onKeyDown={(e) => onOptionKeyDown(e, idx)}
                                >
                                    <span className="cu-lang-dropdown-option-name">{opt.label}</span>
                                    <span className="cu-lang-dropdown-code">{opt.code}</span>
                                </button>
                            );
                        })}
                    </div>
                ) : null}
            </div>
        </div>
    );
};

export default LanguageDropdown;
