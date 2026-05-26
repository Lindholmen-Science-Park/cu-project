import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { sendMessage } from '../../streaming/messaging';
import { shouldDeferImmersiveMediaShortcut } from '../../streaming/utils/immersiveMediaKeyboard';
import { useVideoBookSettings } from '../../streaming/contexts';
import { useControlsAutoHide } from '../../streaming/hooks/useControlsAutoHide';
import { PLAYBACK_SPEED_STEPS } from './videoBookSettings';
import type { VideoBookEntry } from './VideoBookOverlay';
import PanelCloseButton from '../../cu/controls/PanelCloseButton';
import {
    MediaSettingsButton,
    MediaMuteButton,
    MediaCaptionsButton,
    MediaPlayPauseButton,
} from '../../cu/controls/MediaPlayerControls';
import '../CUControls.css';
import './VideoBookOverlay.css';
import './VideoBookPlayer.css';
import { VideoBookFloatingChipIcon } from './VideoBookChipIcons';

const nucleusVideoModules: Record<string, string> = {};
const rawNucleusVideos = import.meta.glob(
    '../../../../../kit-app-template-main/source/data/nucleus/videos/*.{mp4,webm,ogg}',
    { eager: true, import: 'default' },
);
for (const [path, url] of Object.entries(rawNucleusVideos)) {
    const filename = path.split('/').pop();
    if (filename) nucleusVideoModules[filename] = url as string;
}

const kitVideoModules: Record<string, string> = {};
const rawKitVideos = import.meta.glob(
    '../../../../../kit-app-template-main/source/data/Assets/Videos/*.{mp4,webm,ogg}',
    { eager: true, import: 'default' },
);
for (const [path, url] of Object.entries(rawKitVideos)) {
    const filename = path.split('/').pop();
    if (filename) kitVideoModules[filename] = url as string;
}

function resolveVideoSource(source: string): string {
    if (source.startsWith('http://') || source.startsWith('https://')) return source;
    return nucleusVideoModules[source] || kitVideoModules[source] || source;
}

/**
 * Sidecar WebVTT captions live next to the videos under
 * `nucleus/videos/captions/<lang>/<videoBasename>.vtt`. The expander on the Kit side does
 * not need to know about them — the convention is purely a frontend lookup so localised
 * captions can be shipped without touching `interactions.json`. An explicit `captionsUrl`
 * on the entry still wins (back-compat with spatialSound / video360 plumbing).
 */
const captionVttModules: Record<string, Record<string, string>> = {};
{
    const rawCaptionVtts = import.meta.glob(
        '../../../../../kit-app-template-main/source/data/nucleus/videos/captions/*/*.vtt',
        { eager: true, import: 'default' },
    );
    for (const [path, url] of Object.entries(rawCaptionVtts)) {
        const parts = path.split('/');
        const filename = parts[parts.length - 1];
        const lang = parts[parts.length - 2];
        if (!filename || !lang) continue;
        const base = filename.replace(/\.vtt$/i, '');
        if (!captionVttModules[lang]) captionVttModules[lang] = {};
        captionVttModules[lang][base] = url as string;
    }
}

/**
 * Resolve the captions URL for a given video filename + active locale.
 * Falls back from regional locale ("en-GB") → base ("en"). Returns undefined when no
 * sidecar VTT exists for that combination (the CC button stays disabled in that case).
 */
function resolveCaptionSource(videoSource: string, lang: string): string | undefined {
    const filename = (videoSource.split('/').pop() || videoSource).replace(/\.[^.]+$/, '');
    if (!filename) return undefined;
    const base = String(lang || 'en').split('-')[0].toLowerCase();
    return captionVttModules[base]?.[filename];
}

/** From menu chapter button: play [startSeconds, endExclusiveSeconds) — same as dot at start to dot at next chapter. */
export interface PickedChapterSegment {
    startSeconds: number;
    /** Next chapter’s start time; `null` = play to end of file (last chapter). */
    endExclusiveSeconds: number | null;
}

interface VideoBookPlayerProps {
    entry: VideoBookEntry;
    startAtSeconds: number;
    /** When true: initial state is continuous playback (no chapter stops). When false: start in segment mode until the user turns autoplay on in the player. */
    fullVideoAutoplay?: boolean;
    /** When false, in-player autoplay is disabled and full mode is forced off. Default true — can be toggled anytime during playback (including after opening from a chapter). */
    allowFullVideoModeToggle?: boolean;
    /** Set when opening from a chapter row: exact stop at the next dot (next chapter start). */
    pickedChapterSegment?: PickedChapterSegment | null;
    onBack: () => void;
    onClose: () => void;
    /**
     * Open the Video Book settings panel (captions size, autoplay, playback speed). Hoisted
     * to `VideoBookOverlay` so the same panel can render above the chapter menu too.
     */
    onOpenSettings?: () => void;
    /**
     * When true, the top-right button stack (close / settings / chapters) is hidden so it
     * doesn't peek out from behind a foreground panel (e.g. the settings modal). Bottom
     * controls remain visible — they're far from the panel and useful for context.
     */
    topBarHidden?: boolean;
    /**
     * Captions font-size step (0 = small / 1 = default / 2 = large). Surfaced as a
     * `data-caption-size` attribute on the cue overlay so `VideoBookPlayer.css` can
     * scale the cue text via attribute selectors without re-renders or inline styles.
     */
    captionSizeIndex?: number;
}

function formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    const f = Math.floor((seconds % 1) * 100);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}:${String(f).padStart(2, '0')}`;
}

/** Unique sorted chapter start times (clamped to duration). Segments: [0, b0), [b0, b1), … [bn-1, duration]. */
function buildChapterBoundaries(
    chapters: Array<{ timestampSeconds: number }>,
    duration: number,
): number[] {
    const raw = chapters.map((c) => c.timestampSeconds).filter((x): x is number => Number.isFinite(x));
    if (raw.length === 0) return [];
    let sorted = [...new Set(raw)].sort((a, b) => a - b);
    if (duration > 0) {
        sorted = [...new Set(sorted.map((x) => Math.max(0, Math.min(x, duration))))].sort((a, b) => a - b);
    }
    return sorted;
}

/** End of the segment that contains `t` (playback pauses just before crossing this time when segment mode is on). */
function getSegmentEndForTime(t: number, boundaries: number[], duration: number): number {
    if (boundaries.length === 0) return duration;
    if (t < boundaries[0]) return boundaries[0];
    let idx = -1;
    for (let i = 0; i < boundaries.length; i++) {
        if (t >= boundaries[i]) idx = i;
    }
    if (idx < 0) return boundaries[0];
    const next = boundaries[idx + 1];
    return next != null ? next : duration;
}

/** Slack so we don’t miss a boundary between timeupdate ticks (often ~4Hz). */
const SEGMENT_END_EPS = 0.12;

/**
 * Segment boundary for current time `t` (same rules as enforce). Returns null when there are no chapter segments.
 * `t` may be snapped down to a menu-picked endExclusive when slightly past it.
 */
function resolveSegmentPauseState(
    tIn: number,
    duration: number,
    chapterBoundaries: number[],
    pickedChapterSegment: PickedChapterSegment | null,
    pickedSecondDotPaused: boolean,
): { t: number; segmentEnd: number } | null {
    if (!Number.isFinite(duration) || duration <= 0) return null;
    if (chapterBoundaries.length === 0 && !pickedChapterSegment) return null;

    let t = tIn;
    let segmentEnd: number;

    if (
        pickedChapterSegment?.endExclusiveSeconds != null
        && !pickedSecondDotPaused
    ) {
        const endExclusive = Math.min(pickedChapterSegment.endExclusiveSeconds, duration);
        if (t <= endExclusive + SEGMENT_END_EPS) {
            if (t > endExclusive) {
                t = endExclusive;
            }
            segmentEnd = endExclusive;
        } else {
            segmentEnd = chapterBoundaries.length > 0
                ? getSegmentEndForTime(t, chapterBoundaries, duration)
                : duration;
        }
    } else if (pickedChapterSegment && pickedChapterSegment.endExclusiveSeconds == null) {
        segmentEnd = chapterBoundaries.length > 0
            ? getSegmentEndForTime(t, chapterBoundaries, duration)
            : duration;
    } else if (chapterBoundaries.length > 0) {
        segmentEnd = getSegmentEndForTime(t, chapterBoundaries, duration);
    } else {
        segmentEnd = duration;
    }

    return { t, segmentEnd };
}

const VideoBookPlayer: React.FC<VideoBookPlayerProps> = ({
    entry,
    startAtSeconds,
    fullVideoAutoplay: initialFullVideoAutoplay = false,
    allowFullVideoModeToggle = true,
    pickedChapterSegment = null,
    onBack,
    onClose,
    onOpenSettings,
    topBarHidden = false,
    captionSizeIndex = 1,
}) => {
    const { t, i18n } = useTranslation();
    const videoRef = useRef<HTMLVideoElement>(null);
    /** After we pause at the menu-picked “second dot”, use normal segment rules so Play can continue. */
    const pickedSecondDotPausedRef = useRef(false);
    /** Autoplay just turned off while playing: keep playing until this segment’s end (next dot), then pause. */
    const playToSegmentEndAfterAutoplayOffRef = useRef(false);
    const seekBarRef = useRef<HTMLDivElement>(null);

    const resolvedSource = useMemo(() => resolveVideoSource(entry.videoUrl), [entry.videoUrl]);

    const sortedChapters = useMemo(
        () => [...entry.chapters].sort((a, b) => a.timestampSeconds - b.timestampSeconds),
        [entry.chapters],
    );

    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const {
        chromeVisible,
        chromeRootRef,
        resetControlsTimer,
        onChromeFocusCapture,
        onChromeBlurCapture,
    } = useControlsAutoHide(3000);
    /** true = continuous playback; false = pause at each chapter segment boundary. */
    const [fullVideoMode, setFullVideoMode] = useState(initialFullVideoAutoplay);
    /**
     * Mirrors `fullVideoMode` but is updated synchronously inside the toggle updater so `timeupdate` /
     * `playing` handlers don’t run segment enforcement with stale state for a frame after turning autoplay on.
     */
    const fullVideoModeRef = useRef(initialFullVideoAutoplay);
    /**
     * Active cue text mirrored out of the (hidden) `TextTrack`. We render captions ourselves so we
     * can use the brand Lexend font, the dark "chip" treatment from Figma, and lift the strip above
     * the bottom controls when they are visible — none of which native `::cue` rendering allows.
     */
    const [activeCueText, setActiveCueText] = useState<string>('');
    const [isSeeking, setIsSeeking] = useState(false);
    /**
     * Mute, captions on/off, and playback speed live in `VideoBookSettingsContext` so the
     * choices survive view transitions and videobook close/reopen within the same session
     * (the panel exposes speed; the in-player buttons toggle mute and CC). Caption-strip
     * font size is also read here for the `data-caption-size` attribute below.
     */
    const {
        muted,
        setMuted,
        captionsOn,
        setCaptionsOn,
        playbackSpeedIndex,
    } = useVideoBookSettings();

    const chapterBoundaries = useMemo(
        () => buildChapterBoundaries(entry.chapters, duration),
        [entry.chapters, duration],
    );

    const captionLang = useMemo(
        () => String(i18n.language || 'en').split('-')[0].toLowerCase(),
        [i18n.language],
    );
    /**
     * Explicit `entry.captionsUrl` (passed from the Kit-side payload) wins; otherwise we
     * auto-discover a sidecar VTT keyed by the active locale + video basename.
     */
    const resolvedCaptionsUrl = useMemo(
        () => entry.captionsUrl || resolveCaptionSource(entry.videoUrl, captionLang),
        [entry.captionsUrl, entry.videoUrl, captionLang],
    );
    const hasCaptions = !!resolvedCaptionsUrl;

    useEffect(() => {
        if (!allowFullVideoModeToggle) {
            fullVideoModeRef.current = false;
            setFullVideoMode(false);
        }
    }, [allowFullVideoModeToggle]);

    useEffect(() => {
        sendMessage('movementInputControl', { enabled: false });
        return () => { sendMessage('movementInputControl', { enabled: true }); };
    }, []);

    /* useLayoutEffect + autoPlay: start playback before paint so user-activation from the menu click still applies (useEffect runs too late and play() is often blocked). */
    useLayoutEffect(() => {
        pickedSecondDotPausedRef.current = false;
        playToSegmentEndAfterAutoplayOffRef.current = false;
        const video = videoRef.current;
        if (!video) return;
        const startPlayback = () => {
            if (startAtSeconds > 0) video.currentTime = startAtSeconds;
            void video.play().catch(() => {});
        };
        if (video.readyState >= 3) {
            startPlayback();
        } else {
            video.addEventListener('canplay', startPlayback, { once: true });
            return () => video.removeEventListener('canplay', startPlayback);
        }
    }, [startAtSeconds, resolvedSource, pickedChapterSegment]);

    const activeChapterIndex = useMemo(() => {
        const chapters = sortedChapters;
        for (let i = chapters.length - 1; i >= 0; i--) {
            if (currentTime >= chapters[i].timestampSeconds) return i;
        }
        return -1;
    }, [currentTime, sortedChapters]);

    /** Tap on the video area: bring controls back and re-arm the auto-hide. Never affects play/pause — that's the play button's job only. */
    const handleVideoAreaTap = useCallback(() => {
        resetControlsTimer();
    }, [resetControlsTimer]);

    const togglePlayPause = useCallback(() => {
        const video = videoRef.current;
        if (!video) return;
        if (video.paused) video.play().catch(() => {});
        else video.pause();
    }, []);

    const seekTo = useCallback((seconds: number) => {
        const video = videoRef.current;
        if (video) {
            playToSegmentEndAfterAutoplayOffRef.current = false;
            video.currentTime = seconds;
            resetControlsTimer();
        }
    }, [resetControlsTimer]);

    const skipPrev = useCallback(() => {
        const chapters = sortedChapters;
        if (chapters.length === 0) return;
        if (activeChapterIndex <= 0) {
            seekTo(0);
            return;
        }
        seekTo(chapters[activeChapterIndex - 1].timestampSeconds);
    }, [sortedChapters, activeChapterIndex, seekTo]);

    const skipNext = useCallback(() => {
        const chapters = sortedChapters;
        if (chapters.length === 0) return;
        if (activeChapterIndex < 0) {
            seekTo(chapters[0].timestampSeconds);
            return;
        }
        const target = activeChapterIndex < chapters.length - 1 ? activeChapterIndex + 1 : activeChapterIndex;
        seekTo(chapters[target].timestampSeconds);
    }, [sortedChapters, activeChapterIndex, seekTo]);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (topBarHidden || shouldDeferImmersiveMediaShortcut(e)) return;
            if (e.key === 'Escape') { onClose(); }
            else if (e.key === ' ' || e.key === 'k') { e.preventDefault(); togglePlayPause(); }
            else if (e.key === 'ArrowLeft') { e.preventDefault(); skipPrev(); }
            else if (e.key === 'ArrowRight') { e.preventDefault(); skipNext(); }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [topBarHidden, onClose, togglePlayPause, skipPrev, skipNext]);

    /**
     * Apply a target value for `fullVideoMode` and run the same side-effects the in-player
     * Autoplay button used to perform before it was replaced by the mute button:
     *   - turning ON: drop any deferred-pause flag and mark "we already passed our second
     *     chapter dot" so segment enforcement doesn't snap back to the previous boundary;
     *   - turning OFF mid-playback: keep playing to the next dot (`playToSegmentEndAfter…`)
     *     so the transition feels smooth instead of pausing instantly mid-sentence.
     * Ignored when the parent has disabled the toggle entirely (`allowFullVideoModeToggle`
     * = false), which currently never happens but is preserved for future flows.
     */
    const applyFullVideoMode = useCallback((next: boolean) => {
        if (!allowFullVideoModeToggle && next) return;
        if (fullVideoModeRef.current === next) return;
        fullVideoModeRef.current = next;
        if (next) {
            pickedSecondDotPausedRef.current = true;
            playToSegmentEndAfterAutoplayOffRef.current = false;
        } else {
            const video = videoRef.current;
            const canDeferToSegmentEnd =
                video
                && !video.paused
                && Number.isFinite(duration)
                && duration > 0
                && (chapterBoundaries.length > 0 || pickedChapterSegment != null);
            if (canDeferToSegmentEnd) {
                const resolved = resolveSegmentPauseState(
                    video.currentTime,
                    duration,
                    chapterBoundaries,
                    pickedChapterSegment,
                    pickedSecondDotPausedRef.current,
                );
                if (resolved != null) {
                    playToSegmentEndAfterAutoplayOffRef.current = true;
                }
            }
        }
        setFullVideoMode(next);
    }, [allowFullVideoModeToggle, chapterBoundaries, duration, pickedChapterSegment]);

    /**
     * Re-sync `fullVideoMode` whenever `initialFullVideoAutoplay` changes after mount —
     * this is how the settings-panel toggle reaches us: panel writes the context value,
     * the overlay re-passes it as the prop, and we apply it here. The first render is a
     * no-op because `fullVideoMode` was initialised from the same prop above; subsequent
     * changes flip the live mode with the deferred-pause logic above.
     */
    useEffect(() => {
        applyFullVideoMode(initialFullVideoAutoplay);
    }, [initialFullVideoAutoplay, applyFullVideoMode]);

    const toggleMuted = useCallback(() => {
        const video = videoRef.current;
        if (!video) return;
        const next = !video.muted;
        video.muted = next;
        setMuted(next);
    }, [setMuted]);

    const toggleCaptions = useCallback(() => {
        setCaptionsOn(!captionsOn);
    }, [captionsOn, setCaptionsOn]);

    /**
     * Keep `HTMLVideoElement.playbackRate` in sync with the user's chosen speed step. We
     * also write `defaultPlaybackRate` so that any place that resets playback (e.g. some
     * browsers after a media session interruption) restarts at the user's preferred rate
     * instead of snapping back to 1.0×.
     */
    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;
        const step = PLAYBACK_SPEED_STEPS[playbackSpeedIndex] ?? PLAYBACK_SPEED_STEPS[1];
        video.playbackRate = step.rate;
        video.defaultPlaybackRate = step.rate;
    }, [playbackSpeedIndex, resolvedSource]);

    /**
     * Drive cue scheduling via the browser's native `<track>` machinery (which parses VTT for
     * us), but suppress the native cue rendering and mirror the active cue text into our own
     * `activeCueText` state so we can style + position the caption strip ourselves.
     *
     * `mode = 'hidden'` keeps the parser running and `cuechange` firing without showing the
     * default white-on-translucent-black box at the bottom of the video. `mode = 'disabled'`
     * stops parsing entirely (cheap when captions are off).
     *
     * The `<track>` element is re-keyed on locale change so the browser refetches the new VTT;
     * the dependency on `captionLang` / `resolvedCaptionsUrl` re-runs this effect against the
     * fresh `TextTrack` instance after that remount.
     */
    useEffect(() => {
        const video = videoRef.current;
        if (!video || !video.textTracks.length) {
            setActiveCueText('');
            return;
        }
        const track = video.textTracks[0];
        if (!captionsOn) {
            track.mode = 'disabled';
            setActiveCueText('');
            return;
        }
        track.mode = 'hidden';
        const updateCue = () => {
            const cues = track.activeCues;
            if (!cues || cues.length === 0) {
                setActiveCueText('');
                return;
            }
            const text = Array.from(cues)
                .map((c) => (c as VTTCue).text || '')
                .join('\n')
                .replace(/<[^>]+>/g, '')
                .trim();
            setActiveCueText(text);
        };
        updateCue();
        track.addEventListener('cuechange', updateCue);
        return () => {
            track.removeEventListener('cuechange', updateCue);
        };
    }, [captionsOn, captionLang, resolvedCaptionsUrl]);

    /**
     * Open the Video Book settings panel via the parent overlay (so the panel can also be
     * opened from the chapter menu). Falls back to a no-op if the parent didn't pass a handler,
     * which keeps the button defensive against props omissions.
     */
    const handleOpenSettings = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
        e.stopPropagation();
        onOpenSettings?.();
    }, [onOpenSettings]);

    /** Segment mode: pause at every boundary. Menu chapter pick: hard stop on the next dot (second marker). */
    const enforceSegmentPause = useCallback(
        (video: HTMLVideoElement) => {
            if (fullVideoModeRef.current || !Number.isFinite(duration) || duration <= 0) return;
            const t0 = video.currentTime;
            const resolved = resolveSegmentPauseState(
                t0,
                duration,
                chapterBoundaries,
                pickedChapterSegment,
                pickedSecondDotPausedRef.current,
            );
            if (resolved == null) return;

            const { t, segmentEnd } = resolved;
            if (t !== t0) {
                video.currentTime = t;
            }

            const effectiveT = t;

            if (
                playToSegmentEndAfterAutoplayOffRef.current
                && effectiveT < segmentEnd - SEGMENT_END_EPS
            ) {
                return;
            }
            if (
                playToSegmentEndAfterAutoplayOffRef.current
                && effectiveT >= segmentEnd - SEGMENT_END_EPS
            ) {
                playToSegmentEndAfterAutoplayOffRef.current = false;
            }

            if (effectiveT >= segmentEnd - SEGMENT_END_EPS) {
                const clamped = Math.min(segmentEnd, duration);
                video.currentTime = clamped;
                video.pause();
                if (
                    pickedChapterSegment?.endExclusiveSeconds != null
                    && !pickedSecondDotPausedRef.current
                    && Math.abs(clamped - Math.min(pickedChapterSegment.endExclusiveSeconds, duration)) < 0.05
                ) {
                    pickedSecondDotPausedRef.current = true;
                }
            }
        },
        [duration, chapterBoundaries, pickedChapterSegment],
    );

    const handleTimeUpdate = useCallback(() => {
        if (isSeeking) return;
        const video = videoRef.current;
        if (!video) return;
        enforceSegmentPause(video);
        setCurrentTime(video.currentTime);
    }, [isSeeking, enforceSegmentPause]);

    const handleSeeked = useCallback(() => {
        const video = videoRef.current;
        if (!video) return;
        enforceSegmentPause(video);
        setCurrentTime(video.currentTime);
    }, [enforceSegmentPause]);

    /** Segment mode on: enforce boundaries (deferred until next dot if user just turned autoplay off while playing). */
    useEffect(() => {
        if (fullVideoMode) return;
        const video = videoRef.current;
        if (!video || !Number.isFinite(duration) || duration <= 0) return;
        enforceSegmentPause(video);
        setCurrentTime(video.currentTime);
    }, [fullVideoMode, duration, chapterBoundaries, enforceSegmentPause]);

    const handleLoadedMetadata = useCallback(() => {
        const video = videoRef.current;
        if (video && Number.isFinite(video.duration)) setDuration(video.duration);
    }, []);

    const handlePlaying = useCallback(() => {
        const video = videoRef.current;
        if (!video) return;
        enforceSegmentPause(video);
        setCurrentTime(video.currentTime);
    }, [enforceSegmentPause]);

    const handleVideoEnded = useCallback(() => {
        playToSegmentEndAfterAutoplayOffRef.current = false;
        setIsPlaying(false);
        setShowControls(true);
    }, []);

    const handleSeekBarInteraction = useCallback((clientX: number) => {
        const bar = seekBarRef.current;
        const video = videoRef.current;
        if (!bar || !video || !duration) return;
        const rect = bar.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const time = ratio * duration;
        playToSegmentEndAfterAutoplayOffRef.current = false;
        video.currentTime = time;
        setCurrentTime(time);
    }, [duration]);

    const handleSeekPointerDown = useCallback((e: React.PointerEvent) => {
        setIsSeeking(true);
        handleSeekBarInteraction(e.clientX);
        const onMove = (ev: PointerEvent) => handleSeekBarInteraction(ev.clientX);
        const onUp = () => {
            setIsSeeking(false);
            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerup', onUp);
        };
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
    }, [handleSeekBarInteraction]);

    const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

    return (
        <div
            ref={chromeRootRef}
            className="vbp-overlay"
            onMouseMove={resetControlsTimer}
            onFocusCapture={onChromeFocusCapture}
            onBlurCapture={onChromeBlurCapture}
        >
            <div className="vbp-video-area" onClick={handleVideoAreaTap}>
                <video
                    ref={videoRef}
                    src={resolvedSource}
                    autoPlay={initialFullVideoAutoplay}
                    muted={muted}
                    onVolumeChange={(e) => setMuted((e.currentTarget as HTMLVideoElement).muted)}
                    onPlay={() => { setIsPlaying(true); resetControlsTimer(); }}
                    onPlaying={handlePlaying}
                    onPause={() => { setIsPlaying(false); resetControlsTimer(); }}
                    onEnded={handleVideoEnded}
                    onTimeUpdate={handleTimeUpdate}
                    onSeeked={handleSeeked}
                    onLoadedMetadata={handleLoadedMetadata}
                    playsInline
                    crossOrigin="anonymous"
                >
                    {hasCaptions && (
                        <track
                            key={`${captionLang}:${resolvedCaptionsUrl}`}
                            kind="subtitles"
                            src={resolvedCaptionsUrl}
                            srcLang={captionLang}
                            label={captionLang.toUpperCase()}
                        />
                    )}
                </video>

                {captionsOn && activeCueText && (
                    <div
                        className={`vbp-captions${chromeVisible ? ' vbp-captions--with-controls' : ''}`}
                        data-caption-size={captionSizeIndex}
                        aria-live="polite"
                        aria-atomic="true"
                    >
                        <div className="vbp-caption-chip">
                            {activeCueText.split('\n').map((line, i) => (
                                <span key={i} className="vbp-caption-line">{line}</span>
                            ))}
                        </div>
                    </div>
                )}

                {!isPlaying && (
                    <div className="vbp-big-play" aria-hidden>
                        <svg viewBox="0 0 48 48" width="48" height="48" fill="none">
                            <polygon points="16,10 38,24 16,38" fill="white" />
                        </svg>
                    </div>
                )}
            </div>

            {/* Top bar */}
            <div className={`vbp-top-bar ${chromeVisible && !topBarHidden ? 'vbp-visible' : ''}`} aria-hidden={topBarHidden ? true : undefined}>
                <div className="vbp-top-bar-right">
                    <PanelCloseButton
                        className="vbp-close-btn vbp-top-bar-close"
                        onClick={(e) => { e.stopPropagation(); onClose(); }}
                    />
                    <MediaSettingsButton
                        onClick={handleOpenSettings}
                        ariaLabel={t('videobook.openSettings', 'Open Video Book settings')}
                    />
                    <button
                        type="button"
                        className="vbook-floating-btn vbook-floating-btn--videobook vbook-floating-btn--videobook-inline"
                        onClick={(e) => { e.stopPropagation(); onBack(); }}
                        aria-label={t('videobook.openChapters')}
                        title={t('videobook.openChapters')}
                    >
                        <VideoBookFloatingChipIcon />
                        <span className="vbook-floating-btn-label" aria-hidden="true">
                            {t('videobook.chaptersLabel', 'Chapters')}
                        </span>
                    </button>
                </div>
            </div>

            {/* Bottom controls */}
            <div className={`vbp-controls ${chromeVisible ? 'vbp-visible' : ''}`} onClick={(e) => e.stopPropagation()}>
                {/* Seek bar */}
                <div className="vbp-seek-row">
                    <div className="vbp-seek-dot-left" aria-hidden />
                    <div
                        className="vbp-seek-bar"
                        ref={seekBarRef}
                        onPointerDown={handleSeekPointerDown}
                        role="slider"
                        aria-valuemin={0}
                        aria-valuemax={duration}
                        aria-valuenow={currentTime}
                        aria-valuetext={t('common.mediaSeekPosition', {
                            current: formatTime(currentTime),
                            total: formatTime(duration),
                        })}
                        aria-label={t('videobook.seek')}
                        tabIndex={0}
                    >
                        <div className="vbp-seek-track" />
                        <div className="vbp-seek-fill" style={{ width: `${progress}%` }} />
                        <div className="vbp-seek-thumb" style={{ left: `${progress}%` }} />
                        {duration > 0 && entry.chapters.map((ch) => {
                            const pos = (ch.timestampSeconds / duration) * 100;
                            return (
                                <div
                                    key={ch.id}
                                    className={`vbp-chapter-dot${sortedChapters[activeChapterIndex]?.id === ch.id ? ' vbp-chapter-dot--active' : ''}`}
                                    style={{ left: `${pos}%` }}
                                    aria-hidden
                                />
                            );
                        })}
                    </div>
                </div>

                <div className="vbp-time-row">
                    <span className="vbp-time">{formatTime(currentTime)}</span>
                    <span className="vbp-time">{formatTime(duration)}</span>
                </div>

                {/* Transport buttons */}
                <div className="vbp-transport">
                    <MediaMuteButton
                        className="vbp-transport-btn"
                        muted={muted}
                        onClick={(e) => {
                            e.stopPropagation();
                            toggleMuted();
                        }}
                        ariaLabel={muted ? t('videobook.unmute') : t('videobook.mute')}
                    />

                    <button
                        type="button"
                        className="vbp-ctrl-btn vbp-ctrl-btn--md"
                        onClick={skipPrev}
                        aria-label={t('videobook.previousChapter')}
                        title={t('videobook.previousChapter')}
                    >
                        <svg viewBox="0 0 24 24" width="26" height="26" fill="none" aria-hidden>
                            <path d="M19 20L9 12l10-8v16z" fill="currentColor" />
                            <rect x="5" y="5" width="2.5" height="14" rx="1" fill="currentColor" />
                        </svg>
                    </button>

                    <MediaPlayPauseButton
                        className="vbp-transport-btn"
                        isPlaying={isPlaying}
                        onClick={togglePlayPause}
                        ariaLabel={isPlaying ? t('video.pause') : t('video.play')}
                    />

                    <button
                        type="button"
                        className="vbp-ctrl-btn vbp-ctrl-btn--md"
                        onClick={skipNext}
                        aria-label={t('videobook.nextChapter')}
                        title={t('videobook.nextChapter')}
                    >
                        <svg viewBox="0 0 24 24" width="26" height="26" fill="none" aria-hidden>
                            <path d="M5 4l10 8-10 8V4z" fill="currentColor" />
                            <rect x="16.5" y="5" width="2.5" height="14" rx="1" fill="currentColor" />
                        </svg>
                    </button>

                    <MediaCaptionsButton
                        className="vbp-transport-btn"
                        captionsOn={captionsOn}
                        hasCaptions={hasCaptions}
                        onClick={toggleCaptions}
                        ariaLabel={captionsOn ? t('videobook.captionsHide') : t('videobook.captionsShow')}
                        title={t('videobook.captionsLabel')}
                    />
                </div>
            </div>
        </div>
    );
};

export default VideoBookPlayer;
