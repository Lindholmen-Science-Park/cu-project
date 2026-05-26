import i18n from '../../../../i18n';
import { sendMessage } from '../../messaging';
import type { EventStateSetters } from './types';
import {
    showTriggerNotification,
    scheduleSeatArrivalCelebration,
    schedulePoiArrival,
    revertWheelchairMode,
    clearPoiNavigationAfterTeleport,
} from './helpers';

function resolvePoiArrivalLabel(payload: Record<string, unknown> | undefined): string {
    const primPath = String(payload?.primPath || '');
    const i18nKey = String(payload?.arrivalLabelI18nKey || payload?.arrivalLabelI18n || '').trim();
    if (i18nKey && i18n.exists(i18nKey)) {
        return i18n.t(i18nKey);
    }
    const arrivalLabel = String(payload?.arrivalLabel || '').trim();
    if (arrivalLabel) return arrivalLabel;
    return primPath ? primPath.replace(/^.*\//, '') : 'location';
}
import { resolveSeatTeleportFromBirdEyeCheck } from '../../widgets/seat-navigate/seatBirdEyeTeleportRpc';

export function handleSeatEvents(event: any, s: EventStateSetters): void {
    if (event.event_type === 'seatNavigateResult') {
        const seatNum = event.payload?.seatNumber;
        if (event.payload?.success === false) {
            const errorType = event.payload?.error === 'not_available' ? 'not_available' : 'not_found';
            s.setActiveSeatRouteId(`${errorType}:${seatNum}`);
            s.lastSeatPositionRef.current = null;
            setTimeout(() => s.setActiveSeatRouteId((prev) => prev === `${errorType}:${seatNum}` ? null : prev), 3000);
        } else if (event.payload?.success && Array.isArray(event.payload?.position)) {
            s.lastSeatPositionRef.current = event.payload.position;
        }
        return;
    }

    if (event.event_type === 'seatTeleportFromBirdEyeCheckResult') {
        const { requestId, ok, error, seatNumber } = event.payload || {};
        if (!ok) {
            const errorType = error === 'not_available' ? 'not_available' : 'not_found';
            const id = String(seatNumber || '');
            s.setActiveSeatRouteId(`${errorType}:${id}`);
            setTimeout(
                () => s.setActiveSeatRouteId((prev) => (prev === `${errorType}:${id}` ? null : prev)),
                3000,
            );
        }
        resolveSeatTeleportFromBirdEyeCheck(String(requestId || ''), {
            ok: !!ok,
            error: error ? String(error) : undefined,
            seatNumber: seatNumber ? String(seatNumber) : undefined,
        });
        return;
    }

    if (event.event_type === 'seatTeleportResult') {
        const seatNum = event.payload?.seatNumber;
        if (event.payload?.success) {
            // Bird-eye seat-directions swap (`seatRouteFromSeatRef`) hops to
            // the seat as a *stepping stone* on the way to the player's last
            // position — celebrating arrival at the seat would be misleading.
            // The seat overlay state is also kept intact so the route the
            // user is about to navigate stays addressable; `seatDirectionsResolved`
            // re-fills `lastSeatPositionRef` with the actual destination right
            // after this event.
            if (s.seatRouteFromSeatRef.current) {
                return;
            }
            s.setSeatArrivalLabel(String(seatNum || ''));
            s.setActiveSeatRouteId(null);
            s.setMovingToSeatId(null);
            s.lastSeatPositionRef.current = null;
            revertWheelchairMode(s);
            if (s.appModeRef.current === 'cu') {
                scheduleSeatArrivalCelebration(s, { skipFaceTowardCenter: true });
            } else {
                showTriggerNotification(s, `Teleported to seat ${seatNum}`, 'navigation_arrival');
            }
        } else if (event.payload?.success === false) {
            const errorType = event.payload?.error === 'not_available' ? 'not_available' : 'not_found';
            s.setActiveSeatRouteId(`${errorType}:${seatNum}`);
            setTimeout(() => s.setActiveSeatRouteId((prev) => prev === `${errorType}:${seatNum}` ? null : prev), 3000);
        }
        return;
    }

    if (event.event_type === 'poiTeleportResult') {
        if (event.payload?.success) {
            clearPoiNavigationAfterTeleport(s);
            const label = resolvePoiArrivalLabel(event.payload);
            if (s.appModeRef.current === 'cu') {
                schedulePoiArrival(s, label);
            } else {
                showTriggerNotification(s, `Teleported to ${label}`, 'navigation_arrival');
            }
        }
        return;
    }

    if (event.event_type === 'geoTeleportResult') {
        const p = event.payload;
        console.log('[geoTeleportResult] Kit spawn outcome', {
            success: p?.success,
            latitude: p?.latitude,
            longitude: p?.longitude,
            height: p?.height,
            positionSceneCm: p?.position,
            error: p?.success === false ? p?.error : undefined,
        });
        if (p?.success) {
            if (s.appModeRef.current === 'cu') {
                schedulePoiArrival(s, 'map location');
            } else {
                showTriggerNotification(s, 'Teleported to map location', 'navigation_arrival');
            }
        }
        return;
    }

    if (event.event_type === 'seatLayoutChanged') {
        if (event.payload?.success) {
            s.setSeatingLayout(event.payload.variant);
            if (Array.isArray(event.payload.variants) && event.payload.variants.length > 0) {
                s.setAvailableSeatingLayouts(event.payload.variants);
            }
            console.log(`Seating layout switched to: ${event.payload.variant}`);
        } else {
            console.warn(`Seating layout switch failed: ${event.payload?.error}`);
        }
        return;
    }

    if (event.event_type === 'seatedCrowdLayoutChanged') {
        if (event.payload?.success) {
            s.setSeatedCrowdLayout(event.payload.variant);
            if (Array.isArray(event.payload.variants) && event.payload.variants.length > 0) {
                s.setAvailableSeatedCrowdLayouts(event.payload.variants);
            }
            console.log(`Seated crowd density switched to: ${event.payload.variant}`);
        } else {
            console.warn(`Seated crowd density switch failed: ${event.payload?.error}`);
        }
        return;
    }
}
