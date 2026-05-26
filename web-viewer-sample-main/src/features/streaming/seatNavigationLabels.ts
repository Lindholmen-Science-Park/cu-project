/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 */
import type { TFunction } from 'i18next';
import type { RouteMeasure } from './types';

/** Remaining walk ETA for the seat nav card (Kit *Actual* updates while moving; sub-minute routes must not read as "1 min"). */
export function formatSeatNavTimeRemainingLabel(totalSeconds: number, t: TFunction): string {
    const s = Math.max(0, totalSeconds);
    if (s < 60) {
        return t('seat.secondsLeft', { count: Math.max(1, Math.round(s)) });
    }
    return t('seat.minutesLeft', { count: Math.max(1, Math.round(s / 60)) });
}

export function fmtNavMeters(n: number): string {
    return n < 10 ? n.toFixed(1) : String(Math.round(n));
}

/** Turn-by-turn pill copy from Kit `navigation_guide` + live `navigationNext*` fields. */
export function seatNavigationPillText(
    rm: RouteMeasure | null | undefined,
    t: TFunction,
    forceGenericApproach: boolean = false,
): string | null {
    if (!rm?.navigationSteps?.length) return null;
    const dest = rm.navigationDestinationKind || 'unknown';
    const approachLabel = (m: string): string => {
        if (forceGenericApproach) return t('seat.navApproachGeneric', { meters: m });
        if (dest === 'seat') return t('seat.navApproachSeat', { meters: m });
        if (dest === 'exit') return t('seat.navApproachExit', { meters: m });
        if (dest === 'restroom') return t('seat.navApproachRestroom', { meters: m });
        if (dest === 'quiet_zone') return t('seat.navApproachQuietZone', { meters: m });
        return t('seat.navApproachGeneric', { meters: m });
    };
    if (
        rm.navigationNextMeters != null &&
        rm.navigationNextMeters > 0 &&
        rm.navigationNextAction
    ) {
        const m = fmtNavMeters(rm.navigationNextMeters);
        const act = rm.navigationNextAction;
        if (act === 'turn_left') return t('seat.navNextTurnLeft', { meters: m });
        if (act === 'turn_right') return t('seat.navNextTurnRight', { meters: m });
        if (act === 'approach') return approachLabel(m);
    }
    const first = rm.navigationSteps[0];
    if (first?.action === 'straight' && first.distanceMeters != null && first.distanceMeters > 0) {
        return t('seat.navContinueStraight', { meters: fmtNavMeters(first.distanceMeters) });
    }
    if (first?.action === 'approach' && first.distanceMeters != null && first.distanceMeters > 0) {
        return approachLabel(fmtNavMeters(first.distanceMeters));
    }
    return null;
}

/** Format a seat key like "O-8-11" into "Section O, Row 8, Seat 11".
 *  Wheelchair rows (WC) omit the row: "Section C, Seat 1" (lookup id may be R1 — show ticket number only). */
export function formatSeatLabel(key: string, t: (k: string, opts?: Record<string, any>) => string): string {
    const parts = key.split('-');
    if (parts.length < 3) return key;
    const [section, row, ...seatParts] = parts;
    let seat = seatParts.join('-');
    if (row.toUpperCase() === 'WC') {
        const wcNum = /^[rR](\d+)$/.exec(seat);
        if (wcNum) seat = wcNum[1];
        return t('seat.sectionSeatLabel', { section, seat });
    }
    return t('seat.sectionRowSeatLabel', { section, row, seat });
}
