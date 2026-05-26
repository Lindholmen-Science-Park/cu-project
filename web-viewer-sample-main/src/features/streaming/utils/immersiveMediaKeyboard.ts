/**
 * Returns true when a window-level media shortcut (arrows, space, etc.) should not run
 * because the user is interacting with a dialog or form control.
 */
export function shouldDeferImmersiveMediaShortcut(e: KeyboardEvent): boolean {
    const target = e.target as HTMLElement | null;
    if (!target) return false;
    if (target.closest('[role="dialog"]')) return true;
    const tag = target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
    return target.isContentEditable;
}

/** Keep range slider arrow/home/end keys on the input (don't bubble to overlay shortcuts). */
export function stopRangeSliderKeyPropagation(e: React.KeyboardEvent<HTMLInputElement>): void {
    switch (e.key) {
        case 'ArrowLeft':
        case 'ArrowRight':
        case 'ArrowUp':
        case 'ArrowDown':
        case 'Home':
        case 'End':
        case 'PageUp':
        case 'PageDown':
            e.stopPropagation();
            break;
        default:
            break;
    }
}
