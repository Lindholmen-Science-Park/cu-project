import React, { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useControl, useEnvironment, useNavigation } from '../contexts';
import { useModalAccessibility } from '../hooks/useModalAccessibility';
import { sendMessage } from '../messaging';
import { beginViewTransition } from '../viewTransition';
import closeXUrl from '@icons/restrooms/close-x.svg';
import sheetSignpostUrl from '@icons/restrooms/sheet-signpost.svg';
import sheetWheelchairDetailUrl from '@icons/restrooms/sheet-wheelchair-detail.svg';
import './RestroomWidget.css';

/**
 * Bird's-eye map marker detail — same bottom sheet structure and styles as RestroomWidget POI sheet.
 */
const MapMarkerPoiSheet: React.FC = () => {
    const { t } = useTranslation();
    const ctrl = useControl();
    const nav = useNavigation();

    const env = useEnvironment();
    const sheet = nav.mapMarkerSheet;
    const close = nav.closeMapMarkerSheet;

    // Bird-eye cinematic tilt while the small POI sheet is open — same
    // contract as the Directions panel. Restored on close.
    const sheetVisible = !!sheet;
    useEffect(() => {
        if (!sheetVisible) return;
        if (env.currentCamera !== 'bird_eye') return;
        try { sendMessage('birdEyeFrameTarget', {}); } catch { /* ignore */ }
        return () => {
            try { sendMessage('birdEyeFrameRestore', {}); } catch { /* ignore */ }
        };
    }, [sheetVisible, env.currentCamera]);

    // Bird-eye pin marker lifetime is tied to this sheet. Kit holds the
    // solo pin marker; we clear it whenever the sheet closes WITHOUT
    // committing to directions (X button, external close, teleport path),
    // but NOT when we're transitioning into the directions panel — that
    // path fires `birdEyeRouteRequest` and the RouteComposer takes over
    // the overlay. The ref lets us skip the dismiss in that single case so
    // we don't race the composer's own marker updates.
    //
    // Same lifetime applies to the destination flag we show for navmesh
    // POIs opened from the search list (`useNavmeshPoiTeleport`) — those
    // also push a `set_pin_marker` on Kit at sheet open, so the dismiss
    // path needs to fire for them too.
    const sheetRef = useRef<HTMLDivElement>(null);
    useModalAccessibility(sheetRef, { enabled: sheetVisible });
    const transitioningToDirectionsRef = useRef(false);
    const sheetIsAdHocPin = !!sheet?.isAdHocPin;
    const sheetUsesPinMarker = sheetIsAdHocPin || !!sheet?.useNavmeshPoiTeleport;
    useEffect(() => {
        if (!sheetUsesPinMarker) return;
        return () => {
            if (transitioningToDirectionsRef.current) {
                transitioningToDirectionsRef.current = false;
                return;
            }
            try { sendMessage('birdEyePinDismiss', {}); } catch { /* ignore */ }
        };
    }, [sheetUsesPinMarker]);

    const handleTeleport = useCallback(() => {
        if (!sheet) return;
        const { spawnPoint, isAdHocPin, worldPos, isInsideNavmesh, useNavmeshPoiTeleport, primPath } = sheet;
        // Outside-navmesh pins cannot teleport — the player would land in
        // dead geometry with no navmesh to move on. Auto-move via OSM is the
        // only supported flow there (Phase 3c).
        if (isAdHocPin && !isInsideNavmesh) return;
        const navmeshPoiTeleportable = !isAdHocPin && useNavmeshPoiTeleport && !!primPath;
        if (!spawnPoint && !(isAdHocPin && worldPos) && !navmeshPoiTeleportable) return;
        // Teleport path short-circuits the directions route — the sheet
        // unmount cleanup fires `birdEyePinDismiss` automatically, which
        // drops the pin marker + OSM preview before the view transition.
        close();
        nav.clearPoiRouteState();
        ctrl.setBirdEyeRoutePoints(null);
        try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch {}
        try { sendMessage('birdEyeRouteClear', {}); } catch {}
        beginViewTransition({
            target: 'firstPerson',
            message: t('streaming.switchingFirstPerson'),
            onFadeOutComplete: () => {
                try {
                    if (isAdHocPin && worldPos) {
                        sendMessage('pinTeleport', {
                            x: worldPos.x,
                            y: worldPos.y,
                            z: worldPos.z,
                            viewType: 'firstPerson',
                        });
                    } else if (spawnPoint) {
                        sendMessage('teleportToSpawnpoint', {
                            spawnpointName: spawnPoint,
                            viewType: 'firstPerson',
                        });
                    } else if (navmeshPoiTeleportable) {
                        // Same bird-eye contract as seatTeleportFromBirdEye:
                        // Kit enters FP (LOD + navmesh) before poiTeleport runs.
                        sendMessage('poiTeleportFromBirdEye', { primPath });
                        env.setCurrentCamera('first_person');
                    }
                } catch {
                    /* ignore */
                }
            },
        });
    }, [sheet, close, nav, ctrl, env, t]);

    /** Draw route on the map and open the Directions panel (no auto-move until user starts navigation). */
    const handleGetDirections = useCallback(() => {
        if (!sheet) return;
        const { primPath, id, title, spawnPoint, isAdHocPin, worldPos } = sheet;
        if (isAdHocPin) {
            if (!worldPos) return;
            // Signal the unmount cleanup to skip `birdEyePinDismiss` —
            // the `forceActivatePinRoute` below owns the transition;
            // the `birdEyeRouteRequest` it dispatches hands the overlay
            // off to the RouteComposer which redraws everything.
            transitioningToDirectionsRef.current = true;
            close();
            nav.forceActivatePinRoute({ id, title, worldPos });
            return;
        }
        if (!primPath) return;
        // Navmesh POIs opened from the search list show a pre-route flag
        // pin via `birdEyePinShowAtPrim` (see RestroomWidget /
        // QuietZoneWidget). Skip the unmount-time `birdEyePinDismiss` so
        // it doesn't race with the `birdEyeRouteRequest` Kit is about to
        // turn into the route's destination bubble.
        const useNavmeshPoiTeleport = !!sheet.useNavmeshPoiTeleport;
        if (useNavmeshPoiTeleport) {
            transitioningToDirectionsRef.current = true;
        }
        close();
        nav.forceActivatePoiRoute(primPath, id, {
            source: 'mapMarker',
            displayLabel: title,
            birdEyeEndSpawnPoint: spawnPoint || null,
            useNavmeshPoiTeleport,
        });
    }, [sheet, close, nav]);

    if (!sheet) return null;

    const { title, spawnPoint, primPath, isAccessible, isAdHocPin, worldPos, isInsideNavmesh, useNavmeshPoiTeleport } = sheet;
    // Teleport only makes sense for "real" POIs (spawnPoint), navmesh POIs
    // with a known prim path (restrooms / quiet zones reached via
    // `poiTeleport`), or pins that landed inside the navmesh. Outside-
    // navmesh pins rely on OSM-bridged auto-move, so the button is hidden
    // in that case.
    const canTeleport = isAdHocPin
        ? !!(isInsideNavmesh && worldPos)
        : Boolean(spawnPoint) || (Boolean(useNavmeshPoiTeleport) && Boolean(primPath));
    // Directions are always offered when we have a destination — Kit's
    // RouteComposer figures out whether the route needs a NavMesh leg,
    // an OSM leg, or a bridge of both, so the web side doesn't care.
    // Navmesh POIs without a spawnpoint (`useNavmeshPoiTeleport`) ship
    // the prim path as `startEndpointPath` in the swap case.
    const canDirections = isAdHocPin
        ? !!worldPos
        : Boolean(primPath);
    const showWheelchairRow = !isAdHocPin && typeof isAccessible === 'boolean';

    return (
        <div
            className="cu-restroom-widget cu-restroom-widget--sheet-open"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cu-map-marker-sheet-title"
            // The shared `.cu-restroom-widget` rule covers the whole viewport
            // (position: fixed; inset: 0) which is correct for the full
            // restroom panel but blocks bird-eye drag-pan above the bottom
            // sheet here. Make the root inert and re-enable pointer events on
            // just the sheet below so taps on the X button still work.
            style={{ background: 'transparent', zIndex: 1200, pointerEvents: 'none' }}
        >
            {/* No backdrop — tap-outside-to-close would block bird-eye drag-pan on the area
                above the sheet. User dismisses via the visible X button in the sheet header. */}
            <div
                ref={sheetRef}
                className="cu-restroom-widget__sheet"
                role="region"
                aria-labelledby="cu-map-marker-sheet-title"
                style={{ pointerEvents: 'auto' }}
            >
                <div className="cu-restroom-widget__sheet-handle" aria-hidden />
                <div className="cu-restroom-widget__sheet-head">
                    <h2 id="cu-map-marker-sheet-title" className="cu-restroom-widget__sheet-title">
                        {title}
                    </h2>
                    <button type="button" className="cu-restroom-widget__sheet-close" onClick={close} aria-label={t('people.closePanel')}>
                        <img src={closeXUrl} alt="" className="cu-restroom-widget__sheet-close-img" width={23} height={23} />
                    </button>
                </div>
                <div className="cu-restroom-widget__sheet-actions">
                    <button
                        type="button"
                        className="cu-restroom-widget__btn cu-restroom-widget__btn--go"
                        disabled={!canDirections}
                        onClick={handleGetDirections}
                    >
                        <img src={sheetSignpostUrl} alt="" className="cu-restroom-widget__btn-lead-icon" width={20} height={20} />
                        {t('search.toiletGetDirections')}
                    </button>
                    {canTeleport ? (
                        <button type="button" className="cu-restroom-widget__btn cu-restroom-widget__btn--tele" onClick={handleTeleport}>
                            {t('search.toiletTeleportThere')}
                        </button>
                    ) : null}
                </div>
                {showWheelchairRow ? (
                    <div className="cu-restroom-widget__sheet-info">
                        <div className="cu-restroom-widget__sheet-info-row">
                            <img src={sheetWheelchairDetailUrl} alt="" className="cu-restroom-widget__sheet-info-icon" width={16} height={16} />
                            <span className="cu-restroom-widget__sheet-info-label">{t('search.toiletInfoAccessible')}</span>
                            <span className="cu-restroom-widget__sheet-info-value">
                                {isAccessible ? t('search.toiletInfoAccessibleYes') : t('search.toiletInfoAccessibleNo')}
                            </span>
                        </div>
                    </div>
                ) : null}
            </div>
        </div>
    );
};

export default MapMarkerPoiSheet;
