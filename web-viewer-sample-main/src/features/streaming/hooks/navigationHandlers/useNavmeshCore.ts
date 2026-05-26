import { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import i18n from '../../../../i18n';
import { sendMessage } from '../../messaging';
import type { RouteMeasure } from '../../types';
import type { CameraType } from '../../types';
import { NavigationSpot, InteractionPointDef } from '../../types';
import { beginGeoTeleport } from '../../geoTeleport';
import { beginViewTransition } from '../../viewTransition';
import type { RouteErrorAnnouncement } from '../../utils/navRouteErrorMessages';

export function useNavmeshCore(
    streamReady: boolean,
    currentCamera: CameraType,
    setCurrentCamera: (camera: CameraType) => void,
) {
    const [navmeshActive, setNavmeshActive] = useState(false);
    const [navmeshMode, setNavmeshMode] = useState<'wheelchair' | 'walking'>('walking');
    const [navmeshBaking, setNavmeshBaking] = useState(false);
    const [routeMeasureByRouteId, setRouteMeasureByRouteId] = useState<Record<string, RouteMeasure>>({});
    const [routeMeasureEnabled, setRouteMeasureEnabled] = useState(true);
    /**
     * Per-routeId "waypoints generated" flag, set on Kit's `navmeshRouteReady`
     * event. Used by `AppUIContext` to gate the navigation stream overlays
     * (and the auto-move "play" FAB) so they only appear AFTER the route is
     * actually drawable — without this gate they activate optimistically the
     * moment the user clicks "Get directions" and flicker / fire silent
     * no-ops if Kit's pathfinding fails or hasn't finished yet.
     *
     * Reset to false whenever a new `navmeshRouteCalculate` is sent for the
     * same routeId, when the route is stopped, when it errors, and on
     * arrival — call `markRouteCalculating(routeId)` at the dispatch site
     * so the gate closes before Kit's confirmation arrives.
     */
    const [routeReadyByRouteId, setRouteReadyByRouteId] = useState<Record<string, boolean>>({});
    /** Kit `navmeshRouteError` copy for POI / directions widgets (WCAG 4.1.3). */
    const [routeErrorByRouteId, setRouteErrorByRouteId] = useState<
        Record<string, RouteErrorAnnouncement>
    >({});

    const clearRouteError = useCallback((routeId: string) => {
        if (!routeId) return;
        setRouteErrorByRouteId((prev) => {
            if (!prev[routeId]) return prev;
            const next = { ...prev };
            delete next[routeId];
            return next;
        });
    }, []);

    const setRouteError = useCallback((routeId: string, error: RouteErrorAnnouncement) => {
        if (!routeId) return;
        setRouteErrorByRouteId((prev) => ({ ...prev, [routeId]: error }));
    }, []);

    const markRouteCalculating = useCallback(
        (routeId: string) => {
            if (!routeId) return;
            setRouteReadyByRouteId((prev) => {
                if (prev[routeId] !== true) return prev;
                const next = { ...prev };
                delete next[routeId];
                return next;
            });
            clearRouteError(routeId);
        },
        [clearRouteError],
    );

    const markRouteReady = useCallback(
        (routeId: string, ready: boolean) => {
            if (!routeId) return;
            setRouteReadyByRouteId((prev) => {
                const cur = prev[routeId] === true;
                if (cur === ready) return prev;
                const next = { ...prev };
                if (ready) next[routeId] = true;
                else delete next[routeId];
                return next;
            });
            if (ready) clearRouteError(routeId);
        },
        [clearRouteError],
    );
    const [avoidCrowds, setAvoidCrowds] = useState(false);
    const [avoidNoise, setAvoidNoise] = useState(false);
    const [pointClickCostsActive, setPointClickCostsActive] = useState(false);
    /**
     * Shortcut routing toggle (dev-only entry point for now).
     *
     * When `true`, guided routes (seat_nav / exit_nav / poi_nav /
     * quiet_zone_nav) ask Kit's `RouteComposer` to consider elevator
     * (and future bus-stop / tunnel / stairs) hops in pathfinding. The
     * Kit-side `ShortcutTraversalService` then handles the fade +
     * teleport + resume on the entrance vertex.
     *
     * Off by default so production CU behaviour is unchanged. The CU
     * "Prefer Elevators" setting in PreferencesGrids does not yet
     * dispatch to Kit — wiring is a future task; the dev toggle below
     * (`preferShortcutsActive`) covers test coverage in dev builds.
     */
    const [shortcutsActive, setShortcutsActive] = useState(false);
    /**
     * "Prefer elevators" sub-toggle (dev-only). Mirrors the future CU
     * preference. Effective only while `shortcutsActive` is also true.
     *
     * - Off (default): the composer picks the **strict shortest** of
     *   walking and elevator routes.
     * - On: the composer always picks the elevator route when a
     *   **valid** hop exists (vertical filters in `ShortcutRouter`
     *   reject basement-dip / wrong-way / same-band-dip rides), even
     *   when walking would be shorter.
     */
    const [preferShortcutsActive, setPreferShortcutsActive] = useState(false);
    /** Dev: translucent OSM walk-graph overlay (`OsmRouteOverlayService`). */
    const [osmRouteOverlayVisible, setOsmRouteOverlayVisible] = useState(false);
    const [osmRouteOverlayRoadSnap, setOsmRouteOverlayRoadSnap] = useState(false);
    /**
     * Whether the player route is currently being auto-walked by Kit's
     * `PointClickAutoMover`. Toggled from `handleAutoMoveStatus` when an
     * `autoMoveStatus` event with `routeId === 'player'` arrives. Drives
     * the OSM route overlay Play/Pause FAB icon — the FAB optimistically
     * flips to "playing" on Play press, but the source of truth is
     * whatever Kit reports back.
     */
    const [playerAutoMoveActive, setPlayerAutoMoveActive] = useState(false);
    /**
     * Whether the player is currently "bound" to the OSM route overlay —
     * i.e. they tapped a route (and Kit successfully attached them to
     * the polyline) and haven't tapped plain NavMesh since. Mirrored
     * from Kit's `osmRouteOverlayAttached` event so the auto-advance
     * Play/Pause FAB only renders when pressing it would actually do
     * something. Doubles as visual feedback for the "did my last click
     * land on the route or jump me off?" question — when the FAB hides
     * the user knows their click was treated as NavMesh.
     *
     * Auto-resets to false whenever the overlay itself is hidden, so a
     * stale "attached" state from a previous session can't leak into a
     * fresh visibility toggle before Kit has had a chance to confirm.
     */
    const [osmRouteOverlayAttached, setOsmRouteOverlayAttached] = useState(false);
    const [interactionPointDefs, setInteractionPointDefs] = useState<InteractionPointDef[]>([]);
    /** Dev Tools: dual-mesh stair diff overlay (Kit viewport). */
    const [accessibilityDiffVisible, setAccessibilityDiffVisible] = useState(false);
    /** Dev Tools: full active NavMesh triangulation overlay. */
    const [navmeshDebugOverlayVisible, setNavmeshDebugOverlayVisible] = useState(false);

    const navigationSpots: NavigationSpot[] = useMemo(() =>
        interactionPointDefs
            .filter((p) => p.category === 'navigation' && p.position?.primPath)
            .map((p) => ({
                id: p.id,
                label: p.label || p.id,
                icon: p.id.startsWith('wheelchair') ? '\u267F' : '\uD83D\uDCBA',
                primPath: p.position!.primPath!,
            })),
        [interactionPointDefs]
    );

    const navigationSpotsRef = useRef(navigationSpots);
    navigationSpotsRef.current = navigationSpots;

    useEffect(() => {
        if (!streamReady) return;
        try { sendMessage('routeMeasureSet', { enabled: routeMeasureEnabled }); } catch {}
    }, [streamReady, routeMeasureEnabled]);

    useEffect(() => {
        if (!streamReady) return;
        try {
            sendMessage('osmRouteOverlaySet', {
                visible: osmRouteOverlayVisible,
                roadSnap: osmRouteOverlayRoadSnap,
            });
        } catch { /* noop */ }
    }, [streamReady, osmRouteOverlayVisible, osmRouteOverlayRoadSnap]);

    // Defensive reset: when the user hides the overlay, drop the
    // attached flag immediately rather than waiting for Kit's
    // `osmRouteOverlayAttached { attached: false }` confirmation.
    // Hiding the overlay always means the FAB should disappear, and
    // the round-trip latency would otherwise let it linger for a
    // visible frame — confusing in dev mode where rapid toggling is
    // common.
    useEffect(() => {
        if (!osmRouteOverlayVisible && osmRouteOverlayAttached) {
            setOsmRouteOverlayAttached(false);
        }
    }, [osmRouteOverlayVisible, osmRouteOverlayAttached]);

    const handleNavmeshToggle = useCallback((cctv1TrafficValue: number, cameraCosts: Record<string, number>, soundCosts: Record<string, number>) => {
        const newState = !navmeshActive;
        setNavmeshActive(newState);
        console.log(`NavMesh navigation ${newState ? 'starting' : 'stopping'}`);
        if (newState) {
            const allCosts: Record<string, number> = { cctv1_navmesh_area: cctv1TrafficValue, ...cameraCosts, ...soundCosts };
            sendMessage('navmeshRouteCalculate', { routeId: 'default', startpointPath: '/World/PlayerCharacter', endpointPath: '/World/EndPoint_Cube', cameraAreaCosts: allCosts });
        } else {
            sendMessage('navmeshRouteStop', { routeId: 'default' });
        }
    }, [navmeshActive]);

    const handleRouteMeasureToggle = useCallback(() => {
        setRouteMeasureEnabled((prev) => {
            const next = !prev;
            try { sendMessage('routeMeasureSet', { enabled: next }); } catch {}
            return next;
        });
    }, []);

    const revertWheelchairMode = useCallback(() => {
        if (navmeshMode !== 'wheelchair') return;
        setNavmeshMode('walking');
        try { sendMessage('navmeshModeSet', { mode: 'walking' }); } catch {}
    }, [navmeshMode]);

    // Mode swap is an instant pointer swap on the dual-mode NavMesh cache
    // (`navmesh-dual-mode.mdc`). No baking gate needed — concurrent orchestrator
    // rebakes (incidents / area providers) refresh both cached handles in
    // place so the user's mode preference stays valid throughout.
    //
    // Single source of truth for the toggle UI (CU "Exploring mode" radio in
    // `World3dSettings` + dev sidebar) is `navmeshMode` here. Kit owns the
    // persisted runtime state and rehydrates React via the `worldStateSync`
    // snapshot on connect/reconnect (see `world-state-sync.mdc`), so no
    // browser-side persistence is needed.
    const handleNavmeshModeChange = useCallback((mode: 'wheelchair' | 'walking') => {
        setNavmeshMode(mode);
        try { sendMessage('navmeshModeSet', { mode }); } catch {}
    }, []);

    const handleAvoidCrowdsToggle = useCallback(() => {
        const next = !avoidCrowds;
        setAvoidCrowds(next);
        sendMessage('navmeshCostCategoryToggle', { category: 'crowd', active: next });
    }, [avoidCrowds]);

    const handleAvoidNoiseToggle = useCallback(() => {
        const next = !avoidNoise;
        setAvoidNoise(next);
        sendMessage('navmeshCostCategoryToggle', { category: 'sound', active: next });
    }, [avoidNoise]);

    const handlePreferQuietAreas = useCallback(() => {
        setAvoidNoise((prev) => {
            if (prev) return prev;
            try {
                sendMessage('navmeshCostCategoryToggle', { category: 'sound', active: true });
            } catch {}
            return true;
        });
    }, []);

    const handlePointClickCostsToggle = useCallback(() => {
        const next = !pointClickCostsActive;
        setPointClickCostsActive(next);
        sendMessage('navmeshCostCategoryToggle', { category: 'player', active: next });
    }, [pointClickCostsActive]);

    const handleShortcutsToggle = useCallback(() => {
        const next = !shortcutsActive;
        setShortcutsActive(next);
        try {
            sendMessage('shortcutsToggle', { active: next });
        } catch {}
    }, [shortcutsActive]);

    const handlePreferShortcutsToggle = useCallback(() => {
        const next = !preferShortcutsActive;
        setPreferShortcutsActive(next);
        try {
            sendMessage('shortcutsPreferToggle', { active: next });
        } catch {}
    }, [preferShortcutsActive]);

    const handlePoiTeleport = useCallback((primPath: string, options?: { transitionMessageKey?: string }) => {
        if (!primPath) return;
        const msgKey = options?.transitionMessageKey || 'streaming.switchingFirstPerson';
        beginViewTransition({
            target: 'firstPerson',
            message: i18n.t(msgKey),
            onFadeOutComplete: () => {
                try {
                    if (currentCamera === 'bird_eye') {
                        sendMessage('poiTeleportFromBirdEye', { primPath });
                        setCurrentCamera('first_person');
                    } else {
                        sendMessage('poiTeleport', { primPath });
                    }
                } catch { /* stream */ }
                console.log(`POI teleport request sent: ${primPath}`);
            },
        });
    }, [currentCamera, setCurrentCamera]);

    const handleGeoTeleport = useCallback(
        (lat: number, lon: number, height?: number) => {
            if (!streamReady) return;
            if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
            beginGeoTeleport({
                lat,
                lon,
                ...(height != null && Number.isFinite(height) ? { height } : {}),
            });
        },
        [streamReady],
    );

    const handleOsmRouteOverlayToggle = useCallback(() => {
        setOsmRouteOverlayVisible((v) => !v);
    }, []);

    const handleOsmRouteOverlayRoadSnapToggle = useCallback(() => {
        setOsmRouteOverlayRoadSnap((v) => !v);
    }, []);

    const handleAccessibilityDiffToggle = useCallback(() => {
        const next = !accessibilityDiffVisible;
        setAccessibilityDiffVisible(next);
        try {
            sendMessage('accessibilityDiffShow', { visible: next });
        } catch { /* noop */ }
    }, [accessibilityDiffVisible]);

    const handleNavmeshDebugOverlayToggle = useCallback(() => {
        const next = !navmeshDebugOverlayVisible;
        setNavmeshDebugOverlayVisible(next);
        try {
            sendMessage('navmeshDebugShow', { visible: next });
        } catch { /* noop */ }
    }, [navmeshDebugOverlayVisible]);

    return {
        navmeshActive, setNavmeshActive,
        navmeshMode, setNavmeshMode,
        navmeshBaking, setNavmeshBaking,
        routeMeasureByRouteId, setRouteMeasureByRouteId,
        routeReadyByRouteId, setRouteReadyByRouteId,
        routeErrorByRouteId,
        setRouteError,
        clearRouteError,
        markRouteCalculating, markRouteReady,
        routeMeasureEnabled,
        avoidCrowds, avoidNoise,
        pointClickCostsActive,
        shortcutsActive, setShortcutsActive,
        preferShortcutsActive, setPreferShortcutsActive,
        osmRouteOverlayVisible,
        setOsmRouteOverlayVisible,
        osmRouteOverlayRoadSnap,
        setOsmRouteOverlayRoadSnap,
        playerAutoMoveActive,
        setPlayerAutoMoveActive,
        osmRouteOverlayAttached,
        setOsmRouteOverlayAttached,
        handleOsmRouteOverlayToggle,
        handleOsmRouteOverlayRoadSnapToggle,
        interactionPointDefs, setInteractionPointDefs,
        navigationSpots, navigationSpotsRef,
        handleNavmeshToggle,
        handleRouteMeasureToggle,
        revertWheelchairMode,
        handleNavmeshModeChange,
        handleAvoidCrowdsToggle,
        handleAvoidNoiseToggle,
        handlePreferQuietAreas,
        handlePointClickCostsToggle,
        handleShortcutsToggle,
        handlePreferShortcutsToggle,
        handlePoiTeleport,
        handleGeoTeleport,
        accessibilityDiffVisible,
        setAccessibilityDiffVisible,
        handleAccessibilityDiffToggle,
        navmeshDebugOverlayVisible,
        setNavmeshDebugOverlayVisible,
        handleNavmeshDebugOverlayToggle,
    };
}
