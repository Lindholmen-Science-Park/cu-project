import React, { createContext, useContext, useState, useCallback, useRef, useEffect, useLayoutEffect, useMemo } from 'react';
import { useNavigation } from './NavigationContext';
import { useStream } from './StreamContext';
import { useEnvironment } from './EnvironmentContext';

/** Stable interaction id of the bird-eye arena map marker (see `interactions.json`). */
const ARENA_MAP_MARKER_ID = 'map_marker_arena';

export interface AppUIContextType {
    isViewer: boolean;
    onboardingVisible: boolean;
    handleOnboardingDone: () => void;
    invertTouchLook: boolean;
    handleInvertTouchLookToggle: () => void;
    availableScenes: Array<{ id: string; label: string }>;
    setAvailableScenes: React.Dispatch<React.SetStateAction<Array<{ id: string; label: string }>>>;
    viewportCaptureStatus: 'idle' | 'capturing';
    setViewportCaptureStatus: React.Dispatch<React.SetStateAction<'idle' | 'capturing'>>;
    // Seat ceremony
    seatArrivalCelebrationVisible: boolean;
    setSeatArrivalCelebrationVisible: React.Dispatch<React.SetStateAction<boolean>>;
    seatArrivalCelebrationTimerRef: React.MutableRefObject<number | null>;
    seatArrivalLabel: string | null;
    setSeatArrivalLabel: React.Dispatch<React.SetStateAction<string | null>>;
    seatForceExpandSignal: number;
    setSeatForceExpandSignal: React.Dispatch<React.SetStateAction<number>>;
    seatPanelStickyOpen: boolean;
    setSeatPanelStickyOpen: React.Dispatch<React.SetStateAction<boolean>>;
    seatPanelDraft: { section: string; row: string; seat: string };
    setSeatPanelDraft: React.Dispatch<React.SetStateAction<{ section: string; row: string; seat: string }>>;
    seatStreamOverlayActive: boolean;
    restroomStreamOverlayActive: boolean;
    quietStreamOverlayActive: boolean;
    streamNavOverlayActive: boolean;
    seatRouteCuPortalEl: HTMLElement | null;
    closeSeatPanel: () => void;
    dismissArrivalCelebration: () => void;
    // POI arrival (restroom/quiet zone) — top bar without celebration image
    poiArrivalVisible: boolean;
    setPoiArrivalVisible: React.Dispatch<React.SetStateAction<boolean>>;
    poiArrivalTimerRef: React.MutableRefObject<number | null>;
    poiArrivalLabel: string | null;
    setPoiArrivalLabel: React.Dispatch<React.SetStateAction<string | null>>;
    dismissPoiArrival: () => void;
    handleSearchChipNavigate: (intent: 'seat' | 'restroom' | 'quiet') => void;
}

const AppUIContext = createContext<AppUIContextType | null>(null);

export function AppUIProvider({ isViewer, children }: {
    isViewer: boolean;
    children: React.ReactNode;
}) {
    const nav = useNavigation();
    const stream = useStream();
    const env = useEnvironment();

    const [onboardingVisible, setOnboardingVisible] = useState(true);
    const handleOnboardingDone = useCallback(() => {
        setOnboardingVisible(false);
        requestAnimationFrame(() => {
            const active = document.activeElement;
            if (active instanceof HTMLElement && active !== document.body) {
                active.blur();
            }
        });
    }, []);

    const [invertTouchLook, setInvertTouchLook] = useState(true);
    const handleInvertTouchLookToggle = useCallback(() => setInvertTouchLook(prev => !prev), []);

    const [availableScenes, setAvailableScenes] = useState<{ id: string; label: string }[]>([]);
    const [viewportCaptureStatus, setViewportCaptureStatus] = useState<'idle' | 'capturing'>('idle');

    // Seat ceremony state
    const [seatArrivalCelebrationVisible, setSeatArrivalCelebrationVisible] = useState(false);
    const seatArrivalCelebrationTimerRef = useRef<number | null>(null);
    const [seatArrivalLabel, setSeatArrivalLabel] = useState<string | null>(null);
    const [seatForceExpandSignal, setSeatForceExpandSignal] = useState(0);
    const [seatPanelStickyOpen, setSeatPanelStickyOpen] = useState(false);
    const [seatPanelDraft, setSeatPanelDraft] = useState<{ section: string; row: string; seat: string }>({ section: '', row: '', seat: '' });

    /**
     * Stream-side navigation overlay (with the auto-move "play" FAB) is
     * gated on Kit's `navmeshRouteReady` ping (relayed from
     * `navmeshRouteWaypoints` success). Without this gate the overlay
     * activates the moment the user clicks "Get directions" — before Kit
     * has confirmed the route exists or finished pathfinding — and the
     * FAB flickers / silently no-ops on failure.
     *
     * The corresponding panels (seat panel, restroom widget, quiet-zone
     * widget) stay visible while the gate is closed because their hide
     * conditions watch these same flags. That gives the user a "panel
     * stays open while route is calculating, then collapses to overlay
     * once the route is drawable" behaviour without any static waits.
     */
    const seatStreamOverlayActive =
        !isViewer &&
        stream.streamReady &&
        !!nav.activeSeatRouteId &&
        !nav.activeSeatRouteId.includes(':') &&
        nav.routeReadyByRouteId['seat_nav'] === true;

    /** Active route to POI — stream play/stop overlay (hidden during map-marker route preview before Start navigation, and while Kit is still calculating). */
    const restroomStreamOverlayActive =
        !isViewer &&
        stream.streamReady &&
        !!nav.activePoiRouteId &&
        !(nav.mapMarkerDirectionsPreview != null && !nav.movingToPoiId) &&
        nav.routeReadyByRouteId['poi_nav'] === true;

    const quietStreamOverlayActive =
        !isViewer &&
        stream.streamReady &&
        nav.quietZoneWidgetOpen &&
        !!nav.activeQuietZoneRouteId &&
        nav.routeReadyByRouteId['quiet_zone_nav'] === true;

    const streamNavOverlayActive = seatStreamOverlayActive || restroomStreamOverlayActive || quietStreamOverlayActive;

    const [seatRouteCuPortalEl, setSeatRouteCuPortalEl] = useState<HTMLElement | null>(null);
    useLayoutEffect(() => {
        if (!streamNavOverlayActive) { setSeatRouteCuPortalEl(null); return; }
        const el = document.getElementById('stream-seat-nav-cu-controls-root');
        setSeatRouteCuPortalEl(el);
    }, [streamNavOverlayActive, stream.streamReady]);

    const closeSeatPanel = useCallback(() => {
        setSeatPanelStickyOpen(false);
        nav.setSeatWidgetOpen(false);
        setSeatPanelDraft({ section: '', row: '', seat: '' });
        nav.clearBirdEyeMapMarkerFocus();
    }, [nav.setSeatWidgetOpen, nav.clearBirdEyeMapMarkerFocus]);

    const dismissArrivalCelebration = useCallback(() => {
        setSeatArrivalCelebrationVisible(false);
        setSeatArrivalLabel(null);
        if (seatArrivalCelebrationTimerRef.current) {
            window.clearTimeout(seatArrivalCelebrationTimerRef.current);
            seatArrivalCelebrationTimerRef.current = null;
        }
    }, []);

    // POI arrival state (restroom / quiet zone)
    const [poiArrivalVisible, setPoiArrivalVisible] = useState(false);
    const poiArrivalTimerRef = useRef<number | null>(null);
    const [poiArrivalLabel, setPoiArrivalLabel] = useState<string | null>(null);

    const dismissPoiArrival = useCallback(() => {
        setPoiArrivalVisible(false);
        setPoiArrivalLabel(null);
        if (poiArrivalTimerRef.current) {
            window.clearTimeout(poiArrivalTimerRef.current);
            poiArrivalTimerRef.current = null;
        }
    }, []);

    const handleSearchChipNavigate = useCallback((intent: 'seat' | 'restroom' | 'quiet') => {
        const isBirdEye = env.currentCamera === 'bird_eye';
        if (intent === 'seat') {
            if (nav.restroomWidgetOpen) nav.handleRestroomWidgetClose();
            if (nav.quietZoneWidgetOpen) nav.handleQuietZoneWidgetClose();
            // Bird-eye: highlight the arena pin so the visual state matches
            // tapping the in-world "Find my seat" map marker (see
            // `InteractionBoxesOverlay.handleMapMarkerActivate`). Search
            // overlay close is handled by ControlsMenu.
            if (isBirdEye) {
                nav.openFindMySeatFromBirdEyeMap(ARENA_MAP_MARKER_ID);
            }
            setSeatForceExpandSignal((s) => s + 1);
            setSeatPanelStickyOpen(true);
            nav.setSeatWidgetOpen(true);
        } else if (intent === 'restroom') {
            closeSeatPanel();
            if (nav.quietZoneWidgetOpen) nav.handleQuietZoneWidgetClose();
            nav.handleOpenRestroomWidget();
        } else if (intent === 'quiet') {
            closeSeatPanel();
            if (nav.restroomWidgetOpen) nav.handleRestroomWidgetClose();
            nav.handleOpenQuietZoneWidget();
        }
    }, [nav, closeSeatPanel, env.currentCamera]);

    // Sync effects
    useEffect(() => {
        if (!seatPanelStickyOpen) return;
        if (nav.seatWidgetOpen) return;
        nav.setSeatWidgetOpen(true);
    }, [seatPanelStickyOpen, nav.seatWidgetOpen, nav.setSeatWidgetOpen]);

    useEffect(() => {
        if (!seatArrivalCelebrationVisible) return;
        closeSeatPanel();
    }, [seatArrivalCelebrationVisible, closeSeatPanel]);

    useEffect(() => {
        if (!seatArrivalCelebrationVisible) setSeatArrivalLabel(null);
    }, [seatArrivalCelebrationVisible]);

    useEffect(() => {
        if (!nav.movingToSeatId) return;
        setSeatArrivalCelebrationVisible(false);
        if (seatArrivalCelebrationTimerRef.current) {
            window.clearTimeout(seatArrivalCelebrationTimerRef.current);
            seatArrivalCelebrationTimerRef.current = null;
        }
    }, [nav.movingToSeatId]);

    useEffect(() => {
        if (!poiArrivalVisible) setPoiArrivalLabel(null);
    }, [poiArrivalVisible]);

    useEffect(() => {
        return () => {
            if (seatArrivalCelebrationTimerRef.current) window.clearTimeout(seatArrivalCelebrationTimerRef.current);
            if (poiArrivalTimerRef.current) window.clearTimeout(poiArrivalTimerRef.current);
        };
    }, []);

    const value = useMemo<AppUIContextType>(() => ({
        isViewer,
        onboardingVisible, handleOnboardingDone,
        invertTouchLook, handleInvertTouchLookToggle,
        availableScenes, setAvailableScenes,
        viewportCaptureStatus, setViewportCaptureStatus,
        seatArrivalCelebrationVisible, setSeatArrivalCelebrationVisible,
        seatArrivalCelebrationTimerRef,
        seatArrivalLabel, setSeatArrivalLabel,
        seatForceExpandSignal, setSeatForceExpandSignal,
        seatPanelStickyOpen, setSeatPanelStickyOpen,
        seatPanelDraft, setSeatPanelDraft,
        seatStreamOverlayActive, restroomStreamOverlayActive, quietStreamOverlayActive, streamNavOverlayActive,
        seatRouteCuPortalEl,
        closeSeatPanel, dismissArrivalCelebration,
        poiArrivalVisible, setPoiArrivalVisible, poiArrivalTimerRef,
        poiArrivalLabel, setPoiArrivalLabel, dismissPoiArrival,
        handleSearchChipNavigate,
    }), [
        isViewer,
        onboardingVisible, handleOnboardingDone,
        invertTouchLook, handleInvertTouchLookToggle,
        availableScenes, viewportCaptureStatus,
        seatArrivalCelebrationVisible, seatArrivalLabel,
        seatForceExpandSignal, seatPanelStickyOpen, seatPanelDraft,
        seatStreamOverlayActive, restroomStreamOverlayActive, quietStreamOverlayActive, streamNavOverlayActive,
        seatRouteCuPortalEl,
        closeSeatPanel, dismissArrivalCelebration,
        poiArrivalVisible, poiArrivalLabel, dismissPoiArrival,
        handleSearchChipNavigate,
    ]);

    return <AppUIContext.Provider value={value}>{children}</AppUIContext.Provider>;
}

export function useAppUI(): AppUIContextType {
    const ctx = useContext(AppUIContext);
    if (!ctx) throw new Error('useAppUI must be used within AppUIProvider');
    return ctx;
}

export { AppUIContext };
