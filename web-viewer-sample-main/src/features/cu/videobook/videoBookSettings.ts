/**
 * Shared, in-session Video Book user preferences.
 *
 * The settings panel (`VideoBookSettingsPanel.tsx`) provides the UI; this module owns the
 * canonical step tables so the player (`VideoBookPlayer.tsx`) and the overlay
 * (`VideoBookOverlay.tsx`) can read the same source of truth without circular imports.
 *
 * Caption size and playback speed are modelled as **discrete 3-step** indices (0 / 1 / 2),
 * matching the slider stops in Figma (small / default / large, slow / normal / fast). The
 * concrete `pct` / `rate` values live alongside the labels here so wiring code can derive
 * the actual CSS / mediaElement values without hard-coding magic numbers elsewhere.
 *
 * The live values live in `VideoBookSettingsContext` (mounted in `StreamOnlyWindow`) so
 * they persist for the whole browser session — closing and reopening the videobook keeps
 * the user's choices. Refreshing the page resets to the defaults; no localStorage involved.
 */

export type CaptionSizeIndex = 0 | 1 | 2;
export type PlaybackSpeedIndex = 0 | 1 | 2;

export interface CaptionSizeStep {
    index: CaptionSizeIndex;
    /** Size vs default 18px (100%) — used in aria/labels; CSS uses 14 / 18 / 30px. */
    pct: number;
    labelKey: string;
}

export interface PlaybackSpeedStep {
    index: PlaybackSpeedIndex;
    /** Maps directly to `HTMLMediaElement.playbackRate` when wired up. */
    rate: number;
    labelKey: string;
}

/**
 * Caption size scale (Figma): small 14px, default 18px, large 30px — see `VideoBookPlayer.css`
 * and 360° / spatial caption styles.
 */
export const CAPTION_SIZE_STEPS: readonly CaptionSizeStep[] = [
    { index: 0, pct: 78,  labelKey: 'videobook.videoSettings.captionFontSizeSmall' },
    { index: 1, pct: 100, labelKey: 'videobook.videoSettings.captionFontSizeDefault' },
    { index: 2, pct: 167, labelKey: 'videobook.videoSettings.captionFontSizeLarge' },
] as const;

export const DEFAULT_CAPTION_SIZE_INDEX: CaptionSizeIndex = 1;

/**
 * Playback speed scale. Captions follow naturally — `HTMLTrackElement` cue scheduling
 * is driven off the video's `currentTime`, which advances at `playbackRate`, so a 0.5×
 * video shows each cue twice as long without any extra plumbing.
 */
export const PLAYBACK_SPEED_STEPS: readonly PlaybackSpeedStep[] = [
    { index: 0, rate: 0.5, labelKey: 'videobook.videoSettings.playbackSpeedSlow' },
    { index: 1, rate: 1.0, labelKey: 'videobook.videoSettings.playbackSpeedNormal' },
    { index: 2, rate: 1.5, labelKey: 'videobook.videoSettings.playbackSpeedFast' },
] as const;

export const DEFAULT_PLAYBACK_SPEED_INDEX: PlaybackSpeedIndex = 1;
