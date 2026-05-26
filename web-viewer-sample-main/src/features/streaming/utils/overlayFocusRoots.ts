/**
 * CU / streaming overlay roots where keyboard focus must not be stolen by
 * #remote-video WASD refocus (see StreamOnlyWindow).
 */
export const OVERLAY_FOCUS_ROOT_SELECTOR = [
    '.cu-controls',
    '.cu-seat-panel__dock',
    '.avatar-chat-overlay-root',
    '.icon-bubble-wrap',
    '.npc-bubble-wrap',
    '.stream-seat-nav-info',
    '.stream-seat-nav-overlay',
    '.v360-overlay',
    '.ssp-overlay',
    '.vbook-overlay',
    '.vbp-overlay',
    '.cu-settings-frost',
    '.cu-controls-menu-frost',
    '.cu-people-frost',
].join(',');

export function isWithinOverlayFocusRoot(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false;
    return !!target.closest(OVERLAY_FOCUS_ROOT_SELECTOR);
}

/** Persistent CU chrome skipped by “Skip to main content” (not route/POI overlays). */
export const SKIP_BYPASS_CHROME_SELECTOR = [
    '.cu-controls',
    '.cu-settings-frost',
    '.cu-controls-menu-frost',
    '.cu-people-frost',
].join(',');

export function isSkipBypassChrome(el: HTMLElement): boolean {
    return !!el.closest(SKIP_BYPASS_CHROME_SELECTOR);
}
