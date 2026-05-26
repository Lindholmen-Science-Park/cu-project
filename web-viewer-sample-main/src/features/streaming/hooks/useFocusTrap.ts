import { useEffect, type RefObject } from 'react';
import { collectFocusableElements } from '../utils/focusableElements';

export const FOCUSABLE_SELECTOR = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
].join(', ');

export interface UseFocusTrapOptions {
    enabled?: boolean;
    /** Prefer this element for initial focus when inside the container. */
    initialFocusRef?: RefObject<HTMLElement | null>;
}

/**
 * WCAG 2.1.2 — keep keyboard focus inside an open modal while Tab/Shift+Tab cycle.
 */
export function useFocusTrap<T extends HTMLElement>(
    containerRef: RefObject<T | null>,
    options: UseFocusTrapOptions = {},
): void {
    const { enabled = true, initialFocusRef } = options;

    useEffect(() => {
        if (!enabled) return;
        const container = containerRef.current;
        if (!container) return;

        const getFocusable = (): HTMLElement[] => collectFocusableElements(container);

        const focusInitial = () => {
            const preferred = initialFocusRef?.current;
            if (preferred && container.contains(preferred)) {
                preferred.focus({ preventScroll: true });
                return;
            }
            const items = getFocusable();
            if (items.length > 0) items[0].focus({ preventScroll: true });
        };

        const raf = requestAnimationFrame(focusInitial);

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key !== 'Tab') return;
            const active = document.activeElement as HTMLElement | null;
            // Only wrap Tab while focus is already inside this dialog — never pull focus in from the page behind.
            if (!active || !container.contains(active)) return;

            const items = getFocusable();
            if (items.length === 0) return;

            const first = items[0];
            const last = items[items.length - 1];

            if (e.shiftKey) {
                if (active === first) {
                    e.preventDefault();
                    last.focus({ preventScroll: true });
                }
            } else if (active === last) {
                e.preventDefault();
                first.focus({ preventScroll: true });
            }
        };

        container.addEventListener('keydown', onKeyDown);
        return () => {
            if (raf !== undefined) cancelAnimationFrame(raf);
            container.removeEventListener('keydown', onKeyDown);
        };
    }, [containerRef, enabled, initialFocusRef]);
}
