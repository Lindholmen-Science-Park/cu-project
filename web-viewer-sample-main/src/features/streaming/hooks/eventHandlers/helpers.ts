/**
 * Shared utility functions extracted from event handler logic to avoid
 * repeating the same timer-based notification / celebration patterns.
 */

import i18n from 'i18next';
import { sendMessage } from '../../messaging';
import type { PoiResult } from '../../types';
import { resolvePoiLocalizedTitle } from '../../utils/poiLocalizedTitle';

export function revertWheelchairMode(ctx: { setNavmeshMode: React.Dispatch<React.SetStateAction<'wheelchair' | 'walking'>> }): void {
    ctx.setNavmeshMode((prev) => {
        if (prev !== 'wheelchair') return prev;
        try { sendMessage('navmeshModeSet', { mode: 'walking' }); } catch {}
        return 'walking';
    });
}

export interface TriggerNotificationContext {
    setTriggerZoneNotification: React.Dispatch<React.SetStateAction<{ message: string; zoneType: string } | null>>;
    triggerZoneTimerRef: React.MutableRefObject<number | null>;
}

export function showTriggerNotification(
    ctx: TriggerNotificationContext,
    message: string,
    zoneType: string,
    durationMs = 5000,
): void {
    if (ctx.triggerZoneTimerRef.current) window.clearTimeout(ctx.triggerZoneTimerRef.current);
    ctx.setTriggerZoneNotification({ message, zoneType });
    ctx.triggerZoneTimerRef.current = window.setTimeout(() => {
        ctx.setTriggerZoneNotification(null);
        ctx.triggerZoneTimerRef.current = null;
    }, durationMs);
}

export interface SeatCelebrationContext {
    setSeatArrivalCelebrationVisible: React.Dispatch<React.SetStateAction<boolean>>;
    seatArrivalCelebrationTimerRef: React.MutableRefObject<number | null>;
}

/** Seat teleport sets facing on Kit; skip smooth turn to avoid double-rotation. */
export interface SeatArrivalCelebrationOptions {
    skipFaceTowardCenter?: boolean;
}

export function scheduleSeatArrivalCelebration(
    ctx: SeatCelebrationContext,
    options?: SeatArrivalCelebrationOptions,
): void {
    if (ctx.seatArrivalCelebrationTimerRef.current) window.clearTimeout(ctx.seatArrivalCelebrationTimerRef.current);
    ctx.setSeatArrivalCelebrationVisible(true);
    if (!options?.skipFaceTowardCenter) {
        try {
            sendMessage('playerFaceStadiumCenter', {});
        } catch {
            /* stream may not be ready */
        }
    }
    ctx.seatArrivalCelebrationTimerRef.current = window.setTimeout(() => {
        ctx.setSeatArrivalCelebrationVisible(false);
        ctx.seatArrivalCelebrationTimerRef.current = null;
    }, 5000);
}

export interface PoiArrivalContext {
    setPoiArrivalVisible: React.Dispatch<React.SetStateAction<boolean>>;
    poiArrivalTimerRef: React.MutableRefObject<number | null>;
    setPoiArrivalLabel: React.Dispatch<React.SetStateAction<string | null>>;
}

function lookupPoiListTitle(
    poiType: 'restroom' | 'quiet_zone',
    results: PoiResult[],
    primPath: string | null,
    routeKey: string | null,
    fallbackKey: string,
    sectionFallback: (n: number) => string,
): string {
    if (!results.length) return i18n.t(fallbackKey);
    for (let i = 0; i < results.length; i++) {
        const r = results[i];
        const ref = typeof r.poiRef === 'string' ? r.poiRef : '';
        const key = (r.poiId || ref || `poi_${i}`) as string;
        if ((primPath && ref === primPath) || (routeKey && key === routeKey)) {
            return (
                resolvePoiLocalizedTitle(poiType, (r.metadata || {}) as Record<string, unknown>, (k, o) =>
                    i18n.t(k, o),
                ) || sectionFallback(i + 1)
            );
        }
    }
    return i18n.t(fallbackKey);
}

/** Label for restroom arrival — matches in-flight nav overlay resolution. */
export function resolveRestroomArrivalLabel(args: {
    displayNameRef: React.MutableRefObject<string | null>;
    primPathRef: React.MutableRefObject<string | null>;
    routeIdRef: React.MutableRefObject<string | null>;
    resultsRef: React.MutableRefObject<PoiResult[]>;
}): string {
    const fromRef = args.displayNameRef.current?.trim();
    if (fromRef) return fromRef;
    return lookupPoiListTitle(
        'restroom',
        args.resultsRef.current,
        args.primPathRef.current,
        args.routeIdRef.current,
        'search.findToilet',
        (n) => i18n.t('search.toiletSection', { n }),
    );
}

/** Label for quiet-zone arrival — matches in-flight nav overlay resolution. */
export function resolveQuietZoneArrivalLabel(args: {
    displayNameRef: React.MutableRefObject<string | null>;
    primPathRef: React.MutableRefObject<string | null>;
    routeIdRef: React.MutableRefObject<string | null>;
    resultsRef: React.MutableRefObject<PoiResult[]>;
}): string {
    const fromRef = args.displayNameRef.current?.trim();
    if (fromRef) return fromRef;
    return lookupPoiListTitle(
        'quiet_zone',
        args.resultsRef.current,
        args.primPathRef.current,
        args.routeIdRef.current,
        'search.findQuietArea',
        (n) => i18n.t('search.quietAreaPlaceholder', { n }),
    );
}

export function schedulePoiArrival(
    ctx: PoiArrivalContext,
    label: string,
    durationMs = 5000,
): void {
    if (ctx.poiArrivalTimerRef.current) {
        window.clearTimeout(ctx.poiArrivalTimerRef.current);
        ctx.poiArrivalTimerRef.current = null;
    }
    ctx.setPoiArrivalLabel(label);
    ctx.setPoiArrivalVisible(true);
    ctx.poiArrivalTimerRef.current = window.setTimeout(() => {
        ctx.setPoiArrivalVisible(false);
        ctx.poiArrivalTimerRef.current = null;
    }, durationMs);
}

/** Mirror seat teleport cleanup so stream nav overlays and CU chrome restore. */
export function clearPoiNavigationAfterTeleport(s: {
    setActivePoiRouteId: React.Dispatch<React.SetStateAction<string | null>>;
    setMovingToPoiId: React.Dispatch<React.SetStateAction<string | null>>;
    lastPoiPrimPathRef?: React.MutableRefObject<string | null>;
    lastPoiDisplayNameRef?: React.MutableRefObject<string | null>;
    lastPoiEndPosRef?: React.MutableRefObject<[number, number, number] | null>;
    setRestroomTrackingScreen: React.Dispatch<React.SetStateAction<boolean>>;
    setRestroomWidgetOpen: React.Dispatch<React.SetStateAction<boolean>>;
    setActiveQuietZoneRouteId: React.Dispatch<React.SetStateAction<string | null>>;
    setMovingToQuietZoneId: React.Dispatch<React.SetStateAction<string | null>>;
    lastQuietZonePrimPathRef?: React.MutableRefObject<string | null>;
    lastQuietZoneDisplayNameRef?: React.MutableRefObject<string | null>;
    setQuietZoneTrackingScreen: React.Dispatch<React.SetStateAction<boolean>>;
    setQuietZoneWidgetOpen: React.Dispatch<React.SetStateAction<boolean>>;
}): void {
    try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch { /* stream */ }
    try { sendMessage('navmeshRouteStop', { routeId: 'quiet_zone_nav' }); } catch { /* stream */ }
    s.setActivePoiRouteId(null);
    s.setMovingToPoiId(null);
    if (s.lastPoiPrimPathRef) s.lastPoiPrimPathRef.current = null;
    if (s.lastPoiDisplayNameRef) s.lastPoiDisplayNameRef.current = null;
    if (s.lastPoiEndPosRef) s.lastPoiEndPosRef.current = null;
    s.setRestroomTrackingScreen(false);
    s.setRestroomWidgetOpen(false);
    s.setActiveQuietZoneRouteId(null);
    s.setMovingToQuietZoneId(null);
    if (s.lastQuietZonePrimPathRef) s.lastQuietZonePrimPathRef.current = null;
    if (s.lastQuietZoneDisplayNameRef) s.lastQuietZoneDisplayNameRef.current = null;
    s.setQuietZoneTrackingScreen(false);
    s.setQuietZoneWidgetOpen(false);
}
