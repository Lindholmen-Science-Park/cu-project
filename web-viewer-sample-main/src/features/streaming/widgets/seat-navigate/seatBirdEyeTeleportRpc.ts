import { sendMessage } from '../../messaging';
import type { SeatQuery } from './types';

/**
 * Bird-eye seat-teleport preflight RPC.
 *
 * The bird-eye "Teleport me there" flow starts a fade-to-black overlay
 * whose only exit is Kit's `viewTransitionReady` event. If the requested
 * seat doesn't exist, Kit's executor bails silently and the user is stuck
 * on the black "Entering first person…" overlay — so we validate first via
 * the synchronous `seatTeleportFromBirdEyeCheck` event and only start the
 * fade once Kit confirms the seat is teleportable.
 */

export interface SeatBirdEyeCheckResult {
    ok: boolean;
    /** Kit-side reason — `not_found`, `not_available`, `invalid_input`, or `timeout`. */
    error?: string;
    seatNumber?: string;
}

type Resolver = (result: SeatBirdEyeCheckResult) => void;

const pending = new Map<string, Resolver>();
let nextId = 1;

const REQUEST_TIMEOUT_MS = 5000;

/**
 * Send a preflight check to Kit and wait for the response.
 * Resolves to `{ok: false, error: 'timeout'}` if Kit doesn't respond in time
 * (defensive — Kit always responds, this just prevents a wedged Promise).
 */
export function requestSeatTeleportFromBirdEyeCheck(query: SeatQuery): Promise<SeatBirdEyeCheckResult> {
    return new Promise((resolve) => {
        const requestId = `seat-bird-eye-tp-${Date.now()}-${nextId++}`;
        const settle = (result: SeatBirdEyeCheckResult): void => {
            if (!pending.delete(requestId)) return;
            resolve(result);
        };
        pending.set(requestId, settle);

        try {
            sendMessage('seatTeleportFromBirdEyeCheck', {
                section: query.section,
                row: query.row,
                seat: query.seat,
                requestId,
            });
        } catch {
            settle({ ok: false, error: 'send_failed' });
            return;
        }

        setTimeout(() => settle({ ok: false, error: 'timeout' }), REQUEST_TIMEOUT_MS);
    });
}

/** Called from the central seat event handler when Kit responds. */
export function resolveSeatTeleportFromBirdEyeCheck(
    requestId: string,
    result: SeatBirdEyeCheckResult,
): void {
    const resolver = pending.get(requestId);
    if (!resolver) return;
    resolver(result);
}
