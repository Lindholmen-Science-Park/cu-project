/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { AppStreamer, StreamEvent, StreamProps, DirectConfig, GFNConfig, StreamType } from '@nvidia/omniverse-webrtc-streaming-library';
import StreamConfig from '../../config/stream.config.json';
import { safeTerminateStream } from './streamUtils';
import { setMessageSender } from './messaging';
import './AppStream.css';
import BirdEyeRouteOverlay from './overlays/birdEyeRoute/BirdEyeRouteOverlay';
import { LoadingScreen } from './components/loading';
import AppStreamSeatOverlays from './AppStreamSeatOverlays';
import type { AppStreamCoreProps } from './appStreamTypes';
import {
    CONNECT_TIMEOUT_MS,
    MAX_CONNECT_RETRIES,
    ORIENTATION_DEBOUNCE_MS,
    RESIZE_RECONNECT_COOLDOWN_MS,
    getEffectiveServer,
    getAlignedResolution,
} from './appStreamResolution';
import { useRemoteVideoPointerGestures } from './useRemoteVideoPointerGestures';


const AppStreamCore: React.FC<AppStreamCoreProps> = ({
    sessionId,
    backendUrl,
    signalingserver,
    signalingport,
    mediaserver,
    mediaport,
    accessToken,
    style = {},
    onStarted,
    onStreamFailed,
    onLoggedIn,
    handleCustomEvent,
    nextClickPlacesMarker = false,
    nextClickPlacesIncident = false,
    nextClickPlacesCamera = false,
    incidentSizePreset = '1x1',
    incidentShape = 'cube',
    onMarkerClickConsumed,
    onIncidentClickConsumed,
    onCameraClickConsumed,
    pointClickEnabled = false,
    osmRouteOverlayActive = false,
    osmNavigateActive = false,
    isBirdEye = false,
    birdEyeRouteActive = false,
    isViewer = false,
    onLoadingStatus,
    activeFixedCamera = null,
    seatNavigationOverlay = null,
    seatArrivalCelebrationVisible = false,
    seatArrivalLabel = null,
    onArrivalDismiss,
    poiArrivalVisible = false,
    poiArrivalLabel = null,
    onPoiArrivalDismiss,
    invertTouchLook = false,
    usdEditIntent = null,
    vertexDragActive = false,
}) => {
    const { t } = useTranslation();
    const [streamReady, setStreamReady] = useState(false);
    const [resolutionSynced, setResolutionSynced] = useState(false);
    const [desiredResolution, setDesiredResolution] = useState(() =>
        getAlignedResolution(
            typeof window !== 'undefined' ? window.innerWidth : 1280,
            typeof window !== 'undefined' ? window.innerHeight : 720,
        ),
    );
    const [reconnectNonce, setReconnectNonce] = useState(0);
    /** Stream #remote-audio — UI state for seat-route speaker toggle */
    const [seatRouteStreamAudioMuted, setSeatRouteStreamAudioMuted] = useState(true);
    const connectionIdRef = useRef<string>(`conn_${Date.now()}_${Math.random()}`);
    const connectTimeoutRef = useRef<number | null>(null);
    const connectRetryRef = useRef<number>(0);
    const startedRef = useRef(false);
    const lastResizeReconnectRef = useRef(0);
    const deferredResizeRef = useRef<number | null>(null);
    const desiredResolutionRef = useRef(desiredResolution);
    desiredResolutionRef.current = desiredResolution;
    const resizeReconnectingRef = useRef(false);
    /** Avoid re-syncing mute glyph from `#remote-audio` on every seat overlay object churn (route metrics). */
    const seatNavOverlaySeenRef = useRef(false);

    useEffect(() => {
        const active = seatNavigationOverlay != null;
        if (!active) {
            seatNavOverlaySeenRef.current = false;
            return;
        }
        if (seatNavOverlaySeenRef.current) return;
        seatNavOverlaySeenRef.current = true;
        const a = document.getElementById('remote-audio') as HTMLAudioElement | null;
        if (a) setSeatRouteStreamAudioMuted(a.muted);
    }, [seatNavigationOverlay]);

    useEffect(() => {
        const currentConnectionId = `conn_${Date.now()}_${Math.random()}`;
        connectionIdRef.current = currentConnectionId;
        connectRetryRef.current = 0;

        setStreamReady(false);
        setResolutionSynced(false);
        startedRef.current = false;

        safeTerminateStream();

        // When the Kit-side streaming layer restarts (e.g. watchdog recovery
        // after an incompatible browser poisoned the NVST session), the WebRTC
        // connection drops.  Reconnect automatically so the user doesn't have
        // to refresh.
        const handleUnexpectedStop = () => {
            if (connectionIdRef.current !== currentConnectionId) return;
            if (!startedRef.current) return;
            console.warn('[stream] Unexpected stream stop — scheduling reconnect');
            startedRef.current = false;
            setStreamReady(false);
            connectRetryRef.current = 0;
            safeTerminateStream();
            setReconnectNonce((n) => n + 1);
        };

        const connectWithDelay = async (retryCount = 0) => {
            const delay = Math.min(1000 * Math.pow(2, retryCount), 5000);
            await new Promise(resolve => setTimeout(resolve, delay));

            if (connectionIdRef.current !== currentConnectionId) return;

            let streamProps: StreamProps;
            let streamConfig: DirectConfig | GFNConfig;
            let streamSource: StreamType.DIRECT | StreamType.GFN;

            if (StreamConfig.source === 'gfn') {
                    streamSource = StreamType.GFN;
                    streamConfig = {
                        //@ts-ignore
                        GFN             : GFN,
                        catalogClientId : StreamConfig.gfn.catalogClientId,
                        clientId        : StreamConfig.gfn.clientId,
                        cmsId           : StreamConfig.gfn.cmsId,
                        onUpdate        : (message: StreamEvent) => onUpdate(message),
                        onStart         : (message: StreamEvent) => onStart(message),
                        onCustomEvent   : (message: any) => onCustomEvent(message)
                    }
            }

            else if (StreamConfig.source === 'local') {
                const server = getEffectiveServer(StreamConfig.local.server);
                const sigPort = isViewer
                    ? (StreamConfig.local as any).spectatorSignalingPort ?? 49200
                    : StreamConfig.local.signalingPort;
                const medPort = isViewer
                    ? (StreamConfig.local as any).spectatorMediaPort ?? 48000
                    : StreamConfig.local.mediaPort;
                streamSource = StreamType.DIRECT;
                streamConfig = {
                    videoElementId: 'remote-video',
                    audioElementId: 'remote-audio',
                    authenticate: false,
                    maxReconnects: 0,
                    signalingServer: server,
                    signalingPort: sigPort,
                    mediaServer: server,
                    ...(medPort != null && { mediaPort: medPort }),
                    nativeTouchEvents: !isViewer,
                    width: desiredResolution.width,
                    height: desiredResolution.height,
                    fps: 60,
                    onUpdate: (message: StreamEvent) => onUpdate(message),
                    onStart: (message: StreamEvent) => onStart(message),
                    onCustomEvent: (message: any) => onCustomEvent(message),
                    onStop: (message: StreamEvent) => { 
                        console.log('[stream] onStop:', message);
                        handleUnexpectedStop();
                    },
                    onTerminate: (message: StreamEvent) => { 
                        console.log('[stream] onTerminate:', message);
                        handleUnexpectedStop();
                    }
                };
            }
                
            else if (StreamConfig.source === 'stream') {
                streamSource =  StreamType.DIRECT;
                streamConfig = {
                    signalingServer: signalingserver,
                    signalingPort: signalingport,
                    mediaServer: mediaserver,
                    mediaPort: mediaport,
                    backendUrl: backendUrl,
                    sessionId: sessionId,
                    autoLaunch: true,
                    cursor: 'free',
                    mic: false,
                    videoElementId: 'remote-video',
                    audioElementId: 'remote-audio',
                    authenticate: false,
                    maxReconnects: 0,
                    nativeTouchEvents: true,
                    width: desiredResolution.width,
                    height: desiredResolution.height,
                    fps: 60,
                    onUpdate: (message: StreamEvent) => onUpdate(message),
                    onStart: (message: StreamEvent) => onStart(message),
                    onCustomEvent: (message: any) => onCustomEvent(message),
                    onStop: (message: StreamEvent) => { 
                        console.log('[stream] onStop:', message);
                        handleUnexpectedStop();
                    },
                    onTerminate: (message: StreamEvent) => { 
                        console.log('[stream] onTerminate:', message);
                        handleUnexpectedStop();
                    },
                };
            }
                
            else {
                console.error(`Unknown stream source: ${StreamConfig.source}`);
                return;
            }

            try {
                streamProps = {streamConfig, streamSource}
                AppStreamer.connect(streamProps)
                .then((result: StreamEvent) => {
                    if (connectionIdRef.current === currentConnectionId) {
                        console.info('Connection successful:', result);
                    }
                })
                .catch((error: StreamEvent) => {
                    if (connectionIdRef.current === currentConnectionId) {
                        console.error('Connection failed:', error);
                    }
                });
            }
            catch (error) {
                console.error('Connection setup error:', error);
            }
        };
        
        const startConnectTimeout = () => {
            if (connectTimeoutRef.current) {
                window.clearTimeout(connectTimeoutRef.current);
            }
            connectTimeoutRef.current = window.setTimeout(() => {
                if (connectionIdRef.current !== currentConnectionId) return;
                if (streamReady) return;
                if (connectRetryRef.current >= MAX_CONNECT_RETRIES) return;
                connectRetryRef.current += 1;
                safeTerminateStream();
                setReconnectNonce((value) => value + 1);
            }, CONNECT_TIMEOUT_MS);
        };

        connectWithDelay();
        startConnectTimeout();

        return () => {
            if (connectionIdRef.current === currentConnectionId) {
                connectionIdRef.current = `cancelled_${currentConnectionId}`;
            }
            if (connectTimeoutRef.current) {
                window.clearTimeout(connectTimeoutRef.current);
                connectTimeoutRef.current = null;
            }
            safeTerminateStream();
        };
    }, [sessionId, backendUrl, signalingserver, signalingport, mediaserver, mediaport, accessToken, desiredResolution, reconnectNonce]);

    useEffect(() => {
        if (!streamReady) return;
        if (connectTimeoutRef.current) {
            window.clearTimeout(connectTimeoutRef.current);
            connectTimeoutRef.current = null;
        }
        // GFN player extras
        const gfnPlayer = document.getElementById("gfn-stream-player-video") as HTMLVideoElement | null;
        if (gfnPlayer) {
            gfnPlayer.tabIndex = -1;
            gfnPlayer.playsInline = true;
            gfnPlayer.muted = true;
            gfnPlayer.play().catch(() => {});
        }
        // Keep #remote-video out of the tab order (CU production). Dev-only WASD may focus it in StreamOnlyWindow.
        const video = document.getElementById('remote-video') as HTMLVideoElement | null;
        if (video) {
            try {
                video.tabIndex = -1;
            } catch {
                /* ignore */
            }
            try {
                video.play().catch((e) => console.warn('[stream] video.play() after start:', e));
            } catch {
                /* ignore */
            }
        }

        // Log remote video stream dimensions (videoWidth / videoHeight = actual decoded stream size)
        const logRemoteVideoDimensions = () => {
            const el = document.getElementById('remote-video') as HTMLVideoElement | null;
            const w = el?.videoWidth;
            const h = el?.videoHeight;
            console.log('[stream] remote-video dimensions:', { videoWidth: w, videoHeight: h });
        };
        logRemoteVideoDimensions();
        const t1 = window.setTimeout(logRemoteVideoDimensions, 500);
        const t2 = window.setTimeout(logRemoteVideoDimensions, 2000);
        return () => {
            window.clearTimeout(t1);
            window.clearTimeout(t2);
        };
    }, [streamReady]);

    // After resolution sync the <video> becomes visible; some browsers need an explicit play()
    // when tracks attach or when the element was hidden (avoids a stuck black frame).
    useEffect(() => {
        if (StreamConfig.source === 'gfn') return;
        if (!streamReady || !resolutionSynced) return;
        const video = document.getElementById('remote-video') as HTMLVideoElement | null;
        if (!video) return;
        const tryPlay = () => {
            void video.play().catch((e) => console.warn('[stream] video.play() after sync:', e));
        };
        tryPlay();
        video.addEventListener('loadeddata', tryPlay);
        video.addEventListener('canplay', tryPlay);
        return () => {
            video.removeEventListener('loadeddata', tryPlay);
            video.removeEventListener('canplay', tryPlay);
        };
    }, [streamReady, resolutionSynced]);

    // No pointer/keyboard lock; inputs remain free for desktop/mobile

    const onStart = (message: any) => {
        if (message.action === 'start' && message.status === 'success') {
            console.info('streamReady');
            setStreamReady(true);
        }

        if (message.status === "error" && StreamConfig.source === "stream")
        {
            console.log(message.info);
            alert(message.info);
            onStreamFailed();
            return;
        }
    }

    const onUpdate = (message: any) => {
        try {
            if (message.action === 'authUser' && message.status === 'success') {
                onLoggedIn(message.info);
            }
        } catch (error) {
            console.error(message);
        }
    }

    const onCustomEvent = (message: any) => {
        try {
            if (message?.event_type !== 'uiInteractionBoxesUpdate' && message?.event_type !== 'birdEyeRouteOverlay') {
                console.log('onCustomEvent received:', message);
            }
        } catch {}
        // Handle only non-input events (weather, interactions, etc.)
        // Movement is handled automatically by AppStreamer → WebRTC → carb.input
        try {
            handleCustomEvent(message);
        } catch {}
        // Events 2.0 messages from Kit are automatically forwarded via omni.kit.livestream.messaging
    }

    // Send custom messages via AppStreamer (Events 2.0 in Omniverse 109.0.2)
    const sendCustomMessage = useCallback((eventType: string, payload: any) => {
        if (isViewer) return;
        try {
            const message = {
                event_type: eventType,
                payload: payload || {}
            };
            AppStreamer.sendMessage(message);
        } catch (error) {
            console.warn('Failed to send custom message:', error);
        }
    }, [isViewer]);

    useEffect(() => {
        setMessageSender(sendCustomMessage);
        return () => setMessageSender(null);
    }, [streamReady, sendCustomMessage]);

    useRemoteVideoPointerGestures({
        streamReady,
        isViewer,
        sendCustomMessage,
        nextClickPlacesMarker,
        nextClickPlacesIncident,
        nextClickPlacesCamera,
        incidentSizePreset,
        incidentShape,
        onMarkerClickConsumed,
        onIncidentClickConsumed,
        onCameraClickConsumed,
        pointClickEnabled,
        osmNavigateActive,
        osmRouteOverlayActive,
        isBirdEye,
        birdEyeRouteActive,
        activeFixedCamera,
        invertTouchLook,
        usdEditIntent,
        vertexDragActive,
    });

    // ui.ready is sent by handleStreamStarted (useStreamConnection) when onStarted()
    // fires below. Do NOT send a second ui.ready here — each reconnection (e.g. resize)
    // would double-count toward the Kit-side streaming watchdog threshold (5 in 30s).

    // Resolution sync: push the browser's aligned resolution to Kit once connected.
    // The livestream app's resizeAppWindow handles the actual renderer resize; the
    // changeResolutionRequest is belt-and-suspenders confirmation via our ResolutionService.
    // Viewers skip — they observe the host's framebuffer as-is.
    useEffect(() => {
        if (!streamReady) return;

        if (isViewer) {
            setResolutionSynced(true);
            startedRef.current = true;
            onStarted();
            return;
        }

        onLoadingStatus?.(`Syncing resolution to ${desiredResolution.width}×${desiredResolution.height}…`);

        const t1 = window.setTimeout(() => {
            console.log(`[resolution] pushing ${desiredResolution.width}x${desiredResolution.height} to Kit`);
            sendCustomMessage('changeResolutionRequest', {
                width: desiredResolution.width,
                height: desiredResolution.height,
            });
        }, 50);

        // First sync: wait for Kit renderer to apply before showing stream
        if (!startedRef.current) {
            const t2 = window.setTimeout(() => {
                console.log(`[resolution] synced ${desiredResolution.width}x${desiredResolution.height}`);
                startedRef.current = true;
                resizeReconnectingRef.current = false;
                setResolutionSynced(true);
                onStarted();
            }, 400);
            return () => { window.clearTimeout(t1); window.clearTimeout(t2); };
        }

        return () => window.clearTimeout(t1);
    }, [streamReady, desiredResolution]);

    // Reconnect at the new aligned resolution when the browser viewport changes.
    // The NVST encoder max is set at connect time — resize requires a fresh connection
    // so the livestream app's resizeAppWindow sets the Kit renderer to the new size.
    //
    // A cooldown prevents rapid orientation flips from flooding Kit with ui.ready
    // messages (each reconnect sends one). The Kit-side streaming watchdog resets
    // all livestream extensions if 5+ ui.ready arrive within 30s, so we cap
    // reconnection frequency. If a resize fires during cooldown it is deferred
    // and applied once the cooldown expires.
    useEffect(() => {
        if (isViewer) return;

        let debounceTimer: number | null = null;

        const applyResize = () => {
            const next = getAlignedResolution(window.innerWidth, window.innerHeight);
            setDesiredResolution((prev) => {
                if (prev.width === next.width && prev.height === next.height) {
                    resizeReconnectingRef.current = false;
                    setResolutionSynced(true);
                    return prev;
                }
                lastResizeReconnectRef.current = Date.now();
                console.log(`[resolution] viewport changed: ${prev.width}x${prev.height} -> ${next.width}x${next.height}`);
                onLoadingStatus?.(`Resolution changed to ${next.width}×${next.height}, reconnecting…`);
                return next;
            });
        };

        const handleResize = () => {
            const next = getAlignedResolution(window.innerWidth, window.innerHeight);
            const cur = desiredResolutionRef.current;
            if (next.width !== cur.width || next.height !== cur.height) {
                resizeReconnectingRef.current = true;
                setResolutionSynced(false);
            }

            if (debounceTimer) window.clearTimeout(debounceTimer);
            debounceTimer = window.setTimeout(() => {
                const elapsed = Date.now() - lastResizeReconnectRef.current;
                if (elapsed < RESIZE_RECONNECT_COOLDOWN_MS) {
                    if (deferredResizeRef.current) window.clearTimeout(deferredResizeRef.current);
                    deferredResizeRef.current = window.setTimeout(applyResize, RESIZE_RECONNECT_COOLDOWN_MS - elapsed);
                    return;
                }
                applyResize();
            }, ORIENTATION_DEBOUNCE_MS);
        };

        window.addEventListener('resize', handleResize);
        window.addEventListener('orientationchange', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            window.removeEventListener('orientationchange', handleResize);
            if (debounceTimer) window.clearTimeout(debounceTimer);
            if (deferredResizeRef.current) window.clearTimeout(deferredResizeRef.current);
        };
    }, []);


    const source = StreamConfig.source;

    if (source === 'gfn') {
        return (
            <div
                id="view"
                style={{
                    backgroundColor: streamReady ? 'white': '#dddddd',
                    display: 'flex', justifyContent: 'space-between',
                    height: "100%",
                    width: "100%",
                    ...style
                }}
            />
        );
    } else if (source === 'local' || source === 'stream') {
        const showStream = streamReady && resolutionSynced;
        const resolutionAdjusting = !showStream && resizeReconnectingRef.current;
        return (
            <>
            {resolutionAdjusting && (
                <LoadingScreen message={t('loading.readjustingResolution')} />
            )}
            <div
                key={'stream-canvas'}
                id={'main-div'}
                className="stream-main-div stream-canvas-fill"
                style={{
                    backgroundColor: showStream ? 'transparent' : '#dddddd',
                    visibility: showStream ? 'visible' : 'hidden',
                    ...style
                }}
            >
                <video
                    key={'video-canvas'}
                    id={'remote-video'}
                    style={{
                        position: 'absolute',
                        left: 0,
                        top: 0,
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                        objectPosition: 'center',
                        touchAction: 'none',
                        zIndex: 0,
                    }}
                    tabIndex={-1}
                    playsInline muted
                    autoPlay
                    draggable={false}
                />
                {!isViewer && <BirdEyeRouteOverlay />}
                <audio id="remote-audio" muted></audio>
                <h3 style={{ visibility: 'hidden' }} id="message-display">...</h3>

                {isViewer && (
                    <div className="viewer-overlay" />
                )}

                <AppStreamSeatOverlays
                    isViewer={!!isViewer}
                    streamReady={streamReady}
                    handleCustomEvent={handleCustomEvent}
                    seatRouteStreamAudioMuted={seatRouteStreamAudioMuted}
                    setSeatRouteStreamAudioMuted={setSeatRouteStreamAudioMuted}
                    seatArrivalCelebrationVisible={!!seatArrivalCelebrationVisible}
                    seatArrivalLabel={seatArrivalLabel}
                    onArrivalDismiss={onArrivalDismiss}
                    poiArrivalVisible={!!poiArrivalVisible}
                    poiArrivalLabel={poiArrivalLabel}
                    onPoiArrivalDismiss={onPoiArrivalDismiss}
                    seatNavigationOverlay={seatNavigationOverlay}
                />
            </div>
            </>
        );
    }

    return null;
};


// Static methods for backward compatibility
(AppStreamCore as any).sendMessage = (message: any) => {
    AppStreamer.sendMessage(message);
};

(AppStreamCore as any).stop = () => {
    safeTerminateStream();
};

export default AppStreamCore;
