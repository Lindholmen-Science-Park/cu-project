import { useState, useCallback, useRef, useEffect } from 'react';
import { sendMessage } from '../../messaging';
import type { PoiResult } from '../../types';

export type PoiRouteSource = 'search' | 'mapMarker';

export type ForceActivatePoiOpts = {
    source: PoiRouteSource;
    displayLabel?: string | null;
    /** Map marker POI spawn name (e.g. `PlayerSpawnPoint_Foyer`) for bird's-eye dashed route overlay */
    birdEyeEndSpawnPoint?: string | null;
    /**
     * True for navmesh POIs reached via `poiTeleport { primPath }` (no
     * `PlayerSpawnPoint_*`). Enables the directions panel swap to teleport
     * to the POI by resolving its prim xform on Kit (see
     * `mapMarkerDirectionsStart.startEndpointPath`).
     */
    useNavmeshPoiTeleport?: boolean;
};

/** Survives transient Kit clears of `activePoiRouteId` so the Directions UI stays open. */
export type MapMarkerDirectionsPreview =
    | {
        kind: 'poi';
        routeKey: string;
        primPath: string;
        displayLabel: string;
        /** POI's spawn point (e.g. `PlayerSpawnPoint_Foyer`) — needed when the user swaps the inputs and wants the POI to be the start. */
        spawnPoint: string | null;
        /**
         * True when the POI has no `PlayerSpawnPoint_*` (restrooms /
         * quiet zones). The directions panel still allows swap, sending
         * `startEndpointPath: primPath` so Kit teleports there by
         * resolving the prim's xform.
         */
        useNavmeshPoiTeleport?: boolean;
    }
    | {
        kind: 'seat';
        routeKey: string;
        displayLabel: string;
        /** Seat coordinates entered in the seat widget; Kit resolves the world position from these. */
        seatQuery: { section: string; row: string; seat: string; useWaypoints?: boolean };
    }
    | {
        /**
         * Ad-hoc "pin anywhere" destination from the bird-eye click-
         * anywhere flow. `worldPos` is the snapped coordinate (magnet
         * target inside the navmesh, or the nearest OSM node outside).
         * Route composition (NavMesh-only / OSM-bridged / cross-island)
         * is handled entirely by the Kit-side `RouteComposer`, so the
         * web side only needs the destination position.
         */
        kind: 'pin';
        routeKey: string;
        displayLabel: string;
        worldPos: { x: number; y: number; z: number };
    };

/**
 * POI (Point of Interest) navigation — generic state for "navigate to a POI"
 * routes used by the Restroom search list, bird's-eye map-marker POI sheet,
 * and the map-marker directions panel. The Kit-side route id is `poi_nav`.
 *
 * The restroom search widget (`RestroomWidget`) is one consumer; its UI-only
 * state (filters, results list, widget open flag) lives in this hook too as a
 * convenience because both share lifecycle (closing the widget clears the
 * route). Truly restroom-specific names are kept under the `restroom*` prefix.
 */
export function usePoiNavigation(markRouteCalculating: (routeId: string) => void) {
    const [restroomWidgetOpen, setRestroomWidgetOpen] = useState(false);
    /** When true, full-screen list/sheet is hidden so the stream tracking overlay is visible. */
    const [restroomTrackingScreen, setRestroomTrackingScreen] = useState(false);
    const [restroomResults, setRestroomResults] = useState<PoiResult[]>([]);
    /** True after `navmeshRoutesToPoisRequest` until `navmeshRoutesToPoisResult` for restrooms. */
    const [restroomPoiListLoading, setRestroomPoiListLoading] = useState(false);
    const [activePoiRouteId, setActivePoiRouteId] = useState<string | null>(null);
    const [movingToPoiId, setMovingToPoiId] = useState<string | null>(null);
    const [poiRouteSource, setPoiRouteSource] = useState<PoiRouteSource | null>(null);
    const [poiRouteDisplayLabel, setPoiRouteDisplayLabel] = useState<string | null>(null);
    const [mapMarkerDirectionsPreview, setMapMarkerDirectionsPreview] = useState<MapMarkerDirectionsPreview | null>(null);
    /**
     * Directions panel swap toggle (swap start ↔ end). Lifted to the
     * navigation hook so the bird-eye route overlay can mirror the swap on
     * the map markers (flag vs. user-location pulse) — when the user clicks
     * the swap arrow in the panel, the icons on the map should follow.
     * Resets to false whenever the preview changes (different POI/seat or
     * the panel closes).
     */
    const [mapMarkerDirectionsSwapped, setMapMarkerDirectionsSwapped] = useState<boolean>(false);
    const lastPoiPrimPathRef = useRef<string | null>(null);
    const lastPoiDisplayNameRef = useRef<string | null>(null);
    const restroomResultsRef = useRef<PoiResult[]>([]);
    const activePoiRouteIdRef = useRef<string | null>(null);
    useEffect(() => {
        restroomResultsRef.current = restroomResults;
    }, [restroomResults]);
    useEffect(() => {
        activePoiRouteIdRef.current = activePoiRouteId;
    }, [activePoiRouteId]);
    /**
     * Active route's end position (world coordinates), when the destination is
     * NOT a USD prim (e.g. swapped map-marker directions where the destination
     * is the player's previously-stored FP position). Takes precedence over
     * `lastPoiPrimPathRef` when set — `handlePoiMoveStart` /
     * `handlePoiMoveStop` will recalculate the route to this position.
     */
    const lastPoiEndPosRef = useRef<[number, number, number] | null>(null);

    const enterRestroomTrackingScreen = useCallback(() => {
        setRestroomTrackingScreen(true);
    }, []);

    const handleOpenRestroomWidget = useCallback(() => {
        setRestroomWidgetOpen(true);
        setRestroomTrackingScreen(false);
        setRestroomResults([]);
        setRestroomPoiListLoading(true);
        try { sendMessage('navmeshRoutesToPoisRequest', { poiType: 'restroom' }); } catch {}
    }, []);

    const clearPoiRouteState = useCallback(() => {
        if (movingToPoiId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToPoiId(null);
        }
        if (activePoiRouteId) {
            try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch {}
            setActivePoiRouteId(null);
            lastPoiPrimPathRef.current = null;
        }
        lastPoiDisplayNameRef.current = null;
        lastPoiEndPosRef.current = null;
        setPoiRouteSource(null);
        setPoiRouteDisplayLabel(null);
        setMapMarkerDirectionsPreview(null);
        markRouteCalculating('poi_nav');
        try {
            sendMessage('birdEyeRouteClear');
        } catch {
            /* ignore */
        }
    }, [movingToPoiId, activePoiRouteId, markRouteCalculating]);

    const dispatchPoiSearchRouteCalculate = useCallback((primPath: string) => {
        markRouteCalculating('poi_nav');
        try {
            sendMessage('navmeshRouteCalculate', {
                routeId: 'poi_nav',
                startpointPath: '/World/PlayerCharacter',
                endpointPath: primPath,
                drawPath: true,
                enablePeriodicRecalc: true,
                startUseGround: true,
                fromPoiList: true,
            });
        } catch { /* stream */ }
    }, [markRouteCalculating]);

    /** List/card tap — select POI and open the sheet only (no 3D route yet). */
    const handlePoiClick = useCallback((primPath: string, key: string) => {
        const isSame = activePoiRouteId === key;
        if (movingToPoiId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToPoiId(null);
        }
        if (activePoiRouteId) {
            try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch {}
        }
        if (isSame) {
            setActivePoiRouteId(null);
            lastPoiPrimPathRef.current = null;
            lastPoiDisplayNameRef.current = null;
            setPoiRouteSource(null);
            setPoiRouteDisplayLabel(null);
            setMapMarkerDirectionsPreview(null);
            setRestroomTrackingScreen(false);
            markRouteCalculating('poi_nav');
            return;
        }
        setRestroomTrackingScreen(false);
        setActivePoiRouteId(key);
        lastPoiPrimPathRef.current = primPath;
        lastPoiEndPosRef.current = null;
        setPoiRouteSource('search');
        setPoiRouteDisplayLabel(null);
        setMapMarkerDirectionsPreview(null);
        markRouteCalculating('poi_nav');
    }, [activePoiRouteId, movingToPoiId, markRouteCalculating]);

    /** Restroom / quiet-zone sheet "Get directions" — draw `poi_nav` and enable the stream overlay. */
    const handlePoiGetDirections = useCallback((
        primPath: string,
        key: string,
        displayName?: string | null,
    ) => {
        if (!primPath || !key) return;
        if (movingToPoiId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToPoiId(null);
        }
        setActivePoiRouteId(key);
        lastPoiPrimPathRef.current = primPath;
        lastPoiEndPosRef.current = null;
        setPoiRouteSource('search');
        const label = displayName?.trim() || null;
        if (label) {
            lastPoiDisplayNameRef.current = label;
            setPoiRouteDisplayLabel(label);
        }
        dispatchPoiSearchRouteCalculate(primPath);
    }, [movingToPoiId, dispatchPoiSearchRouteCalculate]);

    /**
     * Activate NavMesh route to a POI without going through the search list
     * (e.g. bird's-eye map marker sheet). All POI navigation shares the
     * `poi_nav` routeId.
     */
    const forceActivatePoiRoute = useCallback((
        primPath: string,
        key: string,
        opts?: ForceActivatePoiOpts,
    ) => {
        if (!primPath) return;
        if (movingToPoiId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToPoiId(null);
        }
        if (activePoiRouteId) {
            try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch {}
        }
        setActivePoiRouteId(key);
        lastPoiPrimPathRef.current = primPath;
        lastPoiEndPosRef.current = null;
        const src = opts?.source ?? 'search';
        setPoiRouteSource(src);
        setPoiRouteDisplayLabel(opts?.displayLabel ?? null);
        markRouteCalculating('poi_nav');
        if (src === 'mapMarker') {
            setMapMarkerDirectionsPreview({
                kind: 'poi',
                routeKey: key,
                primPath,
                displayLabel: String(opts?.displayLabel ?? ''),
                spawnPoint: opts?.birdEyeEndSpawnPoint?.trim() || null,
                useNavmeshPoiTeleport: opts?.useNavmeshPoiTeleport === true,
            });
        } else {
            setMapMarkerDirectionsPreview(null);
        }
        if (src !== 'mapMarker') {
            try {
                sendMessage('navmeshRouteCalculate', {
                    routeId: 'poi_nav', startpointPath: '/World/PlayerCharacter', endpointPath: primPath,
                    drawPath: true, enablePeriodicRecalc: true, startUseGround: true,
                });
            } catch {}
        }

        if (src === 'mapMarker') {
            try {
                const sp = opts?.birdEyeEndSpawnPoint?.trim();
                if (sp) {
                    sendMessage('birdEyeRouteRequest', { startPos: null, endSpawnPoint: sp });
                } else {
                    sendMessage('birdEyeRouteRequest', { startPos: null, endpointPath: primPath });
                }
            } catch {
                /* ignore */
            }
        }
    }, [activePoiRouteId, movingToPoiId, markRouteCalculating]);

    /**
     * Activate a route to an ad-hoc bird-eye pin — the click-anywhere
     * counterpart of `forceActivatePoiRoute`. Shares the `poi_nav`
     * routeId so play/pause + directions panel plumbing works identically.
     *
     * The destination is a world position; Kit's `RouteComposer`
     * computes a walkable polyline (NavMesh-only, OSM-bridged, or
     * cross-island NavMesh↔OSM↔NavMesh) and feeds the bird-eye
     * projector + the auto-mover cache.
     *
     * See `bird_eye_pin_service.py` (Kit) for the pin sheet contract
     * and `route_composer.py` for the routing cases it handles.
     */
    const forceActivatePinRoute = useCallback(
        (args: {
            id: string;
            title: string;
            worldPos: { x: number; y: number; z: number };
        }) => {
            const { id: key, title, worldPos } = args;
            if (movingToPoiId) {
                try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
                setMovingToPoiId(null);
            }
            if (activePoiRouteId) {
                try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch {}
            }
            setActivePoiRouteId(key);
            lastPoiPrimPathRef.current = null;
            lastPoiEndPosRef.current = [worldPos.x, worldPos.y, worldPos.z];
            setPoiRouteSource('mapMarker');
            setPoiRouteDisplayLabel(title);
            markRouteCalculating('poi_nav');
            setMapMarkerDirectionsPreview({
                kind: 'pin',
                routeKey: key,
                displayLabel: title,
                worldPos,
            });
            try {
                sendMessage('birdEyeRouteRequest', {
                    startPos: null,
                    endPos: [worldPos.x, worldPos.y, worldPos.z],
                });
            } catch {
                /* ignore */
            }
        },
        [activePoiRouteId, movingToPoiId, markRouteCalculating],
    );

    /** Computes path + starts auto-move in one tick (avoids stale `activePoiRouteId` in `handlePoiMoveStart`). */
    const startPoiRouteAutoMove = useCallback((primPath: string, key: string) => {
        if (!primPath) return;
        forceActivatePoiRoute(primPath, key, { source: 'search' });
        setMovingToPoiId(key);
        try {
            sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: true, routeId: 'poi_nav', endpointPath: primPath, endPos: null });
        } catch {}
    }, [forceActivatePoiRoute]);

    const handlePoiMoveStart = useCallback(() => {
        let routeKey = activePoiRouteId;
        let primPath = lastPoiPrimPathRef.current;
        const endPos = lastPoiEndPosRef.current;
        if (
            (!routeKey || (!primPath && !endPos))
            && mapMarkerDirectionsPreview
            && mapMarkerDirectionsPreview.kind === 'poi'
        ) {
            routeKey = mapMarkerDirectionsPreview.routeKey;
            primPath = mapMarkerDirectionsPreview.primPath;
            setActivePoiRouteId(routeKey);
            lastPoiPrimPathRef.current = primPath;
        }
        if (!routeKey || (!primPath && !endPos)) return;

        // Directions-panel flows (mapMarker source) live on exactly the
        // same Kit-side pipeline as seat_nav: the route engine has
        // already built the polyline via ``set_route_for_id
        // (use_composer=True)`` and cached it on a RouteInstance, the
        // auto-mover has the waypoints from the initial dispatch.
        // Play is a state flip + endpoint reassertion — we always re-
        // send ``endPos`` / ``endpointPath`` so a stale ``end_pos`` in
        // the orchestrator (e.g. the world location of a ground click
        // the user made during pause) can't masquerade as poi_nav's
        // target on the next ``_apply_state`` recompute. Mirrors the
        // seat_nav Play contract; keeps the orchestrator stateless
        // about per-route endpoints.
        if (poiRouteSource === 'mapMarker') {
            const navStatePayload: Record<string, unknown> = {
                movementMode: 'pointClick',
                autoMove: true,
                routeId: 'poi_nav',
                useComposer: true,
            };
            if (endPos) {
                navStatePayload.endPos = endPos;
                navStatePayload.endpointPath = null;
            } else if (primPath) {
                navStatePayload.endpointPath = primPath;
                navStatePayload.endPos = null;
            }
            try {
                sendMessage('navigationStateSet', navStatePayload);
            } catch { /* ignore */ }
            setMovingToPoiId(routeKey);
            return;
        }

        const navStatePayload: Record<string, unknown> = {
            movementMode: 'pointClick',
            autoMove: true,
            routeId: 'poi_nav',
        };
        if (endPos) {
            navStatePayload.endPos = endPos;
            navStatePayload.endpointPath = '';
        } else if (primPath) {
            navStatePayload.endpointPath = primPath;
            navStatePayload.endPos = null;
        }
        setMovingToPoiId(routeKey);
        try { sendMessage('navigationStateSet', navStatePayload); } catch {}
    }, [activePoiRouteId, mapMarkerDirectionsPreview, poiRouteSource]);

    const handlePoiMoveStop = useCallback(() => {
        if (!movingToPoiId) return;
        const primPath = lastPoiPrimPathRef.current;
        const endPos = lastPoiEndPosRef.current;

        // Directions-panel flows: Pause is purely a state flip.
        // ``navigationStateSet { autoMove: false }`` tells the auto-
        // mover to stop; the Kit-side RouteInstance stays alive so
        // the next Play can re-activate from its cached waypoints
        // without re-composing. The route polyline (spheres + web
        // overlay) stays visible so the user can see where they were
        // heading.
        if (poiRouteSource === 'mapMarker') {
            try {
                sendMessage('navigationStateSet', {
                    movementMode: 'pointClick',
                    autoMove: false,
                    routeId: 'poi_nav',
                });
            } catch { /* ignore */ }
            setMovingToPoiId(null);
            return;
        }

        // Pause only stops auto-move; keep the live RouteInstance and its
        // pruned polyline (same contract as quiet-zone + map-marker flows).
        try {
            sendMessage('navigationStateSet', {
                movementMode: 'pointClick',
                autoMove: false,
                routeId: 'poi_nav',
            });
        } catch { /* stream */ }
        setMovingToPoiId(null);
    }, [movingToPoiId, poiRouteSource]);

    const handleRestroomWidgetClose = useCallback(() => {
        clearPoiRouteState();
        setRestroomWidgetOpen(false);
        setRestroomTrackingScreen(false);
        setRestroomPoiListLoading(false);
    }, [clearPoiRouteState]);

    /** Hide the map-marker directions panel without stopping the active route. */
    const clearMapMarkerDirectionsPreview = useCallback(() => {
        setMapMarkerDirectionsPreview(null);
        setMapMarkerDirectionsSwapped(false);
    }, []);

    /**
     * Open the directions panel with a SEAT destination (bird-eye seat
     * navigation flow). The same panel UI is reused — `Start Navigation`
     * branches on `preview.kind === 'seat'` and dispatches a Kit
     * `seatDirectionsStart` event instead of `mapMarkerDirectionsStart`.
     */
    const openSeatDirectionsPreview = useCallback(
        (
            seatQuery: { section: string; row: string; seat: string; useWaypoints?: boolean },
            displayLabel: string,
        ) => {
            const routeKey = `seat:${seatQuery.section}-${seatQuery.row}-${seatQuery.seat}`;
            // The seat preview is independent of any active `poi_nav` route —
            // we set it directly. The user has to press Start Navigation to
            // commit; until then no auto-move pill should appear.
            setMapMarkerDirectionsPreview({
                kind: 'seat',
                routeKey,
                displayLabel,
                seatQuery,
            });
        },
        [],
    );

    /**
     * Adopt an active `poi_nav` route set up by an external orchestrator
     * (e.g. Kit's `mapMarkerDirectionsStart`). Tracking the resolved endpoint
     * here lets the play / pause buttons recalculate against the *correct*
     * destination — for the swap case the destination is a world position
     * (the player's previously-stored FP location), not the POI prim.
     */
    const adoptPoiRouteTarget = useCallback(
        (
            routeKey: string,
            target: {
                primPath?: string | null;
                endPos?: [number, number, number] | null;
                displayLabel?: string | null;
                /**
                 * Route source. Directions-panel flows (POI / seat / pin)
                 * must pass ``'mapMarker'`` so Play / Pause toggles the
                 * shared RouteInstance's auto-move flag via
                 * ``navigationStateSet`` instead of re-invoking
                 * ``navmeshRouteCalculate`` (which would recompute a
                 * pure-NavMesh path and fail for OSM-bridged or cross-
                 * island routes). Defaults to the current source
                 * (no change).
                 */
                source?: PoiRouteSource | null;
            },
        ) => {
            setActivePoiRouteId(routeKey);
            lastPoiPrimPathRef.current = target.primPath ?? null;
            lastPoiEndPosRef.current = target.endPos ?? null;
            if (target.source !== undefined && target.source !== null) {
                setPoiRouteSource(target.source);
            }
            // Allow callers to override the destination label. The pill
            // (poiRouteDisplayLabel state) and the arrival overlay
            // (lastPoiDisplayNameRef) must stay in sync — they always
            // describe the same place — so set both here. Callers should
            // never have to touch lastPoiDisplayNameRef directly when going
            // through this entry point.
            if (target.displayLabel !== undefined) {
                setPoiRouteDisplayLabel(target.displayLabel);
                lastPoiDisplayNameRef.current = target.displayLabel;
            }
        },
        [],
    );

    return {
        restroomWidgetOpen, setRestroomWidgetOpen,
        restroomTrackingScreen,
        setRestroomTrackingScreen,
        enterRestroomTrackingScreen,
        restroomResults, setRestroomResults,
        restroomPoiListLoading, setRestroomPoiListLoading,
        activePoiRouteId, setActivePoiRouteId,
        movingToPoiId, setMovingToPoiId,
        lastPoiPrimPathRef,
        lastPoiDisplayNameRef,
        restroomResultsRef,
        activePoiRouteIdRef,
        lastPoiEndPosRef,
        poiRouteSource,
        poiRouteDisplayLabel,
        mapMarkerDirectionsPreview,
        mapMarkerDirectionsSwapped,
        setMapMarkerDirectionsSwapped,
        clearMapMarkerDirectionsPreview,
        openSeatDirectionsPreview,
        adoptPoiRouteTarget,
        clearPoiRouteState,
        handleOpenRestroomWidget,
        handlePoiClick,
        handlePoiGetDirections,
        handlePoiMoveStart,
        handlePoiMoveStop,
        handleRestroomWidgetClose,
        forceActivatePoiRoute,
        forceActivatePinRoute,
        startPoiRouteAutoMove,
    };
}
