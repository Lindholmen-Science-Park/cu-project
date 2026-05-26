import { useEffect } from 'react';

const STREAM_SURFACE_SELECTOR = '#remote-video, #main-div, .stream-main-div';

/** UI that should keep focus when clicked (not reset to “start tab order at skip”). */
const FOCUSABLE_CHROME_SELECTOR = [
    '.skip-to-content',
    '.cu-controls',
    '.cu-controls-menu-frost',
    '.cu-settings-frost',
    '.cu-people-frost',
    '.onboarding-overlay',
    'button',
    'a[href]',
    'input',
    'select',
    'textarea',
    '[role="dialog"]',
].join(',');

/**
 * Clicking the 3D stream should not leave focus on a menu button — otherwise the
 * next Tab continues from that button and never reaches the skip link (earlier in DOM).
 */
export function useReleaseFocusOnStreamSurface(streamReady: boolean): void {
    useEffect(() => {
        if (!streamReady) return;

        const onPointerDown = (e: PointerEvent) => {
            const target = e.target;
            if (!(target instanceof HTMLElement)) return;
            if (!target.closest(STREAM_SURFACE_SELECTOR)) return;
            if (target.closest(FOCUSABLE_CHROME_SELECTOR)) return;

            const active = document.activeElement;
            if (active instanceof HTMLElement && active !== document.body) {
                active.blur();
            }
        };

        document.addEventListener('pointerdown', onPointerDown, true);
        return () => document.removeEventListener('pointerdown', onPointerDown, true);
    }, [streamReady]);
}
