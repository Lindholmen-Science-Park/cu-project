import { useState, useRef, useEffect, useCallback } from 'react';

const CU_SEAT_ACTION_COOLDOWN_MS = 700;

interface UseCuModeSwitchingOptions {
    isCu: boolean;
    accessibilityMode: 'wheelchair' | 'walking';
    navmeshBaking: boolean;
    onNavmeshModeChange?: (mode: 'walking' | 'wheelchair') => void;
    onDraftChange?: (draft: { section: string; row: string; seat: string }) => void;
    onSeatRouteDismiss?: () => void;
    /** Called to clear form fields when switching modes */
    clearFormFields: () => void;
}

export function useCuModeSwitching({
    isCu,
    accessibilityMode,
    navmeshBaking,
    onNavmeshModeChange,
    onDraftChange,
    onSeatRouteDismiss,
    clearFormFields,
}: UseCuModeSwitchingOptions) {
    const [cuTabMode, setCuTabMode] = useState<'walking' | 'wheelchair'>(accessibilityMode);
    const [cuModeSwitchBusy, setCuModeSwitchBusy] = useState(false);
    const cuModeSwitchSawBakingRef = useRef(false);

    useEffect(() => {
        setCuTabMode(accessibilityMode);
    }, [accessibilityMode]);

    // Clear busy as soon as Kit acks the requested mode. Historically we waited
    // for a `navmeshBaking` true→false pulse (mode switch implied a rebake);
    // with the dual-mode NavMesh cache the swap is instant and no baking pulse
    // fires, so `accessibilityMode === cuTabMode` is the ack signal. The
    // baking-pulse path is still handled in case a future change reintroduces it.
    useEffect(() => {
        if (!isCu) return;
        if (!cuModeSwitchBusy) return;
        if (navmeshBaking) cuModeSwitchSawBakingRef.current = true;
        if (cuModeSwitchSawBakingRef.current && !navmeshBaking) {
            setCuModeSwitchBusy(false);
            cuModeSwitchSawBakingRef.current = false;
            return;
        }
        if (!navmeshBaking && accessibilityMode === cuTabMode) {
            setCuModeSwitchBusy(false);
            cuModeSwitchSawBakingRef.current = false;
        }
    }, [isCu, navmeshBaking, cuModeSwitchBusy, accessibilityMode, cuTabMode]);

    // Timeout fallback for mode switch busy state
    useEffect(() => {
        if (!cuModeSwitchBusy) return;
        const id = window.setTimeout(() => {
            setCuModeSwitchBusy(false);
            cuModeSwitchSawBakingRef.current = false;
        }, 12000);
        return () => window.clearTimeout(id);
    }, [cuModeSwitchBusy]);

    // Button cooldown to prevent double-clicks
    const [cuSeatBtnCooldown, setCuSeatBtnCooldown] = useState(false);
    const cuSeatBtnCooldownTimerRef = useRef<number | null>(null);

    useEffect(() => () => {
        if (cuSeatBtnCooldownTimerRef.current != null) {
            window.clearTimeout(cuSeatBtnCooldownTimerRef.current);
        }
    }, []);

    const armCooldown = useCallback(() => {
        if (!isCu) return;
        if (cuSeatBtnCooldownTimerRef.current != null) {
            window.clearTimeout(cuSeatBtnCooldownTimerRef.current);
        }
        setCuSeatBtnCooldown(true);
        cuSeatBtnCooldownTimerRef.current = window.setTimeout(() => {
            setCuSeatBtnCooldown(false);
            cuSeatBtnCooldownTimerRef.current = null;
        }, CU_SEAT_ACTION_COOLDOWN_MS);
    }, [isCu]);

    const selectNavmeshTab = useCallback(
        (mode: 'walking' | 'wheelchair') => {
            if (!onNavmeshModeChange || navmeshBaking || cuModeSwitchBusy) return;
            if (cuTabMode === mode) return;
            setCuTabMode(mode);
            clearFormFields();
            onDraftChange?.({ section: '', row: '', seat: '' });
            onSeatRouteDismiss?.();
            cuModeSwitchSawBakingRef.current = false;
            setCuModeSwitchBusy(true);
            onNavmeshModeChange(mode);
        },
        [onNavmeshModeChange, navmeshBaking, cuModeSwitchBusy, cuTabMode, clearFormFields, onDraftChange, onSeatRouteDismiss]
    );

    const cuInteractLocked = isCu && !!onNavmeshModeChange && (navmeshBaking || cuModeSwitchBusy);
    const cuSeatActionsBusy = isCu && cuSeatBtnCooldown;

    return {
        cuTabMode,
        cuModeSwitchBusy,
        cuInteractLocked,
        cuSeatActionsBusy,
        armCooldown,
        selectNavmeshTab,
    };
}
