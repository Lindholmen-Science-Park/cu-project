import { FOCUSABLE_SELECTOR } from '../hooks/useFocusTrap';

function isAriaHiddenTree(el: HTMLElement): boolean {
    for (let node: HTMLElement | null = el; node; node = node.parentElement) {
        if (node.getAttribute('aria-hidden') === 'true') return true;
    }
    return false;
}

function isVisibleFocusable(el: HTMLElement): boolean {
    if (el.hasAttribute('disabled')) return false;
    if (isAriaHiddenTree(el)) return false;
    if (el.closest('[inert]')) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rects = el.getClientRects();
    return rects.length > 0 && rects[0].width > 0 && rects[0].height > 0;
}

/** Focusable controls inside `root`, in tab order (positive tabindex first, then DOM order). */
export function collectFocusableElements(root: ParentNode): HTMLElement[] {
    const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        isVisibleFocusable,
    );
    return items.sort((a, b) => {
        const ta = a.tabIndex;
        const tb = b.tabIndex;
        if (ta > 0 && tb > 0) return ta - tb;
        if (ta > 0) return -1;
        if (tb > 0) return 1;
        if (a === b) return 0;
        const pos = a.compareDocumentPosition(b);
        if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
        if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
        return 0;
    });
}
