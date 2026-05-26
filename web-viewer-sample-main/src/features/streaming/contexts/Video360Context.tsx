import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { sendMessage } from '../messaging';
import {
    subscribeXformViewCameraReady,
    type XformViewCameraReady,
} from '../overlays/xformViewCameraChannel';

/** 360° video iconGroup payload. Mirrors `SpatialSoundEntry`. */
export interface Video360Entry {
    id: string;
    iconId: string;
    title: string;
    videoUrl: string;
    videoTitle: string;
    captionsUrl?: string;
    primPath?: string;
}

/** Mirrors `SpatialSoundContextType`. Kept separate so onboarding is per-feature. */
export interface Video360ContextType {
    entry: Video360Entry | null;
    isOpen: boolean;
    hasOnboarded: boolean;
    open: (entry: Video360Entry) => void;
    close: () => void;
    markOnboarded: () => void;
}

const Video360Context = createContext<Video360ContextType | null>(null);

/** See `SpatialSoundContext.CAMERA_READY_TIMEOUT_MS` for rationale. */
const CAMERA_READY_TIMEOUT_MS = 1200;

export function Video360Provider({ children }: { children: React.ReactNode }) {
    const [entry, setEntry] = useState<Video360Entry | null>(null);
    // Onboarding card was removed in favour of the cinematic intro splash;
    // keep `hasOnboarded` so `open()` always takes the teleport-gated path
    // (used for synchronised mount with `playerEnterXformView`).
    const [hasOnboarded, setHasOnboarded] = useState(true);

    const pendingPrimPathRef = useRef<string | null>(null);
    const cancelPendingRef = useRef<(() => void) | null>(null);

    const cancelPending = useCallback(() => {
        const hadPending = pendingPrimPathRef.current !== null;
        if (cancelPendingRef.current) {
            try { cancelPendingRef.current(); } catch { /* ignore */ }
            cancelPendingRef.current = null;
        }
        pendingPrimPathRef.current = null;
        if (hadPending) {
            sendMessage('playerExitXformView', {});
        }
    }, []);

    // See `SpatialSoundContext.open()` for the gating rationale.
    const open = useCallback((next: Video360Entry) => {
        if (!hasOnboarded || !next.primPath) {
            cancelPending();
            setEntry(next);
            return;
        }

        cancelPending();
        pendingPrimPathRef.current = next.primPath;
        sendMessage('playerEnterXformView', { primPath: next.primPath });

        let settled = false;
        const finish = () => {
            if (settled) return;
            settled = true;
            unsubscribe();
            window.clearTimeout(timeoutId);
            cancelPendingRef.current = null;
            pendingPrimPathRef.current = null;
            setEntry(next);
        };

        const unsubscribe = subscribeXformViewCameraReady((payload: XformViewCameraReady) => {
            if (payload.primPath !== next.primPath) return;
            finish();
        });

        const timeoutId = window.setTimeout(finish, CAMERA_READY_TIMEOUT_MS);

        cancelPendingRef.current = () => {
            unsubscribe();
            window.clearTimeout(timeoutId);
        };
    }, [hasOnboarded, cancelPending]);

    const close = useCallback(() => {
        cancelPending();
        setEntry(null);
    }, [cancelPending]);

    const markOnboarded = useCallback(() => setHasOnboarded(true), []);

    useEffect(() => {
        return () => { cancelPending(); };
    }, [cancelPending]);

    const value = useMemo<Video360ContextType>(() => ({
        entry,
        isOpen: entry !== null,
        hasOnboarded,
        open,
        close,
        markOnboarded,
    }), [entry, hasOnboarded, open, close, markOnboarded]);

    return <Video360Context.Provider value={value}>{children}</Video360Context.Provider>;
}

export function useVideo360(): Video360ContextType {
    const ctx = useContext(Video360Context);
    if (!ctx) throw new Error('useVideo360 must be used within Video360Provider');
    return ctx;
}

export { Video360Context };
