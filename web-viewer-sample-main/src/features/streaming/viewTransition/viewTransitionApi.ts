import type { BeginViewTransitionOptions, ViewTransitionTarget } from './types';

type BeginHandler = (opts: BeginViewTransitionOptions) => void;

let handler: BeginHandler | null = null;

/** Called once from StreamOnlyWindow when the view-transition hook is mounted. */
export function registerViewTransitionBegin(fn: BeginHandler | null): void {
    handler = fn;
}

/**
 * Start the full-screen transition (fade out → “Loading” at black → wait for Kit
 * `viewTransitionReady` → fade in). Use from map markers, chat, seat teleports, etc.
 */
export function beginViewTransition(
    options?: BeginViewTransitionOptions | ViewTransitionTarget,
): void {
    if (!handler) return;
    if (options === undefined || options === null) {
        handler({});
        return;
    }
    if (options === 'firstPerson' || options === 'birdEye') {
        handler({ target: options });
        return;
    }
    handler(options);
}

export type { BeginViewTransitionOptions, ViewTransitionTarget } from './types';
