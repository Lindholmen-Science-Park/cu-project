import { useEffect, useRef } from 'react';

/**
 * WCAG 2.4.3 — restore focus to the element that opened a modal/overlay on unmount.
 * Capture runs once on mount; restore runs on cleanup.
 */
export function useFocusRestore(enabled = true): void {
    const openerRef = useRef<HTMLElement | null>(null);

    useEffect(() => {
        if (!enabled) return;
        openerRef.current = (document.activeElement as HTMLElement | null) ?? null;
        return () => {
            const opener = openerRef.current;
            if (opener && document.body.contains(opener)) {
                try {
                    opener.focus({ preventScroll: true });
                } catch {
                    opener.focus();
                }
            }
        };
    }, [enabled]);
}
