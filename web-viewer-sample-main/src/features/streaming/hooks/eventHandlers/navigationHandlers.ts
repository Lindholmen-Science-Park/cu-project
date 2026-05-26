import i18n from '../../../../i18n';
import { sendMessage } from '../../messaging';
import { buildNavRouteErrorAnnouncement } from '../../utils/navRouteErrorMessages';
import type { NavigationGuideAction, NavigationGuideStep, PoiResult } from '../../types';
import type { EventStateSetters } from './types';
import {
    showTriggerNotification,
    scheduleSeatArrivalCelebration,
    schedulePoiArrival,
    revertWheelchairMode,
    resolveRestroomArrivalLabel,
    resolveQuietZoneArrivalLabel,
} from './helpers';

function parseNavigationGuideSteps(raw: unknown): NavigationGuideStep[] | undefined {
    if (!Array.isArray(raw)) return undefined;
    const out: NavigationGuideStep[] = [];
    for (const s of raw) {
        if (!s || typeof s !== 'object') continue;
        const action = String((s as { action?: string }).action || '') as NavigationGuideAction;
        if (!action) continue;
        const distanceMeters = (s as { distanceMeters?: unknown }).distanceMeters;
        out.push({
            action,
            distanceMeters: distanceMeters != null && distanceMeters !== '' ? Number(distanceMeters) : undefined,
        });
    }
    return out.length ? out : undefined;
}

/** Sync Kit PointClickAutoMover off — same payload as handleAutoMoveStatus (navmesh arrival can fire first). */
function syncNavigationAutoMoveOff(): void {
    try {
        sendMessage('navigationStateSet', {
            movementMode: 'pointClick',
            autoMove: false,
            routeId: 'player',
            endPos: null,
            endpointPath: null,
        });
    } catch {}
}

export function handleNavigationEvents(event: any, s: EventStateSetters): void {
    const et = event.event_type;
    if (et === 'accessibilityDiffStatus' || et === 'navmeshDebugStatus') {
        const p = event.payload || {};
        if (p.visible == null) return;
        const vis = !!p.visible;
        try {
            if (et === 'accessibilityDiffStatus') {
                s.setAccessibilityDiffVisible?.(vis);
            } else {
                s.setNavmeshDebugOverlayVisible?.(vis);
            }
        } catch { /* noop */ }
        return;
    }

    if (event.event_type === 'navmeshRouteStatus') {
        const rid = (event.payload && (event.payload.routeId || event.payload.route_id)) || 'default';
        if (rid === 'default') {
            s.setNavmeshActive(event.payload.active === true);
            console.log(`NavMesh navigation (default route) ${event.payload.active ? 'activated' : 'deactivated'}`);
        }
        if (event.payload.active === false) {
            s.setActiveSpotRouteId((prev) => (prev === rid ? null : prev));
            s.setRouteMeasureByRouteId((prev) => { const next = { ...prev }; delete next[rid]; return next; });
            if (rid === 'exit_nav') {
                s.setActiveExitRouteId(null);
                s.setMovingToExitId(null);
                s.lastExitPrimPathRef.current = null;
            }
            // poi_nav / quiet_zone_nav: do NOT clear state here.
            // Kit sends navmeshRouteStatus(active:false) when a route is stopped,
            // but handlePoiClick re-uses the same routeId ('poi_nav') when
            // switching cards — the stop event for the OLD route arrives after
            // the new activePoiRouteId is already set, clobbering it.
            // All cleanup is handled by explicit actions (widget close, card deselect,
            // arrival handlers, error handler).
        }
        return;
    }

    if (event.event_type === 'osmRouteResult') {
        const p = event.payload || {};
        if (p.success) {
            s.setOsmRouteInfo({
                distanceMeters: Number(p.distanceMeters) || 0,
                estimatedTimeSeconds: Number(p.estimatedTimeSeconds) || 0,
                poiId: String(p.poiId || ''),
            });
        }
        return;
    }

    if (event.event_type === 'navmeshRouteMeasure') {
        const p = event.payload || {};
        const rid = String(p.routeId || 'default');
        s.setRouteMeasureByRouteId((prev) => {
            const existing = prev[rid];
            return {
                ...prev,
                [rid]: {
                    success: p.success === true,
                    error: p.error,
                    distanceMetersBase: Number(p.distanceMetersBase) || 0,
                    estimatedTimeSecondsBase: Number(p.estimatedTimeSecondsBase) || 0,
                    distanceMetersActual: p.distanceMetersActual != null ? Number(p.distanceMetersActual) : existing?.distanceMetersActual,
                    estimatedTimeSecondsActual: p.estimatedTimeSecondsActual != null ? Number(p.estimatedTimeSecondsActual) : existing?.estimatedTimeSecondsActual,
                    distanceMetersCrowdDelta: p.distanceMetersCrowdDelta != null ? Number(p.distanceMetersCrowdDelta) : existing?.distanceMetersCrowdDelta,
                    estimatedTimeSecondsCrowdDelta: p.estimatedTimeSecondsCrowdDelta != null ? Number(p.estimatedTimeSecondsCrowdDelta) : existing?.estimatedTimeSecondsCrowdDelta,
                    distanceMetersSoundDelta: p.distanceMetersSoundDelta != null ? Number(p.distanceMetersSoundDelta) : existing?.distanceMetersSoundDelta,
                    estimatedTimeSecondsSoundDelta: p.estimatedTimeSecondsSoundDelta != null ? Number(p.estimatedTimeSecondsSoundDelta) : existing?.estimatedTimeSecondsSoundDelta,
                    navigationDestinationKind: existing?.navigationDestinationKind,
                    navigationSteps: existing?.navigationSteps,
                    navigationTotalMeters: existing?.navigationTotalMeters,
                    navigationNextMeters:
                        p.navigationNextMeters != null && p.navigationNextMeters !== ''
                            ? Number(p.navigationNextMeters)
                            : existing?.navigationNextMeters,
                    navigationNextAction:
                        p.navigationNextAction != null && p.navigationNextAction !== ''
                            ? String(p.navigationNextAction)
                            : existing?.navigationNextAction,
                },
            };
        });
        return;
    }

    if (event.event_type === 'navmeshRouteGuide') {
        const p = event.payload || {};
        const rid = String(p.routeId || '');
        if (!rid) return;
        s.setRouteMeasureByRouteId((prev) => {
            const existing = prev[rid];
            const steps = parseNavigationGuideSteps(p.steps);
            const destRaw = p.destinationKind != null ? String(p.destinationKind) : existing?.navigationDestinationKind;
            const dest =
                destRaw === 'seat' || destRaw === 'exit' || destRaw === 'restroom' || destRaw === 'quiet_zone' || destRaw === 'unknown'
                    ? destRaw
                    : existing?.navigationDestinationKind;
            return {
                ...prev,
                [rid]: {
                    success: p.success !== false,
                    error: p.error ?? existing?.error,
                    distanceMetersBase: existing?.distanceMetersBase ?? 0,
                    estimatedTimeSecondsBase: existing?.estimatedTimeSecondsBase ?? 0,
                    distanceMetersActual: existing?.distanceMetersActual,
                    estimatedTimeSecondsActual: existing?.estimatedTimeSecondsActual,
                    distanceMetersCrowdDelta: existing?.distanceMetersCrowdDelta,
                    estimatedTimeSecondsCrowdDelta: existing?.estimatedTimeSecondsCrowdDelta,
                    distanceMetersSoundDelta: existing?.distanceMetersSoundDelta,
                    estimatedTimeSecondsSoundDelta: existing?.estimatedTimeSecondsSoundDelta,
                    navigationDestinationKind: dest,
                    navigationSteps: steps ?? existing?.navigationSteps,
                    navigationTotalMeters:
                        p.totalDistanceMeters != null && p.totalDistanceMeters !== ''
                            ? Number(p.totalDistanceMeters)
                            : existing?.navigationTotalMeters,
                    navigationNextMeters: existing?.navigationNextMeters,
                    navigationNextAction: existing?.navigationNextAction,
                },
            };
        });
        return;
    }

    if (event.event_type === 'navmeshRoutesToExitsResult') {
        const p = event.payload || {};
        s.setExitsResults(Array.isArray(p.results) ? p.results : []);
        return;
    }

    if (event.event_type === 'navmeshRoutesToPoisResult') {
        const p = event.payload || {};
        const poiType = String(p.poiType || '');
        const results = Array.isArray(p.results) ? p.results : [];
        const mapResult = (r: any): PoiResult => ({
            poiRef: r.exitRef ?? r.poiRef ?? '',
            poiId: r.exitId ?? r.poiId ?? '',
            success: r.success === true,
            error: r.error,
            distanceMetersBase: Number(r.distanceMetersBase) || 0,
            estimatedTimeSecondsBase: Number(r.estimatedTimeSecondsBase) || 0,
            distanceMetersActual: Number(r.distanceMetersActual) || 0,
            estimatedTimeSecondsActual: Number(r.estimatedTimeSecondsActual) || 0,
            metadata: r.metadata ?? undefined,
        });
        if (poiType === 'restroom') {
            s.setRestroomResults(results.map(mapResult));
            if (p.partial !== true) {
                s.setRestroomPoiListLoading(false);
            }
        }
        if (poiType === 'quiet_zone') {
            s.setQuietZoneResults(results.map(mapResult));
            if (p.partial !== true) {
                s.setQuietZonePoiListLoading(false);
            }
        }
        return;
    }

    if (event.event_type === 'navmeshRouteReady') {
        // Kit relays this from `navmeshRouteWaypoints` (success) for the
        // user-facing named routes (seat_nav, poi_nav, quiet_zone_nav,
        // exit_nav). It's the signal that the route is actually drawable —
        // `AppUIContext` gates the navigation overlays / play FAB on this
        // flag so they don't activate optimistically before Kit confirms.
        const routeId = String(event.payload?.routeId || '');
        if (routeId) s.markRouteReady(routeId, true);
        return;
    }

    if (event.event_type === 'navmeshRouteError') {
        const routeId = event.payload?.routeId;
        const error = event.payload?.error || 'Route calculation failed';
        const routeIdStr = routeId ? String(routeId) : '';
        if (routeIdStr) s.markRouteReady(routeIdStr, false);
        const announcement = routeIdStr
            ? buildNavRouteErrorAnnouncement(routeIdStr, String(error), i18n.t)
            : null;
        if (announcement && routeIdStr) {
            s.setRouteError(routeIdStr, announcement);
        }
        if (routeId === 'seat_nav') {
            try { sendMessage('seatNavigate', { action: 'stop' }); } catch {}
            try { sendMessage('navmeshRouteStop', { routeId: 'seat_nav' }); } catch {}
            s.setActiveSeatRouteId((prev) => {
                if (!prev || prev.includes(':')) return prev;
                const errorId = `unreachable:${prev}`;
                setTimeout(() => s.setActiveSeatRouteId((cur) => cur === errorId ? null : cur), 5000);
                return errorId;
            });
            s.setMovingToSeatId(null);
            s.setRouteMeasureByRouteId((prev) => { const next = { ...prev }; delete next['seat_nav']; return next; });
            s.lastSeatPositionRef.current = null;
        }
        if (routeId === 'exit_nav') { s.setActiveExitRouteId(null); s.lastExitPrimPathRef.current = null; }
        if (routeId === 'poi_nav') {
            s.setActivePoiRouteId(null);
            s.lastPoiPrimPathRef.current = null;
            s.lastPoiDisplayNameRef.current = null;
            s.setRestroomTrackingScreen(false);
        }
        if (routeId === 'quiet_zone_nav') {
            s.setActiveQuietZoneRouteId(null);
            s.lastQuietZonePrimPathRef.current = null;
            s.lastQuietZoneDisplayNameRef.current = null;
            s.setQuietZoneTrackingScreen(false);
        }
        console.warn(`[navmeshRouteError] Route "${routeId}" failed: ${error}`);
        return;
    }

    if (event.event_type === 'seatDirectionsResolved') {
        // Bird-eye seat directions: Kit echoes the resolved end position so
        // the play / pause buttons recalculate against the correct point.
        // `kind === 'seat'` routes the response into seat state so the seat
        // overlay (with the seat label, e.g. "A-6-9") activates instead of
        // the POI overlay (which would show "Find toilets" by default).
        const p = event.payload || {};
        const kind = String(p.kind || '');
        const routeKey = String(p.routeKey || '');
        const endPos = Array.isArray(p.endPos) && p.endPos.length === 3
            ? ([Number(p.endPos[0]), Number(p.endPos[1]), Number(p.endPos[2])] as [number, number, number])
            : null;
        if (!endPos) return;
        if (kind === 'seat') {
            const seatKey = String(p.seatKey || '').trim();
            if (seatKey) {
                s.setActiveSeatRouteId(seatKey);
                s.lastSeatPositionRef.current = endPos;
            }
        } else if (routeKey) {
            s.setActivePoiRouteId(routeKey);
            s.lastPoiPrimPathRef.current = null;
            s.lastPoiEndPosRef.current = endPos;
        }
        return;
    }

    if (event.event_type === 'navmeshModeStatus') {
        const p = event.payload || {};
        const status = String(p.status || '');
        const mode = String(p.mode || '');
        if (status === 'baking') {
            s.setNavmeshBaking(true);
        } else {
            s.setNavmeshBaking(false);
            if (status === 'ready' && (mode === 'wheelchair' || mode === 'walking')) {
                s.setNavmeshMode(mode);
            }
        }
        return;
    }

    if (event.event_type === 'autoMoveStatus') {
        handleAutoMoveStatus(event, s);
        return;
    }

    if (event.event_type === 'navmeshRouteArrival') {
        handleRouteArrival(event, s);
        return;
    }

    if (event.event_type === 'osmRouteOverlayAttached') {
        // Single source of truth for the OSM route overlay FAB's
        // visibility — Kit decides whether the player is currently
        // bound to a route (after a successful click dispatch) or
        // jumped off (after any NavMesh point-click). Idempotent on
        // the Kit side, so no need to coalesce here.
        const attached = !!(event.payload && event.payload.attached);
        try { s.setOsmRouteOverlayAttached(attached); } catch {}
        return;
    }
}

function handleAutoMoveStatus(event: any, s: EventStateSetters): void {
    const p = event.payload || {};
    const rid = String(p.routeId || '');
    const active = !!p.active;
    const reason = String(p.reason || 'cancelled');
    console.log(`Auto-move status: routeId=${rid}, active=${p.active}, reason=${reason}`);

    // Mirror the player route's active flag into the OSM route overlay FAB
    // state so the Play/Pause icon flips automatically when Kit
    // arrives at a junction (auto-stop) or the user steps off the
    // route overlay onto NavMesh (interrupted/arrived).
    if (rid === 'player') {
        try { s.setPlayerAutoMoveActive(active); } catch {}
    }

    // Spot auto-move
    s.setMovingToSpotId((prev) => {
        if (!prev || prev !== rid) return prev;
        if (reason === 'arrived') {
            try { sendMessage('navmeshRouteStop', { routeId: rid }); } catch {}
            s.setActiveSpotRouteId((cur) => (cur === rid ? null : cur));
        } else {
            const spot = s.navigationSpotsRef.current.find((sp) => sp.id === rid);
            if (spot) {
                try {
                    sendMessage('navmeshRouteCalculate', {
                        routeId: rid,
                        startpointPath: '/World/PlayerCharacter',
                        endpointPath: spot.primPath,
                        drawPath: true,
                        enablePeriodicRecalc: true,
                        startUseGround: true,
                    });
                } catch {}
            }
        }
        if (reason !== 'interrupted') {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
        }
        return null;
    });

    // Seat auto-move
    //
    // Read + clear `seatRouteFromSeatRef` OUTSIDE the state updater. React
    // (Strict Mode) may double-invoke functional updaters; if we mutated the
    // ref inside, the second pass would see `false` and fire the celebration
    // for the swap case. By capturing the value once into `fromSeat` and
    // closing over it, both invocations make the same decision. The remaining
    // side-effects inside the updater (sendMessage / scheduleSeatArrivalCelebration)
    // are idempotent — running them twice in dev produces identical visible
    // behaviour.
    if (rid === 'seat_nav') {
        const fromSeat = s.seatRouteFromSeatRef.current;
        if (reason === 'arrived') {
            s.clearSeatRouteSwapState();
        }
        s.setMovingToSeatId((prev) => {
            if (!prev) return prev;
            if (reason === 'arrived') {
                try { sendMessage('seatNavigate', { seatNumber: prev, action: 'stop' }); } catch {}
                try { sendMessage('navmeshRouteStop', { routeId: 'player' }); } catch {}
                s.setActiveSeatRouteId(null);
                s.lastSeatPositionRef.current = null;
                revertWheelchairMode(s);
                if (!fromSeat) {
                    s.setSeatArrivalLabel(prev);
                    if (s.appModeRef.current === 'cu') {
                        scheduleSeatArrivalCelebration(s);
                    } else {
                        showTriggerNotification(s, 'You have arrived at seat', 'navigation_arrival');
                    }
                } else {
                    // Swap arrival: destination was the player's previous
                    // location, not a seat. Reuse the POI-style arrival
                    // overlay (same look as Foyer→player) with the same
                    // "Current position" label the directions panel uses
                    // for the player input.
                    const prevLabel = i18n.t('search.directionsCurrentPosition');
                    if (s.appModeRef.current === 'cu') {
                        schedulePoiArrival(s, prevLabel);
                    } else {
                        showTriggerNotification(s, `Arrived at ${prevLabel}`, 'navigation_arrival');
                    }
                }
            } else {
                const pos = s.lastSeatPositionRef.current;
                if (pos && pos.length >= 3) {
                    try { sendMessage('seatNavigate', { seatNumber: prev }); } catch {}
                }
            }
            if (reason !== 'interrupted') {
                try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
            }
            return null;
        });
    }

    // Exit auto-move
    if (rid === 'exit_nav') {
        s.setMovingToExitId((prev) => {
            if (!prev) return prev;
            if (reason === 'arrived') {
                try { sendMessage('navmeshRouteStop', { routeId: 'exit_nav' }); } catch {}
                s.setActiveExitRouteId(null);
                s.lastExitPrimPathRef.current = null;
            } else {
                const primPath = s.lastExitPrimPathRef.current;
                if (primPath) {
                    try {
                        sendMessage('navmeshRouteCalculate', {
                            routeId: 'exit_nav',
                            startpointPath: '/World/PlayerCharacter',
                            endpointPath: primPath,
                            drawPath: true,
                            enablePeriodicRecalc: true,
                            startUseGround: true,
                        });
                    } catch {}
                }
            }
            if (reason !== 'interrupted') {
                try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
            }
            return null;
        });
    }

    // POI auto-move (restroom search, map-marker POI sheet, map-marker directions)
    if (rid === 'poi_nav') {
        const arrivedPoiName =
            reason === 'arrived'
                ? resolveRestroomArrivalLabel({
                    displayNameRef: s.lastPoiDisplayNameRef,
                    primPathRef: s.lastPoiPrimPathRef,
                    routeIdRef: s.activePoiRouteIdRef,
                    resultsRef: s.restroomResultsRef,
                })
                : null;
        if (reason === 'arrived') {
            if (s.appModeRef.current === 'cu') {
                schedulePoiArrival(s, arrivedPoiName!);
            } else {
                showTriggerNotification(s, `Arrived at ${arrivedPoiName}`, 'navigation_arrival');
            }
        }
        s.setMovingToPoiId((prev) => {
            if (!prev) return prev;
            if (reason === 'arrived') {
                try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch {}
                s.setActivePoiRouteId(null);
                s.setRestroomWidgetOpen(false);
            } else {
                const primPath = s.lastPoiPrimPathRef.current;
                if (primPath) {
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
                    } catch {}
                }
            }
            if (reason !== 'interrupted') {
                try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
            }
            return null;
        });
    }

    // Quiet zone auto-move
    if (rid === 'quiet_zone_nav') {
        const arrivedQuietZoneName =
            reason === 'arrived'
                ? resolveQuietZoneArrivalLabel({
                    displayNameRef: s.lastQuietZoneDisplayNameRef,
                    primPathRef: s.lastQuietZonePrimPathRef,
                    routeIdRef: s.activeQuietZoneRouteIdRef,
                    resultsRef: s.quietZoneResultsRef,
                })
                : null;
        if (reason === 'arrived') {
            if (s.appModeRef.current === 'cu') {
                schedulePoiArrival(s, arrivedQuietZoneName!);
            } else {
                showTriggerNotification(s, `Arrived at ${arrivedQuietZoneName}`, 'navigation_arrival');
            }
        }
        s.setMovingToQuietZoneId((prev) => {
            if (!prev) return prev;
            if (reason === 'arrived') {
                try { sendMessage('navmeshRouteStop', { routeId: 'quiet_zone_nav' }); } catch {}
                s.setActiveQuietZoneRouteId(null);
                s.setQuietZoneWidgetOpen(false);
            } else {
                const primPath = s.lastQuietZonePrimPathRef.current;
                if (primPath) {
                    try {
                        sendMessage('navmeshRouteCalculate', {
                            routeId: 'quiet_zone_nav',
                            startpointPath: '/World/PlayerCharacter',
                            endpointPath: primPath,
                            drawPath: true,
                            enablePeriodicRecalc: true,
                            startUseGround: true,
                            fromPoiList: true,
                        });
                    } catch {}
                }
            }
            if (reason !== 'interrupted') {
                try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
            }
            return null;
        });
    }

    // Ground point-and-click (Kit routeId "player"): clear path measure and sync auto-move when walk finishes.
    if (rid === 'player' && reason === 'arrived') {
        try {
            sendMessage('navmeshRouteStop', { routeId: 'player' });
        } catch {
            /* stream */
        }
        s.setRouteMeasureByRouteId((prev) => {
            const next = { ...prev };
            delete next.player;
            delete next.default;
            return next;
        });
        syncNavigationAutoMoveOff();
    }
}

function handleRouteArrival(event: any, s: EventStateSetters): void {
    const p = event.payload || {};
    const rid = String(p.routeId || '');
    // Reserved: Kit does not send proximityOnly today; kept for backward compatibility.
    if (p.proximityOnly === true) {
        return;
    }
    console.log(`[navmeshRouteArrival] Route "${rid}" — player reached destination`);

    // The ready gate is bound to the active route lifecycle — clear it on
    // arrival so the next "Get directions" press starts in the pending
    // (unready) state and the play FAB stays hidden until Kit confirms.
    if (rid) s.markRouteReady(rid, false);

    if (rid === 'seat_nav') {
        // Read + clear the fromSeat flag OUTSIDE the updater (see
        // handleAutoMoveStatus above for the Strict Mode rationale). Side
        // effects inside the updater stay idempotent.
        const fromSeat = s.seatRouteFromSeatRef.current;
        s.clearSeatRouteSwapState();
        s.setActiveSeatRouteId((prev) => {
            if (!prev || prev.includes(':')) return prev;
            try {
                sendMessage('seatNavigate', { seatNumber: prev, action: 'stop' });
            } catch {
                /* stream */
            }
            try {
                sendMessage('navmeshRouteStop', { routeId: 'player' });
            } catch {
                /* stream */
            }
            revertWheelchairMode(s);
            if (!fromSeat) {
                s.setSeatArrivalLabel(prev);
                if (s.appModeRef.current === 'cu') {
                    scheduleSeatArrivalCelebration(
                        s,
                        p.manualNearDestination === true ? { skipFaceTowardCenter: true } : undefined,
                    );
                } else {
                    showTriggerNotification(s, 'You have arrived at seat', 'navigation_arrival');
                }
            } else {
                // Swap arrival at the player's previous location — same
                // POI-style overlay + "Current position" label as
                // handleAutoMoveStatus (mirrors the directions-panel input).
                const prevLabel = i18n.t('search.directionsCurrentPosition');
                if (s.appModeRef.current === 'cu') {
                    schedulePoiArrival(s, prevLabel);
                } else {
                    showTriggerNotification(s, `Arrived at ${prevLabel}`, 'navigation_arrival');
                }
            }
            return null;
        });
        s.setMovingToSeatId(null);
        s.lastSeatPositionRef.current = null;
        s.setRouteMeasureByRouteId((prev) => {
            const next = { ...prev };
            delete next.seat_nav;
            return next;
        });
        syncNavigationAutoMoveOff();
    }

    if (rid === 'exit_nav') {
        s.setActiveExitRouteId(null);
        s.setMovingToExitId(null);
        s.lastExitPrimPathRef.current = null;
        s.setRouteMeasureByRouteId((prev) => { const next = { ...prev }; delete next['exit_nav']; return next; });
        syncNavigationAutoMoveOff();
    }

    if (rid === 'poi_nav') {
        const displayName = resolveRestroomArrivalLabel({
            displayNameRef: s.lastPoiDisplayNameRef,
            primPathRef: s.lastPoiPrimPathRef,
            routeIdRef: s.activePoiRouteIdRef,
            resultsRef: s.restroomResultsRef,
        });
        s.lastPoiDisplayNameRef.current = null;
        s.lastPoiPrimPathRef.current = null;
        s.setActivePoiRouteId(null);
        s.setMovingToPoiId(null);
        s.setRestroomWidgetOpen(false);
        if (s.appModeRef.current === 'cu') {
            schedulePoiArrival(s, displayName);
        } else {
            showTriggerNotification(s, `Arrived at ${displayName}`, 'navigation_arrival');
        }
        s.setRouteMeasureByRouteId((prev) => { const next = { ...prev }; delete next['poi_nav']; return next; });
        syncNavigationAutoMoveOff();
    }

    if (rid === 'quiet_zone_nav') {
        const displayName = resolveQuietZoneArrivalLabel({
            displayNameRef: s.lastQuietZoneDisplayNameRef,
            primPathRef: s.lastQuietZonePrimPathRef,
            routeIdRef: s.activeQuietZoneRouteIdRef,
            resultsRef: s.quietZoneResultsRef,
        });
        s.lastQuietZoneDisplayNameRef.current = null;
        s.lastQuietZonePrimPathRef.current = null;
        s.setActiveQuietZoneRouteId(null);
        s.setMovingToQuietZoneId(null);
        s.setQuietZoneWidgetOpen(false);
        if (s.appModeRef.current === 'cu') {
            schedulePoiArrival(s, displayName);
        } else {
            showTriggerNotification(s, `Arrived at ${displayName}`, 'navigation_arrival');
        }
        s.setRouteMeasureByRouteId((prev) => { const next = { ...prev }; delete next['quiet_zone_nav']; return next; });
        syncNavigationAutoMoveOff();
    }
}
