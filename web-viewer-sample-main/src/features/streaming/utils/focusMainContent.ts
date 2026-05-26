import { collectFocusableElements } from './focusableElements';
import { isSkipBypassChrome } from './overlayFocusRoots';

/**
 * WCAG 2.4.1 — move keyboard focus into the 3D viewer (not the top-right CU chrome).
 */
export function focusMainContent(): boolean {
    const main = document.getElementById('main-content');
    if (!main) return false;

    const candidates = collectFocusableElements(main).filter(
        (el) => !el.closest('.skip-to-content') && !isSkipBypassChrome(el),
    );

    const firstInView = candidates[0];
    if (firstInView) {
        firstInView.focus({ preventScroll: true });
        return true;
    }

    const sentinel = document.getElementById('main-viewer-focus-start');
    if (sentinel instanceof HTMLElement) {
        sentinel.focus({ preventScroll: true });
        return true;
    }

    if (!main.hasAttribute('tabindex')) {
        main.tabIndex = -1;
    }
    main.focus({ preventScroll: true });
    return true;
}

/** Run skip-link activation: focus main viewer, then drop the hash from the URL. */
export function activateSkipToMain(): void {
    focusMainContent();
    const { pathname, search } = window.location;
    window.history.replaceState(null, '', `${pathname}${search}`);
}
