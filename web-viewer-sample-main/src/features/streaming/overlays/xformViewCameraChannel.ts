/**
 * Kit → React channel for `xformViewCameraReady`.
 *
 * Spatial-sound + 360° contexts dispatch `playerEnterXformView` and wait
 * for this ack before mounting their overlay — without gating, the
 * overlay paints before the WebRTC frame at the new pose lands and
 * shows the previous view bleeding through. Onboarding bypasses gating
 * (card must show immediately for the permission grant); the overlay's
 * Start tap re-enters the same flow.
 *
 * Mirrors `viewTransitionChannel` for consistency.
 */

export interface XformViewCameraReady {
    primPath: string;
    /** false on prim-missing / teleport-failure. Web opens anyway so the UI never wedges. */
    ok: boolean;
}

type Listener = (payload: XformViewCameraReady) => void;

const listeners = new Set<Listener>();

export function subscribeXformViewCameraReady(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

export function notifyXformViewCameraReady(payload: XformViewCameraReady): void {
    listeners.forEach((fn) => {
        try {
            fn(payload);
        } catch {
            /* ignore */
        }
    });
}
