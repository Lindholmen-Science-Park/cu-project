import { useEffect } from 'react';

/** Tabbable page chrome behind open CU dialogs (not the dialogs themselves). */
const BACKGROUND_INERT_SELECTOR = [
    '#skip-to-main',
    '#main-div',
    '.ibox-overlay-root',
    '.icon-bubble-wrap',
    '.npc-bubble-wrap',
    '.stream-seat-nav-info',
    '.stream-seat-nav-overlay',
    '.cu-controls > .cu-hamburger',
    '.cu-controls > .cu-icon-btn',
    '.cu-controls > .cu-view-toggle-btn',
].join(',');

/**
 * While Quick settings / controls menu / settings panel is open, keep Tab inside the
 * dialog — skip link and the 3D stream must not appear in the tab order behind it.
 */
export function useCuModalBackgroundInert(modalOpen: boolean): void {
    useEffect(() => {
        const roots = Array.from(document.querySelectorAll<HTMLElement>(BACKGROUND_INERT_SELECTOR));
        roots.forEach((el) => {
            if (modalOpen) el.setAttribute('inert', '');
            else el.removeAttribute('inert');
        });
        return () => {
            roots.forEach((el) => el.removeAttribute('inert'));
        };
    }, [modalOpen]);
}
