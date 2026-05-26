import { useEffect, useRef } from 'react';

const SKIP_LINK_ID = 'skip-to-content-link';

function isModalOpen(): boolean {
    return !!document.querySelector('[role="dialog"][aria-modal="true"]:not([inert])');
}

function isOnboardingVisible(): boolean {
    return !!document.querySelector('.onboarding-overlay');
}

/**
 * Until the user reaches the skip link (or activates it), the next forward Tab from
 * the stream / top chrome redirects to the skip link (WCAG 2.4.1).
 */
export function useSkipLinkTabOrder(enabled: boolean): void {
    const skipUsedRef = useRef(false);

    useEffect(() => {
        if (!enabled) return;

        const resetSkipCycle = () => {
            skipUsedRef.current = false;
        };

        const markSkipUsed = () => {
            skipUsedRef.current = true;
        };

        const skip = () => document.getElementById(SKIP_LINK_ID) as HTMLAnchorElement | null;

        const onPointerDown = (e: PointerEvent) => {
            const target = e.target;
            if (!(target instanceof HTMLElement)) return;
            if (!target.closest('#remote-video, #main-div, .stream-main-div')) return;
            if (target.closest('button, a[href], input, [role="dialog"]')) return;
            resetSkipCycle();
        };

        const onSkipFocus = () => markSkipUsed();

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key !== 'Tab' || e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
            if (skipUsedRef.current || isModalOpen() || isOnboardingVisible()) return;

            const link = skip();
            if (!link) return;

            const active = document.activeElement as HTMLElement | null;
            if (active === link) {
                markSkipUsed();
                return;
            }

            const fromPage =
                !active ||
                active === document.body ||
                active === document.documentElement ||
                !!active.closest(
                    '#root, .cu-controls, #main-div, #remote-video, .stream-only-window, .stream-only-window__main',
                );

            if (!fromPage) return;

            e.preventDefault();
            link.focus({ preventScroll: true });
        };

        const link = skip();
        link?.addEventListener('focus', onSkipFocus);

        document.addEventListener('pointerdown', onPointerDown, true);
        document.addEventListener('keydown', onKeyDown, true);

        return () => {
            link?.removeEventListener('focus', onSkipFocus);
            document.removeEventListener('pointerdown', onPointerDown, true);
            document.removeEventListener('keydown', onKeyDown, true);
        };
    }, [enabled]);
}
