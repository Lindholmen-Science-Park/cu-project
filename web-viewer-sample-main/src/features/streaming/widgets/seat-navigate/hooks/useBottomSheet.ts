import { useState, useRef, useCallback, useEffect } from 'react';
import React from 'react';

const HANDLE_TAP_MAX_PX = 10;
const HANDLE_PEEK_PULL_PX = 44;
const HANDLEBAR_PEEK_FALLBACK_PX = 52;
const HANDLE_PEEK_OVERSCROLL_PX = 40;
const HANDLE_EXPAND_PEEK_UP_PX = 48;

interface UseBottomSheetOptions {
    onClose: () => void;
    isCu: boolean;
    forceExpandSignal: number;
    /** Auto-collapse when route is confirmed */
    shouldAutoCollapse: boolean;
}

export function useBottomSheet({
    onClose,
    isCu,
    forceExpandSignal,
    shouldAutoCollapse,
}: UseBottomSheetOptions) {
    const [sheetExiting, setSheetExiting] = useState(false);
    const sheetExitDoneRef = useRef(false);
    const [sheetEnterDone, setSheetEnterDone] = useState(false);
    const [handlePullPx, setHandlePullPx] = useState(0);
    const handlePullPxRef = useRef(0);
    const handlePullDraggingRef = useRef(false);
    const handlePullStartYRef = useRef(0);
    const sheetShellRef = useRef<HTMLDivElement>(null);
    const handlebarHitRef = useRef<HTMLDivElement>(null);
    const [sheetCollapsed, setSheetCollapsed] = useState(false);
    const [collapsedOffsetPx, setCollapsedOffsetPx] = useState(0);
    const [peekPullPx, setPeekPullPx] = useState(0);
    const peekPullPxRef = useRef(0);
    const handleDragStartedCollapsedRef = useRef(false);
    const pointerTravelMaxRef = useRef(0);
    const [shellPointerActive, setShellPointerActive] = useState(false);

    const getSheetShellHeight = () => sheetShellRef.current?.offsetHeight ?? 420;

    const getHandlebarPeekHeight = () => {
        const el = handlebarHitRef.current;
        const rectH = el?.getBoundingClientRect().height;
        const oh = el?.offsetHeight;
        const h = rectH && rectH > 0 ? rectH : oh && oh > 0 ? oh : 0;
        return h > 0 ? h : HANDLEBAR_PEEK_FALLBACK_PX;
    };

    const computePeekCollapseOffset = () => {
        const shellH = getSheetShellHeight();
        const handleH = getHandlebarPeekHeight();
        return Math.max(48, shellH - handleH);
    };

    const computeMaxExpandedDragPull = () => computePeekCollapseOffset() + HANDLE_PEEK_OVERSCROLL_PX;

    const expandFromPeek = useCallback(() => {
        setSheetCollapsed(false);
        setCollapsedOffsetPx(0);
        setPeekPullPx(0);
        peekPullPxRef.current = 0;
    }, []);

    const collapseToPeek = useCallback(() => {
        requestAnimationFrame(() => {
            const off = computePeekCollapseOffset();
            setCollapsedOffsetPx(off);
            setSheetCollapsed(true);
            setPeekPullPx(0);
            peekPullPxRef.current = 0;
        });
    }, []);

    const requestClose = useCallback(() => {
        if (sheetExiting) return;
        expandFromPeek();
        if (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            onClose();
            return;
        }
        sheetExitDoneRef.current = false;
        setSheetExiting(true);
    }, [sheetExiting, onClose, expandFromPeek]);

    // Exit animation timeout fallback
    useEffect(() => {
        if (!sheetExiting) return;
        const t = window.setTimeout(() => {
            if (!sheetExitDoneRef.current) {
                sheetExitDoneRef.current = true;
                onClose();
            }
        }, 520);
        return () => window.clearTimeout(t);
    }, [sheetExiting, onClose]);

    // Reduced motion: skip enter animation
    useEffect(() => {
        if (!isCu) return;
        if (typeof window === 'undefined') return;
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            setSheetEnterDone(true);
        }
    }, [isCu]);

    // Fallback if animationEnd doesn't fire
    useEffect(() => {
        if (!isCu) return;
        if (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            return;
        }
        const t = window.setTimeout(() => {
            setSheetEnterDone((prev) => prev || true);
        }, 520);
        return () => window.clearTimeout(t);
    }, [isCu]);

    // Force expand from parent signal
    useEffect(() => {
        if (!isCu || forceExpandSignal <= 0 || sheetExiting) return;
        expandFromPeek();
    }, [isCu, forceExpandSignal, sheetExiting, expandFromPeek]);

    // Auto-collapse when route is confirmed
    useEffect(() => {
        if (!isCu || !shouldAutoCollapse) return;
        collapseToPeek();
    }, [isCu, shouldAutoCollapse, collapseToPeek]);

    const onSheetShellAnimationEnd = useCallback(
        (e: React.AnimationEvent<HTMLDivElement>) => {
            if (e.target !== e.currentTarget) return;
            const name = e.animationName || '';
            if (name.includes('cu-seat-sheet-in')) {
                setSheetEnterDone(true);
                return;
            }
            if (sheetExiting && name.includes('cu-seat-sheet-out') && !sheetExitDoneRef.current) {
                sheetExitDoneRef.current = true;
                onClose();
            }
        },
        [sheetExiting, onClose]
    );

    const onHandlePointerDown = useCallback(
        (e: React.PointerEvent<HTMLDivElement>) => {
            if (!sheetEnterDone || sheetExiting) return;
            e.preventDefault();
            handlePullDraggingRef.current = true;
            setShellPointerActive(true);
            handlePullStartYRef.current = e.clientY;
            handleDragStartedCollapsedRef.current = sheetCollapsed;
            pointerTravelMaxRef.current = 0;
            handlePullPxRef.current = 0;
            setHandlePullPx(0);
            peekPullPxRef.current = 0;
            setPeekPullPx(0);
            e.currentTarget.setPointerCapture(e.pointerId);
        },
        [sheetEnterDone, sheetExiting, sheetCollapsed]
    );

    const onHandlePointerMove = useCallback(
        (e: React.PointerEvent<HTMLDivElement>) => {
            if (!handlePullDraggingRef.current || sheetExiting) return;
            const dy = e.clientY - handlePullStartYRef.current;
            pointerTravelMaxRef.current = Math.max(pointerTravelMaxRef.current, Math.abs(dy));
            if (handleDragStartedCollapsedRef.current) {
                const capUp = -collapsedOffsetPx;
                const next = Math.max(capUp, Math.min(0, dy));
                peekPullPxRef.current = next;
                setPeekPullPx(next);
            } else {
                const maxPull = computeMaxExpandedDragPull();
                const next = Math.max(0, Math.min(maxPull, dy));
                handlePullPxRef.current = next;
                setHandlePullPx(next);
            }
        },
        [sheetExiting, collapsedOffsetPx]
    );

    const finishHandlePull = useCallback(
        (e: React.PointerEvent<HTMLDivElement>) => {
            if (!handlePullDraggingRef.current) return;
            handlePullDraggingRef.current = false;
            setShellPointerActive(false);
            const travel = pointerTravelMaxRef.current;
            const pullExpanded = handlePullPxRef.current;
            const pullPeek = peekPullPxRef.current;
            handlePullPxRef.current = 0;
            setHandlePullPx(0);
            peekPullPxRef.current = 0;
            setPeekPullPx(0);
            try {
                e.currentTarget.releasePointerCapture(e.pointerId);
            } catch {
                /* ignore */
            }

            const isTap = travel < HANDLE_TAP_MAX_PX;
            if (isTap) {
                if (sheetCollapsed) {
                    expandFromPeek();
                } else {
                    collapseToPeek();
                }
                return;
            }

            if (handleDragStartedCollapsedRef.current) {
                if (pullPeek <= -HANDLE_EXPAND_PEEK_UP_PX) {
                    expandFromPeek();
                }
                return;
            }

            const maxDrag = computeMaxExpandedDragPull();
            const closeIfPullPast = maxDrag - Math.max(12, HANDLE_PEEK_OVERSCROLL_PX / 2);

            if (pullExpanded >= closeIfPullPast) {
                requestClose();
            } else if (pullExpanded >= HANDLE_PEEK_PULL_PX) {
                collapseToPeek();
            }
        },
        [sheetCollapsed, expandFromPeek, collapseToPeek, requestClose]
    );

    const onHandlePointerCancel = useCallback(
        (e: React.PointerEvent<HTMLDivElement>) => {
            handlePullDraggingRef.current = false;
            setShellPointerActive(false);
            handlePullPxRef.current = 0;
            setHandlePullPx(0);
            peekPullPxRef.current = 0;
            setPeekPullPx(0);
            try {
                e.currentTarget.releasePointerCapture(e.pointerId);
            } catch {
                /* ignore */
            }
        },
        []
    );

    const onHandleKeyDown = useCallback(
        (e: React.KeyboardEvent<HTMLDivElement>) => {
            if (!sheetEnterDone || sheetExiting) return;
            if (e.key !== 'Enter' && e.key !== ' ') return;
            e.preventDefault();
            if (sheetCollapsed) expandFromPeek();
            else collapseToPeek();
        },
        [sheetEnterDone, sheetExiting, sheetCollapsed, expandFromPeek, collapseToPeek]
    );

    // Compute the sheet transform style
    const reduceMotion =
        typeof window !== 'undefined' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const cuSheetShellTY = sheetCollapsed ? collapsedOffsetPx + peekPullPx : handlePullPx;
    const cuSheetShellStyle: React.CSSProperties | undefined =
        sheetExiting
            ? undefined
            : sheetEnterDone || reduceMotion
              ? {
                    transform: `translate3d(0, ${cuSheetShellTY}px, 0)`,
                    transition:
                        shellPointerActive || reduceMotion
                            ? 'none'
                            : 'transform 0.32s cubic-bezier(0.32, 0.72, 0, 1)',
                }
              : undefined;

    return {
        sheetShellRef,
        handlebarHitRef,
        sheetExiting,
        sheetEnterDone,
        sheetCollapsed,
        cuSheetShellStyle,
        requestClose,
        expandFromPeek,
        collapseToPeek,
        onSheetShellAnimationEnd,
        onHandlePointerDown,
        onHandlePointerMove,
        finishHandlePull,
        onHandlePointerCancel,
        onHandleKeyDown,
    };
}
