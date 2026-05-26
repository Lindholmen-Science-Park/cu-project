import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import type { CSSProperties } from 'react';

/** Match typical phone / narrow streaming chrome */
const MOBILE_MQ = '(max-width: 639px)';
const DISMISS_PULL_PX = 88;

export function useIotPanelDrag(open: boolean, onDismiss: () => void) {
    const [isMobile, setIsMobile] = useState(() =>
        typeof window !== 'undefined' ? window.matchMedia(MOBILE_MQ).matches : false,
    );
    const [offsetY, setOffsetY] = useState(0);
    const [isDragging, setIsDragging] = useState(false);
    const draggingRef = useRef(false);
    const startYRef = useRef(0);
    const startOffsetRef = useRef(0);
    const offsetYRef = useRef(0);

    useEffect(() => {
        offsetYRef.current = offsetY;
    }, [offsetY]);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        const mq = window.matchMedia(MOBILE_MQ);
        const onChange = () => setIsMobile(mq.matches);
        onChange();
        mq.addEventListener('change', onChange);
        return () => mq.removeEventListener('change', onChange);
    }, []);

    useEffect(() => {
        if (open) {
            setOffsetY(0);
            setIsDragging(false);
            draggingRef.current = false;
        }
    }, [open]);

    const onHandlePointerDown = useCallback(
        (e: React.PointerEvent<HTMLButtonElement>) => {
            if (!isMobile) return;
            draggingRef.current = true;
            setIsDragging(true);
            startYRef.current = e.clientY;
            startOffsetRef.current = offsetYRef.current;
            e.currentTarget.setPointerCapture(e.pointerId);
        },
        [isMobile],
    );

    const onHandlePointerMove = useCallback(
        (e: React.PointerEvent<HTMLButtonElement>) => {
            if (!isMobile || !draggingRef.current) return;
            const dy = e.clientY - startYRef.current;
            setOffsetY(Math.max(0, startOffsetRef.current + dy));
        },
        [isMobile],
    );

    const finishDrag = useCallback(
        (e: React.PointerEvent<HTMLButtonElement>) => {
            if (!isMobile) return;
            if (!draggingRef.current) return;
            draggingRef.current = false;
            setIsDragging(false);
            try {
                e.currentTarget.releasePointerCapture(e.pointerId);
            } catch {
                /* already released */
            }
            const dy = e.clientY - startYRef.current;
            const final = Math.max(0, startOffsetRef.current + dy);
            if (final > DISMISS_PULL_PX) {
                onDismiss();
            }
            setOffsetY(0);
        },
        [isMobile, onDismiss],
    );

    const sheetOuterStyle = useMemo((): CSSProperties | undefined => {
        if (!isMobile) return undefined;
        return {
            transform: `translateY(${offsetY}px)`,
            transition: isDragging ? 'none' : 'transform 0.22s cubic-bezier(0.32, 0.72, 0, 1)',
        };
    }, [isMobile, offsetY, isDragging]);

    return {
        isMobile,
        sheetOuterStyle,
        onHandlePointerDown,
        onHandlePointerMove,
        onHandlePointerUp: finishDrag,
        onHandlePointerCancel: finishDrag,
    };
}
