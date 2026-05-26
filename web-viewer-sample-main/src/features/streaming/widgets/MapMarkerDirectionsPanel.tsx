import React, { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useControl, useEnvironment, useNavigation } from '../contexts';
import { sendMessage } from '../messaging';
import { beginViewTransition, subscribeViewTransitionKitReady } from '../viewTransition';
import arrowLeftUrl from '@icons/navigation/arrow-left.svg';
import closeUrl from '@icons/navigation/close.svg';
import personWalkUrl from '@icons/navigation/person-walk.svg';
import wheelchairUrl from '@icons/navigation/wheelchair.svg';
import userLocationUrl from '@icons/map-markers/MapPinSimpleArea.svg';
import flagPennantUrl from '@icons/navigation/flag-pennant.svg';
import swapVertUrl from '@icons/navigation/swap-vert.svg';
import navigationUrl from '@icons/navigation/navigation.svg';
import { useModalAccessibility } from '../hooks/useModalAccessibility';
import RouteErrorAlert from './RouteErrorAlert';
import './MapMarkerDirectionsPanel.css';

/**
 * Map-marker POI “Get directions” — route preview on the map + Directions sheet (before Start navigation).
 */
const MapMarkerDirectionsPanel: React.FC = () => {
    const { t } = useTranslation();
    const ctrl = useControl();
    const env = useEnvironment();
    const nav = useNavigation();
    const pendingStartRef = useRef(false);
    const sheetRef = useRef<HTMLDivElement>(null);

    const preview = nav.mapMarkerDirectionsPreview;
    const visible = !!preview && !nav.movingToPoiId;
    const previewRouteId =
        preview?.kind === 'seat' ? 'seat_nav' : preview ? 'poi_nav' : null;
    const directionsRouteError =
        nav.routeErrorByRouteId['bird_eye']
        ?? (previewRouteId ? nav.routeErrorByRouteId[previewRouteId] : undefined);

    // Bird-eye cinematic tilt while the panel is shown — Kit tilts the camera
    // further down so the player marker pulls above the bottom sheet, then
    // restores on close. No-op if we're not in bird-eye view (Kit guards it).
    useEffect(() => {
        if (!visible) return;
        if (env.currentCamera !== 'bird_eye') return;
        try { sendMessage('birdEyeFrameTarget', {}); } catch { /* ignore */ }
        return () => {
            try { sendMessage('birdEyeFrameRestore', {}); } catch { /* ignore */ }
        };
    }, [visible, env.currentCamera]);

    const destinationLabel = preview?.displayLabel || nav.poiRouteDisplayLabel || t('search.findToilet');
    const travelMode: 'foot' | 'wheelchair' =
        nav.navmeshMode === 'wheelchair' ? 'wheelchair' : 'foot';
    // Mode switch is an instant pointer swap on the dual-mode NavMesh cache —
    // see `navmesh-dual-mode.mdc`. No baking gate or busy state needed.
    const setTravelMode = useCallback(
        (mode: 'foot' | 'wheelchair') => {
            const target = mode === 'wheelchair' ? 'wheelchair' : 'walking';
            if (nav.navmeshMode === target) return;
            nav.handleNavmeshModeChange(target);
        },
        [nav],
    );
    // Swap state is lifted to the navigation hook so the bird-eye route
    // overlay can mirror the swap on the map markers (flag vs. user-location
    // pulse). Reset whenever the directions session changes (closed, or
    // re-opened for a different POI/seat) so a previously swapped POI
    // session does not carry into the next destination.
    const swapped = nav.mapMarkerDirectionsSwapped;
    const setSwapped = nav.setMapMarkerDirectionsSwapped;
    const previewRouteKey = preview?.routeKey ?? null;
    useEffect(() => {
        setSwapped(false);
    }, [previewRouteKey, setSwapped]);

    const dismiss = useCallback(() => {
        // Stop both routes — the directions panel is shared between POI and
        // seat sessions, and we may have only the bird-eye SVG up at this
        // point (no committed Kit route yet) so harmless duplicate stops are
        // cheaper than tracking which one is live.
        nav.clearPoiRouteState();
        nav.clearSeatRouteSwapState();
        nav.clearRouteError('bird_eye');
        nav.clearRouteError('poi_nav');
        nav.clearRouteError('seat_nav');
        ctrl.setBirdEyeRoutePoints(null);
        try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch {}
        try { sendMessage('navmeshRouteStop', { routeId: 'seat_nav' }); } catch {}
        try { sendMessage('birdEyeRouteClear', {}); } catch {}
    }, [nav, ctrl]);

    useModalAccessibility(sheetRef, { enabled: visible });

    useEffect(() => {
        if (!visible) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') dismiss();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [visible, dismiss]);

    const onStartNavigation = useCallback(() => {
        if (!preview) return;

        const effectiveSwap = swapped;

        // Direction is read straight off the swap state of the inputs:
        //   not swapped → top "Current position" (= no teleport, enter FP at
        //                 stored previous location), bottom = destination
        //                 (POI primPath or seat coords)
        //   swapped     → top destination (teleport to it), bottom
        //                 "Current position" (navigate back to where the player was)
        const endUseStoredFp = effectiveSwap;

        // Capture stored FP NOW (before Kit invalidates it on teleport) for
        // the swap case — both POI and seat flows need it as the route's
        // resolved end position so play/pause buttons recalculate correctly.
        let resolvedEndPos: [number, number, number] | null = null;
        if (effectiveSwap) {
            const fp = env.firstPersonLocation;
            if (!fp) return;
            resolvedEndPos = [fp.x, fp.y, fp.z];
        }

        const fireKitFlow = () => {
            // Wipe any previous route artefacts before the new calculation:
            //   - `bird_eye` route would otherwise still be projected when the
            //     user returns to bird-eye view (its SVG overlay would reappear).
            //   - the previous `poi_nav` / `seat_nav` 3D curves would otherwise
            //     stay on the ground until the recalc finishes (visible flash,
            //     and they remain visible from bird-eye too since it overlooks
            //     the world).
            try { sendMessage('birdEyeRouteClear', {}); } catch { /* ignore */ }
            ctrl.setBirdEyeRoutePoints(null);
            try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch { /* ignore */ }
            try { sendMessage('navmeshRouteStop', { routeId: 'seat_nav' }); } catch { /* ignore */ }

            if (preview.kind === 'seat') {
                // Seat directions — Kit resolves the world position from
                // section/row/seat, performs `seatTeleport` if swapped, then
                // dispatches `navmeshRouteCalculate` with `seat_nav`. Kit
                // echoes back the resolved end position + seatKey via
                // `seatDirectionsResolved` so the seat overlay activates with
                // the correct seat label and play/pause can recalculate.
                try {
                    sendMessage('seatDirectionsStart', {
                        routeId: 'seat_nav',
                        routeKey: preview.routeKey,
                        seat: {
                            section: preview.seatQuery.section,
                            row: preview.seatQuery.row,
                            seat: preview.seatQuery.seat,
                            useWaypoints: preview.seatQuery.useWaypoints !== false,
                        },
                        startIsSeat: effectiveSwap,
                        endUseStoredFp,
                    });
                } catch { /* ignore */ }
                return;
            }

            if (preview.kind === 'pin') {
                // Ad-hoc pin directions — Kit's `mapMarkerDirectionsStart`
                // enters first-person, optionally teleports to `startPos`
                // for the swap case, then hands off to the `RouteComposer`
                // which produces a unified polyline (NavMesh-only, OSM
                // bridge, or cross-island NavMesh ↔ OSM ↔ NavMesh) and
                // caches it for Play / Pause.
                //   not swapped: startPos = current (no teleport), endPos = pin
                //   swapped    : startPos = pin (teleport to it), endPos = stored FP
                const pinPos = [preview.worldPos.x, preview.worldPos.y, preview.worldPos.z];
                try {
                    sendMessage('mapMarkerDirectionsStart', {
                        routeId: 'poi_nav',
                        startSpawnPoint: '',
                        endpointPath: '',
                        endUseStoredFp: effectiveSwap,
                        startPos: effectiveSwap ? pinPos : null,
                        endPos: effectiveSwap ? null : pinPos,
                    });
                } catch { /* ignore */ }
                return;
            }

            // POI directions
            //
            // Swap variants:
            //   - classic POI (Foyer): teleport via its `PlayerSpawnPoint_*`
            //     during FP-enter (`startSpawnPoint`)
            //   - navmesh POI (restroom / quiet zone): no spawnpoint —
            //     ship the prim path as `startEndpointPath` so Kit
            //     resolves the prim's xform after FP-enter and teleports
            //     there (mirrors the pin-anywhere `startPos` flow). Empty
            //     `startSpawnPoint` makes Kit FP-enter at stored FP first
            //     (cheap LOD/navmesh prep) before the override teleport.
            const useNavmeshPoiTeleport = !!preview.useNavmeshPoiTeleport;
            const startSpawnPoint = effectiveSwap && !useNavmeshPoiTeleport
                ? (preview.spawnPoint ?? '')
                : '';
            const endpointPath = effectiveSwap ? '' : preview.primPath;
            const startEndpointPath = effectiveSwap && useNavmeshPoiTeleport
                ? preview.primPath
                : '';
            try {
                sendMessage('mapMarkerDirectionsStart', {
                    routeId: 'poi_nav',
                    startSpawnPoint,
                    endpointPath,
                    endUseStoredFp,
                    startEndpointPath,
                });
            } catch { /* ignore */ }
        };

        // POI swap requires either a spawnpoint (classic Foyer flow) OR a
        // navmesh-POI prim Kit can teleport to via `startEndpointPath`
        // (restroom / quiet zone). Otherwise we have no way to teleport
        // the player to the start of the route.
        if (
            preview.kind === 'poi'
            && effectiveSwap
            && !preview.spawnPoint
            && !preview.useNavmeshPoiTeleport
        ) {
            return;
        }

        // Hide the directions panel for good — the route is drawn and the user
        // is now in first-person. We do not flip `movingToPoiId` because
        // the user starts the auto-move themselves (no auto-walk on Start).
        nav.clearMapMarkerDirectionsPreview();

        // Track the *resolved* destination so the play / pause buttons
        // recalculate against the correct point.
        //   - POI:  goes through `adoptPoiRouteTarget` (POI overlay).
        //   - Seat: pre-set `activeSeatRouteId` so the seat overlay
        //     activates immediately with the seat label
        //     (e.g. "A-6-9"). The seat position arrives from Kit via
        //     `seatDirectionsResolved` shortly after.
        if (preview.kind === 'poi') {
            // The destination label drives BOTH the in-flight navigation
            // pill and the arrival overlay — `adoptPoiRouteTarget` keeps
            // them in sync internally so we only pass it once. For the
            // swap case the destination is the player's previous position
            // (mirror the panel's "Current position" input label), not the
            // POI we started from.
            const destLabel = effectiveSwap
                ? t('search.directionsCurrentPosition')
                : (preview.displayLabel || nav.poiRouteDisplayLabel || null);
            nav.adoptPoiRouteTarget(preview.routeKey, {
                primPath: effectiveSwap ? null : preview.primPath,
                endPos: resolvedEndPos,
                displayLabel: destLabel,
                // Directions panel → Kit RouteComposer → shared
                // RouteInstance (preset). Play / Pause toggles auto-
                // move on that instance via `navigationStateSet`.
                source: 'mapMarker',
            });
            // Close the ready gate — Kit (`mapMarkerDirectionsStart`)
            // calculates the route AFTER the FP-enter, so the play FAB
            // must wait for `navmeshRouteReady` before showing.
            nav.markRouteCalculating('poi_nav');
        } else if (preview.kind === 'pin') {
            // Same contract as the POI case, but destination / start are
            // world positions instead of prim paths. Swap resolves the
            // destination to the stored FP ("Current position"); otherwise
            // it's the pin itself. Play / Pause is keyed on
            // `poiRouteSource === 'mapMarker'` (see usePoiNavigation) so
            // it toggles auto-move on the shared RouteInstance via
            // ``navigationStateSet`` regardless of route shape.
            const pinPos: [number, number, number] = [
                preview.worldPos.x,
                preview.worldPos.y,
                preview.worldPos.z,
            ];
            const destLabel = effectiveSwap
                ? t('search.directionsCurrentPosition')
                : (preview.displayLabel || null);
            nav.adoptPoiRouteTarget(preview.routeKey, {
                primPath: null,
                endPos: effectiveSwap ? resolvedEndPos : pinPos,
                displayLabel: destLabel,
                source: 'mapMarker',
            });
            nav.markRouteCalculating('poi_nav');
        } else {
            // Seat key matches the format used everywhere else
            // (`<section>-<row>-<seat>`), driving the seat overlay label.
            const seatKey = `${preview.seatQuery.section}-${preview.seatQuery.row}-${preview.seatQuery.seat}`;
            nav.setActiveSeatRouteId(seatKey);
            // For swap we already know the destination (stored FP); otherwise
            // wait for `seatDirectionsResolved` to fill it in.
            if (resolvedEndPos) {
                nav.lastSeatPositionRef.current = resolvedEndPos;
            } else {
                nav.lastSeatPositionRef.current = null;
            }
            // Swap = seat is the *start*, player position is the destination.
            // Mark the route so the seat-arrival celebration is suppressed
            // (we'll arrive at the player position, not at the seat) and
            // override the in-flight pill label to mirror the panel input
            // ("Current position") instead of the formatted seat label.
            // The paired setter keeps the ref + state in sync.
            nav.setSeatRouteSwapState({
                fromSeat: effectiveSwap,
                displayLabel: effectiveSwap ? t('search.directionsCurrentPosition') : null,
            });
            // Close the ready gate — Kit's `seatDirectionsStart` calculates
            // the route AFTER FP-enter, so the play FAB must wait for
            // `navmeshRouteReady` before showing.
            nav.markRouteCalculating('seat_nav');
        }

        if (env.currentCamera === 'bird_eye') {
            pendingStartRef.current = true;
            const unsub = subscribeViewTransitionKitReady(() => {
                unsub();
                pendingStartRef.current = false;
            });
            beginViewTransition({
                message: t('streaming.switchingFirstPerson'),
                onFadeOutComplete: () => {
                    // mapMarkerDirectionsStart / seatDirectionsStart already
                    // enter first-person on the Kit side. We only flip the
                    // LOCAL camera state so overlays update — sending a second
                    // cameraViewSwitchRequest would race with our handler.
                    fireKitFlow();
                    env.setCurrentCamera('first_person');
                },
            });
            return;
        }

        fireKitFlow();
    }, [preview, swapped, env, nav, t, ctrl]);

    // Seats can always be swapped (we always know how to teleport there); POIs
    // require a spawnpoint to teleport to. Ad-hoc pins always swap —
    // Kit's `RouteComposer` handles the reverse direction (including
    // cross-island NavMesh ↔ OSM ↔ NavMesh bridges). See
    // `bird-eye-pin-anywhere.mdc` and `route-composer.mdc`.
    const canSwap =
        preview?.kind === 'seat'
        || Boolean(
            preview?.kind === 'poi'
            && (preview.spawnPoint || preview.useNavmeshPoiTeleport),
        )
        || preview?.kind === 'pin';
    const toggleSwap = useCallback(() => {
        if (!canSwap) return;
        setSwapped((s) => !s);
    }, [canSwap]);

    if (!visible) return null;

    const startText = t('search.directionsCurrentPosition');
    const endText = destinationLabel;
    const topLabel = swapped ? endText : startText;
    const bottomLabel = swapped ? startText : endText;
    const topIcon = swapped ? flagPennantUrl : userLocationUrl;
    const bottomIcon = swapped ? userLocationUrl : flagPennantUrl;

    return (
        <div
            className="map-marker-directions"
            role="dialog"
            aria-modal="true"
            aria-labelledby="map-marker-directions-title"
        >
            <div ref={sheetRef} className="map-marker-directions__sheet">
                <div className="map-marker-directions__handle" aria-hidden />
                <div className="map-marker-directions__toolbar">
                    <button
                        type="button"
                        className="map-marker-directions__icon-btn"
                        onClick={dismiss}
                        aria-label={t('search.directionsBack')}
                    >
                        <img src={arrowLeftUrl} alt="" width={23} height={23} draggable={false} />
                    </button>
                    <h2 id="map-marker-directions-title" className="map-marker-directions__title">
                        {t('search.directionsTitle')}
                    </h2>
                    <button
                        type="button"
                        className="map-marker-directions__icon-btn"
                        onClick={dismiss}
                        aria-label={t('people.closePanel')}
                    >
                        <img src={closeUrl} alt="" width={23} height={23} draggable={false} />
                    </button>
                </div>

                <div className="map-marker-directions__card">
                    <div className="map-marker-directions__tabs">
                        <div className="map-marker-directions__tabs-travel">
                            <button
                                type="button"
                                className={`map-marker-directions__tab${travelMode === 'foot' ? ' map-marker-directions__tab--active' : ''}`}
                                onClick={() => setTravelMode('foot')}
                            >
                                <img src={personWalkUrl} alt="" width={20} height={20} draggable={false} />
                                <span>{t('search.directionsByFoot')}</span>
                            </button>
                            <button
                                type="button"
                                className={`map-marker-directions__tab${travelMode === 'wheelchair' ? ' map-marker-directions__tab--active' : ''}`}
                                onClick={() => setTravelMode('wheelchair')}
                            >
                                <img src={wheelchairUrl} alt="" width={20} height={20} draggable={false} />
                                <span>{t('search.directionsWheelchair')}</span>
                            </button>
                        </div>
                    </div>

                    <div className="map-marker-directions__route-block">
                        <div className="map-marker-directions__route-col" aria-hidden>
                            <img
                                className="map-marker-directions__route-icon"
                                src={topIcon}
                                alt=""
                                width={22}
                                height={22}
                                draggable={false}
                            />
                            <div className="map-marker-directions__route-dots">
                                <span className="map-marker-directions__route-dot" />
                                <span className="map-marker-directions__route-dot" />
                                <span className="map-marker-directions__route-dot" />
                                <span className="map-marker-directions__route-dot" />
                            </div>
                            <img
                                className="map-marker-directions__route-icon"
                                src={bottomIcon}
                                alt=""
                                width={22}
                                height={22}
                                draggable={false}
                            />
                        </div>
                        <div className="map-marker-directions__route-inputs">
                            <div className="map-marker-directions__route-inputs-inner">
                                <div className="map-marker-directions__field">
                                    <span className="map-marker-directions__field-text">{topLabel}</span>
                                </div>
                                <div className="map-marker-directions__field">
                                    <span className="map-marker-directions__field-text">{bottomLabel}</span>
                                </div>
                            </div>
                        </div>
                        <button
                            type="button"
                            className="map-marker-directions__swap"
                            onClick={toggleSwap}
                            aria-label={t('search.directionsSwapStartEnd')}
                            disabled={!canSwap}
                        >
                            <img
                                src={swapVertUrl}
                                alt=""
                                className="map-marker-directions__swap-icon"
                                draggable={false}
                            />
                        </button>
                    </div>

                    {directionsRouteError ? (
                        <RouteErrorAlert id="map-marker-directions-route-error" error={directionsRouteError} />
                    ) : null}

                    <button type="button" className="map-marker-directions__start-btn" onClick={onStartNavigation}>
                        <img src={navigationUrl} alt="" width={22} height={22} draggable={false} />
                        <span className="map-marker-directions__start-btn-label">{t('search.directionsStartNavigation')}</span>
                    </button>
                </div>
            </div>
        </div>
    );
};

export default MapMarkerDirectionsPanel;
