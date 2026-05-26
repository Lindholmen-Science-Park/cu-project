export type ViewTransitionTarget = 'firstPerson' | 'birdEye';

/** Options for {@link beginViewTransition} — extend for future spawn flows. */
export interface BeginViewTransitionOptions {
    /** Reserved for analytics / future Kit payloads; does not change timing today. */
    target?: ViewTransitionTarget;
    /** Center label at full black (default from constants). */
    message?: string;
    /** Fires once the screen is fully opaque (black). Send Kit commands here, not before. */
    onFadeOutComplete?: () => void;
}
