import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SettingsLangCaretIcon } from '../../../../cu/controls/settings-icons/SettingsIcons';
import '../../../../cu/controls/LanguageDropdown.css';

/**
 * Generic Section/Row/Seat dropdown. Re-uses the language-dropdown trigger /
 * list chrome (`cu-seat-panel__section-lang-dropdown` styles) so all three
 * seat fields look like one visual rhythm.
 *
 * The component is intentionally dumb: it renders the supplied `options` list
 * verbatim and does not know about cascading or validation -- the parent owns
 * filtering (Section → Row → Seat) and value reset on change.
 *
 * Keyboard support (matches native <select> conventions):
 *  - Printable character: type-ahead jump to first option starting with the
 *    buffered string (resets after 700 ms idle). Opens the list if closed.
 *  - ArrowDown / ArrowUp: move the active highlight (wraps).
 *  - Home / End: jump to first / last option.
 *  - Enter / Space: open if closed, otherwise commit the active option.
 *  - Escape: close.
 */
export interface SeatChoiceDropdownProps {
    /** id of the trigger button (also drives the listbox aria-controls). */
    id: string;
    /** id of the visible <label> (WCAG 3.3.2 / 4.1.2). */
    labelId: string;
    /** Input name for programmatic purpose (WCAG 1.3.5 — no HTML token for stadium seats). */
    inputName: string;
    /** autocomplete token when applicable; use `off` for custom venue fields. */
    autoComplete?: string;
    /** ids of hint/error elements (space-separated) for aria-describedby. */
    describedBy?: string;
    /** Currently selected value (must be a member of `options` to highlight it). */
    value: string;
    /** Visible options. */
    options: readonly string[];
    /** Placeholder shown when `value` is empty. */
    placeholder: string;
    /** Accessible name for the listbox (visible label is rendered by the parent). */
    ariaLabel: string;
    /** Disable the trigger entirely. */
    disabled?: boolean;
    /** Apply error styling (red border + box-shadow). */
    error?: boolean;
    /** Called with the chosen option string. */
    onChange: (value: string) => void;
    /** Bubble keyboard events from the trigger up to the form (`Enter` to submit). */
    onKeyDown?: (e: React.KeyboardEvent) => void;
    /** Per-option label override (default identity). Useful for "Row 4" vs "4". */
    formatOption?: (value: string) => string;
    /** Per-trigger label override (default identity). */
    formatTrigger?: (value: string) => string;
}

const TYPEAHEAD_RESET_MS = 700;

const SeatChoiceDropdown: React.FC<SeatChoiceDropdownProps> = ({
    id,
    labelId,
    inputName,
    autoComplete = 'off',
    describedBy,
    value,
    options,
    placeholder,
    ariaLabel,
    disabled = false,
    error = false,
    onChange,
    onKeyDown,
    formatOption,
    formatTrigger,
}) => {
    const [open, setOpen] = useState(false);
    const [activeIndex, setActiveIndex] = useState<number | null>(null);
    const anchorRef = useRef<HTMLDivElement>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
    const searchBufferRef = useRef<string>('');
    const searchTimerRef = useRef<number | null>(null);
    const listId = `${id}-listbox`;

    /** Stable upper-cased option list for case-insensitive type-ahead search. */
    const upperOptions = useMemo(() => options.map((o) => o.toUpperCase()), [options]);

    /** Reset transient state when options change or the popover closes. */
    useEffect(() => {
        if (!open) {
            setActiveIndex(null);
            searchBufferRef.current = '';
            if (searchTimerRef.current !== null) {
                window.clearTimeout(searchTimerRef.current);
                searchTimerRef.current = null;
            }
        }
    }, [open]);

    /** Clear search buffer on unmount. */
    useEffect(() => {
        return () => {
            if (searchTimerRef.current !== null) {
                window.clearTimeout(searchTimerRef.current);
            }
        };
    }, []);

    const focusOptionAt = useCallback((idx: number) => {
        const last = options.length - 1;
        const clamped = Math.max(0, Math.min(last, idx));
        setActiveIndex(clamped);
        optionRefs.current[clamped]?.focus({ preventScroll: true });
    }, [options.length]);

    /** When opening, seed highlight and move focus into the list (WCAG 2.4.3). */
    useEffect(() => {
        if (!open) return;
        const initial = value ? options.indexOf(value) : -1;
        const idx = initial >= 0 ? initial : (options.length > 0 ? 0 : null);
        setActiveIndex(idx);
        const el = listRef.current;
        if (el) el.scrollTop = 0;
        if (idx !== null) {
            const raf = requestAnimationFrame(() => focusOptionAt(idx));
            return () => cancelAnimationFrame(raf);
        }
    }, [open, options, value, focusOptionAt]);

    /** Keep the active option scrolled into view as the highlight moves. */
    useEffect(() => {
        if (!open || activeIndex === null) return;
        const node = optionRefs.current[activeIndex];
        if (node) node.scrollIntoView({ block: 'nearest' });
    }, [open, activeIndex]);

    useEffect(() => {
        if (!open) return;
        const onDoc = (e: MouseEvent) => {
            if (anchorRef.current && !anchorRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', onDoc);
        return () => document.removeEventListener('mousedown', onDoc);
    }, [open]);

    /**
     * Document-level Escape safety net for the rare case focus drifts off the
     * trigger while the popover is open (e.g. mouse interactions that move
     * focus to an option button before close commits).
     */
    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setOpen(false);
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [open]);

    const findMatchIndex = useCallback(
        (needle: string, startFrom = 0): number => {
            if (!needle || upperOptions.length === 0) return -1;
            const len = upperOptions.length;
            for (let i = 0; i < len; i++) {
                const idx = (startFrom + i) % len;
                if (upperOptions[idx].startsWith(needle)) return idx;
            }
            return -1;
        },
        [upperOptions],
    );

    const scheduleSearchReset = useCallback(() => {
        if (searchTimerRef.current !== null) {
            window.clearTimeout(searchTimerRef.current);
        }
        searchTimerRef.current = window.setTimeout(() => {
            searchBufferRef.current = '';
            searchTimerRef.current = null;
        }, TYPEAHEAD_RESET_MS);
    }, []);

    /**
     * Append `char` to the type-ahead buffer and move the active highlight to
     * the first matching option. If the buffer is a single repeated character
     * (e.g. "A" then "A"), advance to the next option starting with that char
     * — same behaviour as a native <select>.
     */
    const handleTypeahead = useCallback(
        (char: string) => {
            const upperChar = char.toUpperCase();
            const buffer = searchBufferRef.current;
            const isRepeat = buffer.length === 1 && buffer === upperChar;
            const nextBuffer = isRepeat ? upperChar : buffer + upperChar;
            searchBufferRef.current = nextBuffer;
            scheduleSearchReset();

            const startFrom = isRepeat
                ? ((activeIndex ?? -1) + 1) % Math.max(options.length, 1)
                : 0;
            const matchIndex = findMatchIndex(nextBuffer, startFrom);
            if (matchIndex >= 0) {
                setActiveIndex(matchIndex);
            }
        },
        [activeIndex, findMatchIndex, options.length, scheduleSearchReset],
    );

    const commitActive = useCallback(() => {
        if (activeIndex === null) return false;
        const opt = options[activeIndex];
        if (opt === undefined) return false;
        onChange(opt);
        setOpen(false);
        return true;
    }, [activeIndex, onChange, options]);

    const triggerText = value ? (formatTrigger ? formatTrigger(value) : value) : placeholder;
    /** Disable trigger when options list is empty so users can't open an empty popover. */
    const triggerDisabled = disabled || options.length === 0;
    /** Mirror to a ref so the (memoised) keydown handler always sees the latest value. */
    const triggerDisabledRef = useRef(triggerDisabled);
    triggerDisabledRef.current = triggerDisabled;

    const activeId = activeIndex !== null ? `${id}-opt-${activeIndex}` : undefined;

    const handleTriggerKeyDown = useCallback(
        (e: React.KeyboardEvent<HTMLButtonElement>) => {
            if (triggerDisabledRef.current) {
                onKeyDown?.(e);
                return;
            }

            const key = e.key;

            if (key === 'Escape') {
                if (open) {
                    e.preventDefault();
                    e.stopPropagation();
                    setOpen(false);
                    return;
                }
            }

            if (key === 'ArrowDown' || key === 'ArrowUp') {
                e.preventDefault();
                if (!open) {
                    setOpen(true);
                    return;
                }
                if (options.length === 0) return;
                setActiveIndex((prev) => {
                    const base = prev ?? -1;
                    const delta = key === 'ArrowDown' ? 1 : -1;
                    const next = (base + delta + options.length) % options.length;
                    return next;
                });
                return;
            }

            if (key === 'Home' || key === 'End') {
                if (!open || options.length === 0) return;
                e.preventDefault();
                setActiveIndex(key === 'Home' ? 0 : options.length - 1);
                return;
            }

            if (key === 'Enter' || key === ' ' || key === 'Spacebar') {
                if (!open) {
                    if (key === ' ' || key === 'Spacebar') {
                        e.preventDefault();
                        setOpen(true);
                        return;
                    }
                    onKeyDown?.(e);
                    return;
                }
                e.preventDefault();
                e.stopPropagation();
                commitActive();
                return;
            }

            // Type-ahead: any single printable character (letters, digits, etc.)
            // without modifier keys. We deliberately ignore Tab/Shift/Ctrl/etc.
            if (
                key.length === 1
                && !e.ctrlKey
                && !e.metaKey
                && !e.altKey
            ) {
                e.preventDefault();
                if (!open) setOpen(true);
                handleTypeahead(key);
                return;
            }

            onKeyDown?.(e);
        },
        [open, options.length, commitActive, handleTypeahead, onKeyDown],
    );

    return (
        <div
            className={`Dropdown_Language_LIGHT cu-seat-panel__section-lang-dropdown${error ? ' cu-seat-panel__section-lang-dropdown--error' : ''}${triggerDisabled ? ' cu-seat-panel__section-lang-dropdown--disabled' : ''}`}
        >
            <div
                ref={anchorRef}
                className={`cu-lang-dropdown-anchor${open ? ' cu-lang-dropdown-anchor--open' : ''}`}
            >
                <button
                    type="button"
                    id={id}
                    name={inputName}
                    autoComplete={autoComplete}
                    className="cu-lang-dropdown-trigger"
                    tabIndex={0}
                    disabled={triggerDisabled}
                    aria-invalid={error || undefined}
                    aria-labelledby={labelId}
                    aria-describedby={describedBy || undefined}
                    aria-haspopup="listbox"
                    aria-expanded={open}
                    aria-controls={open ? listId : undefined}
                    aria-activedescendant={open ? activeId : undefined}
                    onClick={() => {
                        if (!triggerDisabled) setOpen((v) => !v);
                    }}
                    onKeyDown={handleTriggerKeyDown}
                >
                    <span className="cu-lang-dropdown-trigger-main cu-seat-panel__section-lang-trigger-main">
                        <span className="cu-lang-dropdown-value-row">
                            <span
                                className={`cu-lang-dropdown-value${!value ? ' cu-seat-panel__section-lang-placeholder' : ''}`}
                            >
                                {triggerText}
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
                        aria-label={ariaLabel}
                    >
                        {options.map((opt, idx) => {
                            const isSelected = value === opt;
                            const isActive = activeIndex === idx;
                            return (
                                <button
                                    key={opt}
                                    ref={(el) => { optionRefs.current[idx] = el; }}
                                    id={`${id}-opt-${idx}`}
                                    type="button"
                                    role="option"
                                    tabIndex={0}
                                    aria-selected={isSelected}
                                    className={`cu-lang-dropdown-option${isSelected ? ' cu-lang-dropdown-option--selected' : ''}${isActive && !isSelected ? ' cu-lang-dropdown-option--active' : ''}`}
                                    onFocus={() => setActiveIndex(idx)}
                                    onMouseEnter={() => setActiveIndex(idx)}
                                    onClick={() => {
                                        onChange(opt);
                                        setOpen(false);
                                    }}
                                    onKeyDown={(e) => {
                                        const last = options.length - 1;
                                        if (e.key === 'ArrowDown') {
                                            e.preventDefault();
                                            e.stopPropagation();
                                            focusOptionAt(idx + 1);
                                        } else if (e.key === 'ArrowUp') {
                                            e.preventDefault();
                                            e.stopPropagation();
                                            focusOptionAt(idx - 1);
                                        } else if (e.key === 'Home') {
                                            e.preventDefault();
                                            e.stopPropagation();
                                            focusOptionAt(0);
                                        } else if (e.key === 'End') {
                                            e.preventDefault();
                                            e.stopPropagation();
                                            focusOptionAt(last);
                                        } else if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            e.stopPropagation();
                                            onChange(opt);
                                            setOpen(false);
                                        } else if (e.key === 'Escape') {
                                            e.preventDefault();
                                            e.stopPropagation();
                                            setOpen(false);
                                            document.getElementById(id)?.focus();
                                        }
                                    }}
                                >
                                    <span className="cu-lang-dropdown-option-name">
                                        {formatOption ? formatOption(opt) : opt}
                                    </span>
                                </button>
                            );
                        })}
                    </div>
                ) : null}
            </div>
        </div>
    );
};

export default SeatChoiceDropdown;
