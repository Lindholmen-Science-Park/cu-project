import { useState, useCallback, useRef, useEffect } from 'react';
import { sendMessage } from '../messaging';
import StreamConfig from '../../../config/stream.config.json';

export interface LoadingPhase {
    phase: string;
    message: string;
}

export function useStreamConnection(userId: string | undefined, onStreamFailedProp?: () => void, isViewer = false) {
    const [streamReady, setStreamReady] = useState(false);
    const [loadingText, setLoadingText] = useState(
        StreamConfig.source === 'local' ? 'Connecting to local stream...' : `User ${userId} connecting to stream...`
    );
    const [appStreamKey, setAppStreamKey] = useState(Date.now());
    const [sceneLoading, setSceneLoading] = useState(false);
    const [loadingPhase, setLoadingPhase] = useState<LoadingPhase>({ phase: 'idle', message: '' });

    const timeoutRef = useRef<number | null>(null);
    const uiReadyRetryRef = useRef<number | null>(null);
    const sceneLoadedOnceRef = useRef(false);
    const sceneLoadingRef = useRef(false);
    sceneLoadingRef.current = sceneLoading;

    const handleStreamStarted = useCallback(() => {
        console.log('The streaming session has started!');

        if (timeoutRef.current) {
            clearTimeout(timeoutRef.current);
            timeoutRef.current = null;
        }

        setStreamReady(true);
        setLoadingText(`User ${userId} stream connected!`);

        if (isViewer) {
            sceneLoadedOnceRef.current = true;
            setSceneLoading(false);
            setLoadingPhase({ phase: 'ready', message: 'Ready' });
            return;
        }

        if (!sceneLoadedOnceRef.current) {
            setSceneLoading(true);
            setLoadingPhase({ phase: 'connecting', message: 'Stream connected, waiting for scene...' });
        }

        try { sendMessage('ui.ready', {}); } catch {}
    }, [userId, isViewer]);

    const handleStreamFailed = useCallback(() => {
        console.log('Stream connection failed');

        if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = null; }
        if (uiReadyRetryRef.current) { window.clearInterval(uiReadyRetryRef.current); uiReadyRetryRef.current = null; }

        setStreamReady(false);
        setSceneLoading(false);
        setLoadingPhase({ phase: 'idle', message: '' });
        sceneLoadedOnceRef.current = false;
        setLoadingText(`User ${userId} connection failed. Cleaning up...`);

        if (onStreamFailedProp) onStreamFailedProp();

        setTimeout(() => {
            setLoadingText(`User ${userId} connection failed. Click retry to try again.`);
        }, 1000);
    }, [userId, onStreamFailedProp]);

    const retryConnection = useCallback(() => {
        console.log('Manual retry connection');
        if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = null; }
        if (uiReadyRetryRef.current) { window.clearInterval(uiReadyRetryRef.current); uiReadyRetryRef.current = null; }

        setStreamReady(false);
        setLoadingText(StreamConfig.source === 'local' ? 'Retrying connection to local stream...' : `User ${userId} retrying connection to stream...`);
        setAppStreamKey((prev) => prev + 1);

        timeoutRef.current = window.setTimeout(() => {
            setLoadingText(`User ${userId} connection timeout. Please check if the stream server is running.`);
        }, 10000);
    }, [userId]);

    const handleRerequestSceneStatus = useCallback(() => {
        setLoadingPhase({ phase: 'waiting', message: 'Re-requesting scene status...' });
        try { sendMessage('ui.ready', {}); } catch {}
    }, []);

    const handleSceneSwitch = useCallback((sceneId: string) => {
        console.log(`Switching scene to: ${sceneId}`);
        setSceneLoading(true);
        setLoadingPhase({ phase: 'loading', message: 'Loading scene...' });
        sendMessage('switchScene', { scene: sceneId });
    }, []);

    /** Handles scene lifecycle events (scene.loading, scene.loaded, loading.phase). */
    const processSceneEvent = useCallback((event: any) => {
        try {
            if (event.event_type === 'scene.loading') {
                setSceneLoading(true);
                setLoadingPhase((p) => ({ phase: 'loading', message: p.message || 'Loading scene...' }));
                return true;
            }
            if (event.event_type === 'scene.loaded') {
                sceneLoadedOnceRef.current = true;
                setSceneLoading(false);
                setLoadingPhase({ phase: 'ready', message: 'Ready' });
                sendMessage('navigationStateSet', { movementMode: 'pointClick', navigationEnabled: true, drawPath: false, autoMove: true, routeId: 'player' });
                console.log('Default navigation state sent: point-and-click mode');
                try { sendMessage('seatLayoutChange', { variant: '' }); } catch {}
                try { sendMessage('seatedCrowdLayoutChange', { variant: '' }); } catch {}
                return true;
            }
            if (event.event_type === 'loading.phase') {
                const payload = event.payload || {};
                const phase = String(payload.phase || 'idle');
                const message = String(payload.message || phase);
                setLoadingPhase({ phase, message });
                if (phase === 'ready') {
                    sceneLoadedOnceRef.current = true;
                    setSceneLoading(false);
                }
                return true;
            }
        } catch {}
        return false;
    }, []);

    // Periodic ui.ready retry — handles late-connect scenarios where the
    // WebRTC data channel isn't ready for custom messages when the initial
    // ui.ready is sent (video stream starts before data channel is bidirectional).
    const UI_READY_RETRY_MS = 3000;
    const UI_READY_MAX_RETRIES = 20;
    const uiReadyRetryCountRef = useRef(0);

    useEffect(() => {
        if (!streamReady || !sceneLoading || isViewer) return;

        uiReadyRetryCountRef.current = 0;

        uiReadyRetryRef.current = window.setInterval(() => {
            uiReadyRetryCountRef.current += 1;
            if (uiReadyRetryCountRef.current > UI_READY_MAX_RETRIES) {
                if (uiReadyRetryRef.current) { window.clearInterval(uiReadyRetryRef.current); uiReadyRetryRef.current = null; }
                setLoadingPhase((p) => ({ ...p, message: 'Loading is taking longer than expected. Try "Re-request scene status" or refresh the page.' }));
                return;
            }
            console.log(`[useStreamConnection] ui.ready retry ${uiReadyRetryCountRef.current}/${UI_READY_MAX_RETRIES}`);
            try { sendMessage('ui.ready', {}); } catch {}
        }, UI_READY_RETRY_MS);

        return () => {
            if (uiReadyRetryRef.current) { window.clearInterval(uiReadyRetryRef.current); uiReadyRetryRef.current = null; }
        };
    }, [streamReady, sceneLoading, isViewer]);

    // Timeout on mount + cleanup
    useEffect(() => {
        timeoutRef.current = window.setTimeout(() => {
            if (!streamReady) {
                setLoadingText(`User ${userId} connection timeout. Please check if the stream server is running.`);
            }
        }, 10000);

        return () => {
            if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = null; }
            if (uiReadyRetryRef.current) { window.clearInterval(uiReadyRetryRef.current); uiReadyRetryRef.current = null; }
        };
    }, [streamReady, userId]);

    return {
        streamReady,
        loadingText,
        setLoadingText,
        appStreamKey,
        sceneLoading,
        sceneLoadingRef,
        loadingPhase,
        setSceneLoading,
        handleStreamStarted,
        handleStreamFailed,
        retryConnection,
        handleRerequestSceneStatus,
        handleSceneSwitch,
        processSceneEvent,
    };
}
