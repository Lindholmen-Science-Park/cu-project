import type { RefObject } from 'react';
import { useFocusRestore } from './useFocusRestore';
import { useFocusTrap, type UseFocusTrapOptions } from './useFocusTrap';

/**
 * WCAG modal pattern: restore opener focus on close + trap Tab inside the dialog.
 * Pass `initialFocusRef` when the dialog should receive focus on open (Settings, etc.).
 */
export function useModalAccessibility<T extends HTMLElement>(
    containerRef: RefObject<T | null>,
    options?: UseFocusTrapOptions,
): void {
    const enabled = options?.enabled ?? true;
    useFocusRestore(enabled);
    useFocusTrap(containerRef, { ...options, enabled });
}
