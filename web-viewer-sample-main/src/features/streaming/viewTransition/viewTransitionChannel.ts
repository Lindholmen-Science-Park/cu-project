/**
 * Kit → React: when `viewTransitionReady` arrives, all subscribers are notified
 * so the overlay can fade in (or flush a pending ready that arrived during fade-out).
 */

type KitReadyListener = () => void;

const listeners = new Set<KitReadyListener>();

export function subscribeViewTransitionKitReady(listener: KitReadyListener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

export function notifyViewTransitionKitReady(): void {
    listeners.forEach((fn) => {
        try {
            fn();
        } catch {
            /* ignore */
        }
    });
}
