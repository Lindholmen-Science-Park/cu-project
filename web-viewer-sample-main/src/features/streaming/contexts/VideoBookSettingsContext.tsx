import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import {
    DEFAULT_CAPTION_SIZE_INDEX,
    DEFAULT_PLAYBACK_SPEED_INDEX,
    type CaptionSizeIndex,
    type PlaybackSpeedIndex,
} from '../../cu/videobook/videoBookSettings';

/**
 * Session-scoped Video Book user preferences.
 *
 * State lives in the streaming context tree (mounted once in `StreamOnlyWindow.tsx`,
 * alongside the other media-overlay contexts) so the player and the settings panel share
 * the same values across view transitions, panel re-mounts, and even videobook
 * close/reopen cycles within the same browser session. Refreshing the page resets to the
 * defaults — no localStorage / cookies involved.
 *
 * Field-by-field intent:
 *   - `captionSizeIndex` — small / default / large caption font; bound to the captions
 *     slider in `VideoBookSettingsPanel` and to the `data-caption-size` attribute on the
 *     custom captions strip in `VideoBookPlayer`.
 *   - `autoplayEnabled` — mirror of the player's "play continuously through every chapter
 *     dot" mode (`fullVideoMode`). Overlay entry-points write it (icon / splash / menu
 *     "Autoplay" → true; chapter-row click → false); the settings-panel PillSwitch reads
 *     and writes it so the user can flip the mode mid-playback (replacing the in-player
 *     Autoplay button that used to sit next to mute).
 *   - `muted` — mirror of the in-player mute button so the volume preference survives
 *     closing & reopening the videobook within the same session.
 *   - `captionsOn` — mirror of the in-player CC button (same survival semantics).
 *   - `playbackSpeedIndex` — slow / normal / fast multiplier picked in the settings panel;
 *     applied to `HTMLVideoElement.playbackRate` by the player.
 */
export interface VideoBookSettingsContextType {
    captionSizeIndex: CaptionSizeIndex;
    setCaptionSizeIndex: (next: CaptionSizeIndex) => void;
    autoplayEnabled: boolean;
    setAutoplayEnabled: (next: boolean) => void;
    muted: boolean;
    setMuted: (next: boolean) => void;
    captionsOn: boolean;
    setCaptionsOn: (next: boolean) => void;
    playbackSpeedIndex: PlaybackSpeedIndex;
    setPlaybackSpeedIndex: (next: PlaybackSpeedIndex) => void;
}

const VideoBookSettingsContext = createContext<VideoBookSettingsContextType | null>(null);

export function VideoBookSettingsProvider({ children }: { children: React.ReactNode }) {
    const [captionSizeIndex, setCaptionSizeIndexState] = useState<CaptionSizeIndex>(
        DEFAULT_CAPTION_SIZE_INDEX,
    );
    /* Default ON to match the historic "splash → autoplay" first-open path. */
    const [autoplayEnabled, setAutoplayEnabledState] = useState<boolean>(true);
    /* Mute / captions default off so the very first open behaves like the legacy player. */
    const [muted, setMutedState] = useState<boolean>(false);
    const [captionsOn, setCaptionsOnState] = useState<boolean>(false);
    const [playbackSpeedIndex, setPlaybackSpeedIndexState] = useState<PlaybackSpeedIndex>(
        DEFAULT_PLAYBACK_SPEED_INDEX,
    );

    const setCaptionSizeIndex = useCallback((next: CaptionSizeIndex) => {
        setCaptionSizeIndexState(next);
    }, []);

    const setAutoplayEnabled = useCallback((next: boolean) => {
        setAutoplayEnabledState(next);
    }, []);

    const setMuted = useCallback((next: boolean) => {
        setMutedState(next);
    }, []);

    const setCaptionsOn = useCallback((next: boolean) => {
        setCaptionsOnState(next);
    }, []);

    const setPlaybackSpeedIndex = useCallback((next: PlaybackSpeedIndex) => {
        setPlaybackSpeedIndexState(next);
    }, []);

    const value = useMemo<VideoBookSettingsContextType>(
        () => ({
            captionSizeIndex,
            setCaptionSizeIndex,
            autoplayEnabled,
            setAutoplayEnabled,
            muted,
            setMuted,
            captionsOn,
            setCaptionsOn,
            playbackSpeedIndex,
            setPlaybackSpeedIndex,
        }),
        [
            captionSizeIndex,
            setCaptionSizeIndex,
            autoplayEnabled,
            setAutoplayEnabled,
            muted,
            setMuted,
            captionsOn,
            setCaptionsOn,
            playbackSpeedIndex,
            setPlaybackSpeedIndex,
        ],
    );

    return (
        <VideoBookSettingsContext.Provider value={value}>
            {children}
        </VideoBookSettingsContext.Provider>
    );
}

export function useVideoBookSettings(): VideoBookSettingsContextType {
    const ctx = useContext(VideoBookSettingsContext);
    if (!ctx) throw new Error('useVideoBookSettings must be used within VideoBookSettingsProvider');
    return ctx;
}

export { VideoBookSettingsContext };
