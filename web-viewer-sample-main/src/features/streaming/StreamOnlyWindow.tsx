/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 */
import React, { useEffect, useMemo, useRef, useCallback } from 'react';
import type { AppMode } from '../../context/AppModeContext';
import { useTranslation } from 'react-i18next';

import { AppStreamConnected } from './AppStream';
import './DarkMode.css';
import { AppProps } from './connection/Window';
import { registerViewTransitionBegin, useViewTransitionController } from './viewTransition';
import LoadingOverlay from './components/LoadingOverlay';
import PlacementButtons from './components/PlacementButtons';
import SkipToMainLink from './components/SkipToMainLink';

import { aiLanguageFor } from '../../services/aiLanguage';
import { useCustomEventHandler } from './hooks/useCustomEventHandler';
import { useAmbientSoundEngine } from './hooks/useAmbientSoundEngine';
import { useReleaseFocusOnStreamSurface } from './hooks/useReleaseFocusOnStreamSurface';
import {
    StreamProvider, useStream,
    EnvironmentProvider, useEnvironment,
    NavigationProvider, useNavigation,
    ControlProvider, useControl,
    ChatProvider, useChat,
    AppUIProvider, useAppUI,
    SpatialSoundProvider,
    Video360Provider,
    VideoBookSettingsProvider,
    StreamShellProvider,
    useStreamShell,
} from './contexts';
import { useAppMode } from '../../context/AppModeContext';

import SharedWidgetLayer from './SharedWidgetLayer';
import SharedOverlayLayer from './SharedOverlayLayer';
import DevViewLayer from './DevViewLayer';
import CuViewLayer from './CuViewLayer';
import GlobeViewOverlay from './overlays/globeView/GlobeViewOverlay';
import { peekGeoFromUrl, stripGeoQueryParamsFromWindowUrl, parseExploreGeoBridgePayload } from './geoTeleport';
import SpectatorJoinGate from './components/SpectatorJoinGate';
import './StreamOnlyWindow.css';
/**
 * Outer shell: spectator join gate + provider stack entry.
 */
const StreamOnlyWindow: React.FC<AppProps> = (props) => {
    const isViewer = props.isViewer ?? false;
    return (
        <StreamShellProvider isViewer={isViewer}>
            <StreamOnlyWindowBody appProps={props} />
        </StreamShellProvider>
    );
};

const StreamOnlyWindowBody: React.FC<{ appProps: AppProps }> = ({ appProps }) => {
    const isViewer = appProps.isViewer ?? false;
    const { viewerJoined, setViewerJoined } = useStreamShell();

    if (isViewer && !viewerJoined) {
        return <SpectatorJoinGate onJoin={() => setViewerJoined(true)} />;
    }

    return (
        <StreamProvider userId={appProps.userId} onStreamFailed={appProps.onStreamFailed} isViewer={isViewer}>
        <EnvironmentProvider>
        <NavigationProvider>
        <ControlProvider>
        <SpatialSoundProvider>
        <Video360Provider>
        <VideoBookSettingsProvider>
        <ChatProvider>
        <AppUIProvider isViewer={isViewer}>
            <StreamOnlyWindowInner appProps={appProps} />
        </AppUIProvider>
        </ChatProvider>
        </VideoBookSettingsProvider>
        </Video360Provider>
        </SpatialSoundProvider>
        </ControlProvider>
        </NavigationProvider>
        </EnvironmentProvider>
        </StreamProvider>
    );
};

/**
 * Inner component: all contexts are available here.
 * This is where the event handler wiring and rendering happens.
 */
const StreamOnlyWindowInner: React.FC<{ appProps: AppProps }> = ({ appProps }) => {
    const { t, i18n } = useTranslation();
    const { mode: appMode } = useAppMode();
    const appModeRef = useRef<AppMode>(appMode);
    appModeRef.current = appMode;

    const stream = useStream();
    const env = useEnvironment();
    const nav = useNavigation();
    const ctrl = useControl();
    const chat = useChat();
    const appUI = useAppUI();

    const viewTransitionCtrl = useViewTransitionController();

    useAmbientSoundEngine();
    useReleaseFocusOnStreamSurface(stream.streamReady);

    useEffect(() => {
        registerViewTransitionBegin(viewTransitionCtrl.begin);
        return () => registerViewTransitionBegin(null);
    }, [viewTransitionCtrl.begin]);

    // Deep link: explicit ?geo=… or both ?lat= and ?lon= — once per page load, never without those keys.
    const geoFromUrlConsumedRef = useRef(false);
    useEffect(() => {
        if (geoFromUrlConsumedRef.current) return;
        if (!stream.streamReady || stream.sceneLoading || appProps.isViewer) return;

        let u: URL;
        try {
            u = new URL(window.location.href);
        } catch {
            return;
        }
        const geoRaw = u.searchParams.get('geo');
        const hasGeoParam = geoRaw != null && String(geoRaw).trim() !== '';
        const latQ = u.searchParams.get('lat');
        const lonQ = u.searchParams.get('lon');
        const hasLatLonPair =
            latQ != null &&
            lonQ != null &&
            String(latQ).trim() !== '' &&
            String(lonQ).trim() !== '';
        if (!hasGeoParam && !hasLatLonPair) return;

        const coords = peekGeoFromUrl(window.location.href);
        if (!coords) return;

        console.log('[geoTeleport] deep link parsed from URL → will spawn', {
            href: window.location.href,
            coords,
        });

        geoFromUrlConsumedRef.current = true;
        stripGeoQueryParamsFromWindowUrl();
        nav.handleGeoTeleport(coords.lat, coords.lon, coords.height);
    }, [stream.streamReady, stream.sceneLoading, appProps.isViewer, nav.handleGeoTeleport]);

    // Chrome extension (web-plugin): content script → window.postMessage → same path as manual geo teleport.
    const streamReadyGeoBridgeRef = useRef(stream.streamReady);
    const sceneLoadingGeoBridgeRef = useRef(stream.sceneLoading);
    const isViewerGeoBridgeRef = useRef(appProps.isViewer);
    const handleGeoTeleportBridgeRef = useRef(nav.handleGeoTeleport);
    streamReadyGeoBridgeRef.current = stream.streamReady;
    sceneLoadingGeoBridgeRef.current = stream.sceneLoading;
    isViewerGeoBridgeRef.current = appProps.isViewer;
    handleGeoTeleportBridgeRef.current = nav.handleGeoTeleport;

    useEffect(() => {
        const onWindowMessage = (ev: MessageEvent) => {
            if (ev.source !== window) return;
            const coords = parseExploreGeoBridgePayload(ev.data);
            if (!coords) return;
            if (!streamReadyGeoBridgeRef.current || sceneLoadingGeoBridgeRef.current || isViewerGeoBridgeRef.current) {
                console.warn('[geoTeleport] bridge postMessage ignored (not ready, scene loading, or viewer mode)', {
                    streamReady: streamReadyGeoBridgeRef.current,
                    sceneLoading: sceneLoadingGeoBridgeRef.current,
                    isViewer: isViewerGeoBridgeRef.current,
                });
                return;
            }
            console.log('[geoTeleport] chrome bridge postMessage → spawn', coords);
            handleGeoTeleportBridgeRef.current(coords.lat, coords.lon, coords.height);
        };
        window.addEventListener('message', onWindowMessage);
        return () => window.removeEventListener('message', onWindowMessage);
    }, []);

    // Video focus for WASD mode
    useEffect(() => {
        if (!stream.streamReady || ctrl.controlMode !== 'wasd') return;
        const video = document.getElementById('remote-video') as HTMLVideoElement | null;
        if (!video) return;
        video.tabIndex = 0;
        video.focus();
        const refocus = (e: FocusEvent) => {
            // Tab/Shift+Tab sets relatedTarget to the next focusable — never steal focus back to the stream.
            if (e.relatedTarget) return;
            requestAnimationFrame(() => video.focus());
        };
        video.addEventListener('blur', refocus);
        return () => video.removeEventListener('blur', refocus);
    }, [stream.streamReady, ctrl.controlMode]);

    // Kit → React event handler bridge
    const events = useCustomEventHandler({
        appModeRef,
        setNavmeshActive: nav.setNavmeshActive,
        setShortcutsActive: nav.setShortcutsActive,
        setActiveSpotRouteId: nav.setActiveSpotRouteId,
        setMovingToSpotId: nav.setMovingToSpotId,
        setPlayerAutoMoveActive: nav.setPlayerAutoMoveActive,
        setOsmRouteOverlayAttached: nav.setOsmRouteOverlayAttached,
        setRouteMeasureByRouteId: nav.setRouteMeasureByRouteId,
        setRouteReadyByRouteId: nav.setRouteReadyByRouteId,
        markRouteCalculating: nav.markRouteCalculating,
        markRouteReady: nav.markRouteReady,
        setRouteError: nav.setRouteError,
        clearRouteError: nav.clearRouteError,
        setExitsResults: nav.setExitsResults,
        setActiveSeatRouteId: nav.setActiveSeatRouteId,
        setMovingToSeatId: nav.setMovingToSeatId,
        lastSeatPositionRef: nav.lastSeatPositionRef,
        seatRouteFromSeatRef: nav.seatRouteFromSeatRef,
        clearSeatRouteSwapState: nav.clearSeatRouteSwapState,
        setSeatingLayout: nav.setSeatingLayout,
        setAvailableSeatingLayouts: nav.setAvailableSeatingLayouts,
        setSeatedCrowdLayout: nav.setSeatedCrowdLayout,
        setAvailableSeatedCrowdLayouts: nav.setAvailableSeatedCrowdLayouts,
        setCameraDataHeatmapActive: env.setCameraDataHeatmapActive,
        setCameraDataTrackerActive: env.setCameraDataTrackerActive,
        setCameraDataStats: env.setCameraDataStats,
        setPeopleVisible: ctrl.setPeopleVisible,
        setLightCullingEnabled: ctrl.setLightCullingEnabled,
        setTileCullingEnabled: ctrl.setTileCullingEnabled,
        setActiveFixedCamera: env.setActiveFixedCamera,
        setPlacedCameras: env.setPlacedCameras,
        setUiInteractionBoxes: ctrl.setUiInteractionBoxes,
        setInteractionPointDefs: nav.setInteractionPointDefs,
        setNpcTestActive: ctrl.setNpcTestActive,
        setMaintenanceBotsActive: ctrl.setMaintenanceBotsActive,
        setCameraDepthStatus: env.setCameraDepthStatus,
        setCameraDepthPointCount: env.setCameraDepthPointCount,
        setCameraDepthObstacleCount: env.setCameraDepthObstacleCount,
        setCameraDepthPointsVisible: env.setCameraDepthPointsVisible,
        setCameraDepthAreasVisible: env.setCameraDepthAreasVisible,
        setNavmeshBaking: nav.setNavmeshBaking,
        setNavmeshMode: nav.setNavmeshMode,
        setCameraDataCalcActive: env.setCameraDataCalcActive,
        setCameraDataCalcBaking: env.setCameraDataCalcBaking,
        setSoundDataCalcActive: env.setSoundDataCalcActive,
        setSoundDataCalcBaking: env.setSoundDataCalcBaking,
        setActiveExitRouteId: nav.setActiveExitRouteId,
        setMovingToExitId: nav.setMovingToExitId,
        lastExitPrimPathRef: nav.lastExitPrimPathRef,
        setRestroomResults: nav.setRestroomResults,
        restroomResultsRef: nav.restroomResultsRef,
        setRestroomPoiListLoading: nav.setRestroomPoiListLoading,
        setActivePoiRouteId: nav.setActivePoiRouteId,
        activePoiRouteIdRef: nav.activePoiRouteIdRef,
        setMovingToPoiId: nav.setMovingToPoiId,
        lastPoiPrimPathRef: nav.lastPoiPrimPathRef,
        lastPoiDisplayNameRef: nav.lastPoiDisplayNameRef,
        lastPoiEndPosRef: nav.lastPoiEndPosRef,
        setRestroomWidgetOpen: nav.setRestroomWidgetOpen,
        setQuietZoneResults: nav.setQuietZoneResults,
        setQuietZonePoiListLoading: nav.setQuietZonePoiListLoading,
        quietZoneResultsRef: nav.quietZoneResultsRef,
        setActiveQuietZoneRouteId: nav.setActiveQuietZoneRouteId,
        activeQuietZoneRouteIdRef: nav.activeQuietZoneRouteIdRef,
        setMovingToQuietZoneId: nav.setMovingToQuietZoneId,
        lastQuietZonePrimPathRef: nav.lastQuietZonePrimPathRef,
        lastQuietZoneDisplayNameRef: nav.lastQuietZoneDisplayNameRef,
        setQuietZoneWidgetOpen: nav.setQuietZoneWidgetOpen,
        setQuietZoneTrackingScreen: nav.setQuietZoneTrackingScreen,
        setRestroomTrackingScreen: nav.setRestroomTrackingScreen,
        setTriggerZoneNotification: ctrl.setTriggerZoneNotification,
        triggerZoneTimerRef: ctrl.triggerZoneTimerRef,
        sceneLoadingRef: stream.sceneLoadingRef,
        navigationSpotsRef: nav.navigationSpotsRef,
        setOsmRouteInfo: nav.setOsmRouteInfo,
        setVideoList: ctrl.setVideoList,
        setVideoPlayerOpen: ctrl.setVideoPlayerOpen,
        setVideoPlayerConfig: ctrl.setVideoPlayerConfig,
        dispatchInteractionAction: chat.interactionActions.dispatch,
        setViewportCaptureStatus: appUI.setViewportCaptureStatus,
        setTransitLiveOverlayStatus: ctrl.setTransitLiveOverlayStatus,
        setStadiumLodLight: ctrl.setStadiumLodLight,
        setCurrentCamera: env.setCurrentCamera,
        setSeatArrivalCelebrationVisible: appUI.setSeatArrivalCelebrationVisible,
        seatArrivalCelebrationTimerRef: appUI.seatArrivalCelebrationTimerRef,
        setSeatArrivalLabel: appUI.setSeatArrivalLabel,
        setPoiArrivalVisible: appUI.setPoiArrivalVisible,
        poiArrivalTimerRef: appUI.poiArrivalTimerRef,
        setPoiArrivalLabel: appUI.setPoiArrivalLabel,
        setUsdEditPhase: ctrl.setUsdEditPhase,
        setNextClickSelectsVertex: ctrl.setNextClickSelectsVertex,
        setNextClickSelectsPrim: ctrl.setNextClickSelectsPrim,
        setSelectedVertexInfo: ctrl.setSelectedVertexInfo,
        setEditingMeshPath: ctrl.setEditingMeshPath,
        setEditingVertexCount: ctrl.setEditingVertexCount,
        setTransformInfo: ctrl.setTransformInfo,
        setUsdEditSaveStatus: ctrl.setUsdEditSaveStatus,
        setSublayerList: ctrl.setSublayerList,
        setMarkerPlacementArmed: ctrl.setMarkerPlacementArmed,
        setSelectedMarkerInfo: ctrl.setSelectedMarkerInfo,
        measureModeRef: ctrl.measureModeRef,
        measurePoint1Ref: ctrl.measurePoint1Ref,
        setMeasureMode: ctrl.setMeasureMode,
        setMeasurePoint1: ctrl.setMeasurePoint1,
        setMeasurePoint2: ctrl.setMeasurePoint2,
        setMeasureResult: ctrl.setMeasureResult,
        setAvailableScenes: appUI.setAvailableScenes,
        setNearestNpc: ctrl.setNearestNpc,
        setNearestIcon: ctrl.setNearestIcon,
        // World state sync setters
        setWeather: env.setWeather,
        setSeason: env.setSeason,
        setTimeOfDayMinutes: env.setTimeOfDayMinutes,
        setCameraHeight: env.setCameraHeight,
        setFogIntensity: env.setFogIntensity,
        setTimeOfDay: env.setTimeOfDay,
        setDayOfYear: env.setDayOfYear,
        setCloudCoverage: env.setCloudCoverage,
        setCumulusEnabled: env.setCumulusEnabled,
        setWeatherPreset: env.setWeatherPreset,
        setCurrentPhysics: env.setCurrentPhysics,
        setMovementSpeed: env.setMovementSpeed,
        setFirstPersonLocation: env.setFirstPersonLocation,
        setBirdEyeRoutePoints: ctrl.setBirdEyeRoutePoints,
        openMapMarkerSheet: nav.openMapMarkerSheet,
        setMediaAdminKitRegistry: ctrl.setMediaAdminKitRegistry,
        setMediaContentTheme: ctrl.setMediaContentTheme,
        setDevLocaleWriteStatus: ctrl.setDevLocaleWriteStatus,
        setAccessibilityDiffVisible: nav.setAccessibilityDiffVisible,
        setNavmeshDebugOverlayVisible: nav.setNavmeshDebugOverlayVisible,
    });

    const combinedHandleCustomEvent = useMemo(
        () => events.createCombinedHandler(stream.processSceneEvent),
        [events, stream.processSceneEvent],
    );

    const handleGlobeExit = useCallback((targetView: import('./types').CameraType) => {
        env.handleCameraChange(targetView);
    }, [env]);

    // AI agent event handler
    const avatarAgentHandlerRegistered = useRef(false);
    useEffect(() => {
        if (avatarAgentHandlerRegistered.current) return;
        avatarAgentHandlerRegistered.current = true;

        const handler = (evt: any) => {
            if (!evt?.event_type) return;
            const p = evt.payload || evt;
            const avatarId = p.avatarId ?? p.avatar_id ?? 'default';

            if (evt.event_type === 'ai.agent.typing') {
                chat.setAvatarAgentTyping(true);
            } else if (evt.event_type === 'ai.agent.done') {
                chat.setAvatarAgentTyping(false);
            } else if (evt.event_type === 'ai.agent.response') {
                chat.setAvatarAgentTyping(false);
                const text = p.text ?? '';
                if (text) {
                    // AI replies in the language we asked for in the request.
                    // Prefer the backend-echoed `language` when present; fall
                    // back to whatever `aiLanguageFor` mapped the UI to (en/sv
                    // for now). This drives the "Listen" voice so French/
                    // Spanish UIs don't try to pronounce English text with a
                    // French/Spanish voice.
                    const lang = String(p.language ?? aiLanguageFor(i18n.language));
                    chat.conversation.addMessage(avatarId, { role: 'assistant', text, lang });
                }
            } else if (evt.event_type === 'ai.agent.error') {
                chat.setAvatarAgentTyping(false);
                // Backend may send an error string in the AI's reply language;
                // when it doesn't, we substitute a UI-localized message.
                const backendText = typeof p.text === 'string' ? p.text : '';
                const errText = backendText || t('streaming.genericError');
                const lang = backendText
                    ? String(p.language ?? aiLanguageFor(i18n.language))
                    : i18n.language;
                chat.conversation.addMessage(avatarId, { role: 'assistant', text: errText, isError: true, lang });
            }
        };
        combinedHandleCustomEvent(handler);
    }, [combinedHandleCustomEvent, chat, t, i18n.language]);

    useEffect(() => {
        if (stream.loadingPhase.phase === 'ready') env.setActiveFixedCamera(null);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [stream.loadingPhase.phase]);

    useEffect(() => {
        return () => { env.cleanupDebounces(); ctrl.cleanupTimers(); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return (
        <div className="stream-only-window">
            <SkipToMainLink />

            <LoadingOverlay />

            <PlacementButtons />

            <main
                id="main-content"
                aria-label={t('app.mainLandmark')}
                tabIndex={-1}
                className="stream-only-window__main"
            ><div
                id="streamonly-wrapper"
                className={`stream-only-wrapper ${stream.streamReady ? 'stream-only-wrapper--visible' : 'stream-only-wrapper--hidden'}`}
            >
                <span
                    id="main-viewer-focus-start"
                    tabIndex={-1}
                    className="sr-only"
                >
                    {t('app.mainLandmark')}
                </span>

                <SharedWidgetLayer />

                <SharedOverlayLayer
                    viewTransitionOverlay={!appUI.seatArrivalCelebrationVisible && !appUI.poiArrivalVisible && stream.streamReady ? viewTransitionCtrl.overlay : null}
                />

                {!appUI.seatArrivalCelebrationVisible && !appUI.poiArrivalVisible && !appUI.onboardingVisible && appMode === 'dev' && !ctrl.avatarChatOpen && env.currentCamera !== 'space' && (
                    <DevViewLayer />
                )}

                <AppStreamConnected
                    key={stream.appStreamKey}
                    appProps={appProps}
                    handleCustomEvent={combinedHandleCustomEvent}
                />

                {appMode === 'cu' && <CuViewLayer />}
            </div></main>

            {env.currentCamera === 'space' && (
                <GlobeViewOverlay onExitToView={handleGlobeExit} />
            )}

            {appUI.isViewer && stream.streamReady && (
                <div className="viewer-badge">{t('streaming.viewOnly')}</div>
            )}
        </div>
    );
};

export default StreamOnlyWindow;
