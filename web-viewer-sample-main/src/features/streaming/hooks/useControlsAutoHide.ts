import { useCallback, useEffect, useRef, useState, type FocusEvent, type RefObject } from 'react';

/**
 * Auto-hide media chrome (360° / spatial / videobook) after idle, but keep it visible
 * while any control inside `chromeRootRef` has keyboard focus (WCAG 2.4.7).
 */
export function useControlsAutoHide(hideAfterMs: number): {
    showControls: boolean;
    chromeVisible: boolean;
    chromeRootRef: RefObject<HTMLDivElement | null>;
    resetControlsTimer: () => void;
    onChromeFocusCapture: (e: FocusEvent) => void;
    onChromeBlurCapture: (e: FocusEvent) => void;
} {
    const [showControls, setShowControls] = useState(true);
    const [focusPinned, setFocusPinned] = useState(false);
    const controlsTimerRef = useRef<ReturnType<typeof setTimeout>>();
    const chromeRootRef = useRef<HTMLDivElement>(null);

    const resetControlsTimer = useCallback(() => {
        setShowControls(true);
        if (controlsTimerRef.current) window.clearTimeout(controlsTimerRef.current);
        controlsTimerRef.current = window.setTimeout(() => {
            const root = chromeRootRef.current;
            if (root?.contains(document.activeElement)) return;
            setShowControls(false);
        }, hideAfterMs);
    }, [hideAfterMs]);

    const onChromeFocusCapture = useCallback(
        (_e: FocusEvent) => {
            setFocusPinned(true);
            resetControlsTimer();
        },
        [resetControlsTimer],
    );

    const onChromeBlurCapture = useCallback((e: FocusEvent) => {
        const next = e.relatedTarget as Node | null;
        const root = chromeRootRef.current;
        if (!root?.contains(next)) {
            setFocusPinned(false);
        }
    }, []);

    useEffect(
        () => () => {
            if (controlsTimerRef.current) window.clearTimeout(controlsTimerRef.current);
        },
        [],
    );

    const chromeVisible = showControls || focusPinned;

    return {
        showControls,
        chromeVisible,
        chromeRootRef,
        resetControlsTimer,
        onChromeFocusCapture,
        onChromeBlurCapture,
    };
}
