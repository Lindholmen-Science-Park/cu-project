import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { sendMessage } from '../messaging';
import {
    subscribeXformViewCameraReady,
    type XformViewCameraReady,
} from '../overlays/xformViewCameraChannel';

/**
 * Spatial-sound iconGroup payload. Synthesised Kit-side by
 * `_expand_icon_group_entry`. See `topics/spatial-audio.mdc`.
 */
export interface SpatialSoundEntry {
    id: string;
    iconId: string;
    title: string;
    soundUrl: string;
    soundTitle: string;
    captionsUrl?: string;
    primPath?: string;
}

/**
 * Spatial-sound overlay state. `hasOnboarded` gates context-level teleport
 * before mount (mirrors `Video360Context`). The overlay always runs a 4 s
 * cinematic intro; this flag does not skip that intro.
 */
export interface SpatialSoundContextType {
    entry: SpatialSoundEntry | null;
    isOpen: boolean;
    hasOnboarded: boolean;
    open: (entry: SpatialSoundEntry) => void;
    close: () => void;
    markOnboarded: () => void;
}

const SpatialSoundContext = createContext<SpatialSoundContextType | null>(null);

/** Safety net for missed `xformViewCameraReady` acks — open anyway so the UI never wedges. */
const CAMERA_READY_TIMEOUT_MS = 1200;

export function SpatialSoundProvider({ children }: { children: React.ReactNode }) {
    const [entry, setEntry] = useState<SpatialSoundEntry | null>(null);
    // Default true so every `open()` takes the teleport-gated path (see Video360Context).
    const [hasOnboarded, setHasOnboarded] = useState(true);

    // In-flight prepare so a rapid second open() cancels the stale wait
    // instead of layering two opens on top of each other.
    const pendingPrimPathRef = useRef<string | null>(null);
    const cancelPendingRef = useRef<(() => void) | null>(null);

    const cancelPending = useCallback(() => {
        if (cancelPendingRef.current) {
            try { cancelPendingRef.current(); } catch { /* ignore */ }
            cancelPendingRef.current = null;
        }
        pendingPrimPathRef.current = null;
    }, []);

    const open = useCallback((next: SpatialSoundEntry) => {
        // No primPath: mount immediately. Otherwise teleport before mount so
        // the intro splash paints over the listen-spot view (overlay intro
        // phase handles orientation permission + playback).
        if (!hasOnboarded || !next.primPath) {
            cancelPending();
            setEntry(next);
            return;
        }

        // Skip-onboarding: teleport, then wait for ack before mounting
        // so the overlay never paints over the old view.
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
            // Match primPath so we ignore stale acks from a prior open.
            // ok=false still resolves — better to open at wrong pose
            // than wedge the UI.
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
        // Sole owner of the exit dispatch (callback path, so React 18
        // StrictMode never double-fires it). Kit's exit_xform_view is
        // idempotent — safe even if no enter was sent (onboarding-only
        // open).
        sendMessage('playerExitXformView', {});
        setEntry(null);
    }, [cancelPending]);

    const markOnboarded = useCallback(() => setHasOnboarded(true), []);

    useEffect(() => {
        return () => { cancelPending(); };
    }, [cancelPending]);

    const value = useMemo<SpatialSoundContextType>(() => ({
        entry,
        isOpen: entry !== null,
        hasOnboarded,
        open,
        close,
        markOnboarded,
    }), [entry, hasOnboarded, open, close, markOnboarded]);

    return <SpatialSoundContext.Provider value={value}>{children}</SpatialSoundContext.Provider>;
}

export function useSpatialSound(): SpatialSoundContextType {
    const ctx = useContext(SpatialSoundContext);
    if (!ctx) throw new Error('useSpatialSound must be used within SpatialSoundProvider');
    return ctx;
}

export { SpatialSoundContext };
