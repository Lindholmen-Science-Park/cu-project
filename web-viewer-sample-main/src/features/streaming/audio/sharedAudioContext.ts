/**
 * One AudioContext for the whole app.
 *
 * Both the Spatial Sound Overlay (Omnitone FOA decoder) and the
 * ambient sound engine (PannerNode pool) share this context so a
 * single hardware output is driven and the overlay can duck the
 * ambient bus without fighting over a second context.
 *
 * Browsers start the context in `suspended` state until a user
 * gesture unlocks it. Call `unlockSharedAudioContext()` inside a
 * pointerdown/click handler once per session.
 */

let ctx: AudioContext | null = null;

export function getSharedAudioContext(): AudioContext {
    if (!ctx) {
        const Ctor = (window as any).AudioContext || (window as any).webkitAudioContext;
        ctx = new Ctor();
    }
    return ctx!;
}

export async function unlockSharedAudioContext(): Promise<void> {
    const c = getSharedAudioContext();
    if (c.state === 'suspended') {
        try { await c.resume(); } catch { /* some browsers throw on repeated resume */ }
    }
}

export function hasSharedAudioContext(): boolean {
    return ctx !== null;
}
