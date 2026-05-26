import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSpatialSound, useVideoBookSettings } from '../../contexts';
import { sendMessage } from '../../messaging';
import { requestOrientationPermission, useDeviceOrientation, isDeviceOrientationSupported } from '../../hooks/useDeviceOrientation';
import PanelCloseButton from '../../../cu/controls/PanelCloseButton';
import {
    MediaSettingsButton,
    MediaMuteButton,
    MediaCaptionsButton,
    MediaPlayPauseButton,
} from '../../../cu/controls/MediaPlayerControls';
import VideoBookSettingsPanel from '../../../cu/videobook/VideoBookSettingsPanel';
import headphonesSvg from '@icons/map-markers/headphones.svg';
import { useControlsAutoHide } from '../../hooks/useControlsAutoHide';
import { useAmbisonicPlayer } from './useAmbisonicPlayer';
import './SpatialSoundOverlay.css';

const nucleusSoundModules: Record<string, string> = {};
const rawNucleusSounds = import.meta.glob(
    '@nucleus-sounds/**/*.{wav,mp3,ogg,flac,vtt}',
    { eager: true, import: 'default' },
);
for (const [path, url] of Object.entries(rawNucleusSounds)) {
    const filename = path.split('/').pop();
    if (filename) nucleusSoundModules[filename] = url as string;
}

function resolveSoundSource(source: string): string {
    if (!source) return source;
    if (source.startsWith('http://') || source.startsWith('https://')) return source;
    return nucleusSoundModules[source] || source;
}

function formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

const KIT_SENSITIVITY = 0.15;

/** Intro-only: swipe cue beside onboarding copy (Figma handset + arrows). */
const SspIntroSwipeIcon: React.FC<{ className?: string }> = ({ className }) => (
    <svg
        className={className}
        xmlns="http://www.w3.org/2000/svg"
        width="36"
        height="64"
        viewBox="0 0 36 64"
        fill="none"
        aria-hidden
    >
        <path
            d="M11.7545 38.9163C11.7545 37.082 12.4832 35.3228 13.7802 34.0257C15.0773 32.7287 16.8365 32 18.6708 32C20.5051 32 22.2643 32.7287 23.5613 34.0257C24.8584 35.3228 25.5871 37.082 25.5871 38.9163C25.5871 39.222 25.4656 39.5152 25.2495 39.7314C25.0333 39.9476 24.7401 40.069 24.4344 40.069C24.1286 40.069 23.8354 39.9476 23.6193 39.7314C23.4031 39.5152 23.2816 39.222 23.2816 38.9163C23.2816 37.6934 22.7959 36.5206 21.9312 35.6559C21.0665 34.7912 19.8937 34.3054 18.6708 34.3054C17.4479 34.3054 16.2751 34.7912 15.4104 35.6559C14.5457 36.5206 14.0599 37.6934 14.0599 38.9163C14.0599 39.222 13.9385 39.5152 13.7223 39.7314C13.5061 39.9476 13.2129 40.069 12.9072 40.069C12.6015 40.069 12.3083 39.9476 12.0921 39.7314C11.8759 39.5152 11.7545 39.222 11.7545 38.9163ZM32.3924 46.9853C31.1518 47.0429 30.1979 48.1121 30.1979 49.3527V50.4017C30.2019 50.6992 30.0932 50.9871 29.8935 51.2077C29.6938 51.4282 29.418 51.5649 29.1216 51.5904C28.9639 51.6009 28.8058 51.5788 28.657 51.5256C28.5082 51.4724 28.3719 51.3891 28.2567 51.281C28.1414 51.1729 28.0496 51.0423 27.987 50.8972C27.9243 50.7521 27.8922 50.5957 27.8925 50.4377V47.0501C27.8925 45.8095 26.9386 44.7447 25.698 44.6828C25.3863 44.6677 25.0748 44.7162 24.7823 44.8251C24.4899 44.934 24.2226 45.1012 23.9967 45.3165C23.7708 45.5318 23.5909 45.7907 23.468 46.0776C23.3451 46.3644 23.2817 46.6732 23.2816 46.9853V49.2518C23.2857 49.5493 23.1769 49.8373 22.9772 50.0578C22.7775 50.2784 22.5017 50.4151 22.2053 50.4406C22.0476 50.451 21.8895 50.429 21.7407 50.3758C21.5919 50.3225 21.4556 50.2393 21.3404 50.1312C21.2251 50.0231 21.1333 49.8924 21.0707 49.7474C21.008 49.6023 20.9759 49.4459 20.9762 49.2879V38.9811C20.9762 37.7405 20.0223 36.6757 18.7817 36.6137C18.47 36.5987 18.1585 36.6472 17.866 36.7561C17.5736 36.865 17.3063 37.0322 17.0804 37.2475C16.8545 37.4628 16.6746 37.7217 16.5517 38.0085C16.4288 38.2954 16.3654 38.6042 16.3654 38.9163V56.1696C16.3689 56.4484 16.2735 56.7194 16.0963 56.9346C15.9191 57.1498 15.6713 57.2953 15.3971 57.3453H15.3798C15.2078 57.3646 15.034 57.3327 14.8802 57.2534C14.7264 57.1742 14.5994 57.0513 14.5152 56.9001L11.4894 51.6495C10.8698 50.5746 9.50957 50.1265 8.40585 50.6956C8.12694 50.8375 7.87984 51.0346 7.67957 51.275C7.4793 51.5154 7.33007 51.7941 7.24097 52.094C7.15186 52.394 7.12474 52.7089 7.16127 53.0197C7.19779 53.3304 7.29719 53.6305 7.45341 53.9016L11.913 62.5542C12.0147 62.7275 12.16 62.8712 12.3344 62.971C12.5088 63.0708 12.7063 63.1234 12.9072 63.1233H32.5034C32.7175 63.1235 32.9275 63.064 33.1097 62.9515C33.2919 62.839 33.4392 62.678 33.5351 62.4865C33.5869 62.3827 34.8088 60.3165 34.8088 56.6292V49.2907C34.8092 48.9784 34.7461 48.6693 34.6233 48.3821C34.5006 48.0949 34.3208 47.8356 34.0948 47.62C33.8688 47.4044 33.6014 47.237 33.3088 47.1279C33.0161 47.0188 32.7044 46.9703 32.3924 46.9853Z"
            fill="currentColor"
        />
        <path
            d="M31.9205 27.8944L27.8975 31.9494C27.835 32.0125 27.7553 32.0554 27.6685 32.0728C27.5818 32.0903 27.4919 32.0813 27.4101 32.0472C27.3284 32.0131 27.2586 31.9553 27.2095 31.8811C27.1604 31.8069 27.1342 31.7198 27.1342 31.6306V28.0262H21.7702C21.6517 28.0262 21.538 27.9787 21.4542 27.8942C21.3703 27.8097 21.3232 27.6951 21.3232 27.5756C21.3232 27.4561 21.3703 27.3415 21.4542 27.257C21.538 27.1725 21.6517 27.1251 21.7702 27.1251H27.1342V23.5206C27.1342 23.4314 27.1604 23.3443 27.2095 23.2701C27.2586 23.196 27.3284 23.1381 27.4101 23.104C27.4919 23.0699 27.5818 23.061 27.6685 23.0784C27.7553 23.0958 27.835 23.1388 27.8975 23.2018L31.9205 27.2568C31.9621 27.2987 31.995 27.3484 32.0175 27.4031C32.04 27.4578 32.0516 27.5164 32.0516 27.5756C32.0516 27.6348 32.04 27.6934 32.0175 27.7481C31.995 27.8028 31.9621 27.8525 31.9205 27.8944Z"
            fill="currentColor"
        />
        <path
            d="M3.85197 27.2569L7.87497 23.2019C7.93748 23.1388 8.01716 23.0958 8.10392 23.0784C8.19067 23.061 8.2806 23.0699 8.36233 23.104C8.44405 23.1382 8.51389 23.196 8.563 23.2701C8.61211 23.3443 8.63829 23.4315 8.63822 23.5206L8.63822 27.1251L14.0022 27.1251C14.1208 27.1251 14.2345 27.1725 14.3183 27.257C14.4021 27.3415 14.4492 27.4561 14.4492 27.5756C14.4492 27.6951 14.4021 27.8097 14.3183 27.8942C14.2345 27.9787 14.1208 28.0262 14.0022 28.0262L8.63822 28.0262L8.63822 31.6306C8.63829 31.7198 8.61211 31.807 8.563 31.8811C8.51389 31.9553 8.44405 32.0131 8.36232 32.0472C8.2806 32.0814 8.19067 32.0903 8.10392 32.0729C8.01716 32.0555 7.93748 32.0125 7.87497 31.9494L3.85197 27.8944C3.81041 27.8526 3.77743 27.8029 3.75494 27.7482C3.73244 27.6935 3.72087 27.6348 3.72087 27.5756C3.72087 27.5164 3.73244 27.4578 3.75494 27.4031C3.77743 27.3484 3.81041 27.2987 3.85197 27.2569Z"
            fill="currentColor"
        />
        <rect x="1" y="1" width="33.7209" height="62" rx="5" stroke="currentColor" strokeWidth="2" />
    </svg>
);

function SspHeadphoneRings({ playing }: { playing: boolean }): React.ReactElement {
    const playCls = playing ? ' ssp-ring--playing' : '';
    return (
        <div className="ssp-rings">
            <div className={`ssp-ring ssp-ring--4${playCls}`} />
            <div className={`ssp-ring ssp-ring--3${playCls}`} />
            <div className={`ssp-ring ssp-ring--2${playCls}`} />
            <div className={`ssp-ring ssp-ring--1${playCls}`} />
            <img className="ssp-icon" src={headphonesSvg} alt="" draggable={false} aria-hidden />
        </div>
    );
}

/** Chrome auto-hide timeout — matches videobook + 360 overlays. */
const SSP_CONTROLS_AUTO_HIDE_MS = 3000;

/** Cinematic intro dwell before main audio — mirrors `Video360Overlay` `INTRO_DWELL_MS` (4 s). */
const SSP_INTRO_DWELL_MS = 4000;

type Phase = 'intro' | 'player';

const SpatialSoundOverlayInner: React.FC = () => {
    const { t } = useTranslation();
    const spatialSound = useSpatialSound();
    const entry = spatialSound.entry!;
    const seekBarRef = useRef<HTMLDivElement>(null);

    const resolvedSource = resolveSoundSource(entry.soundUrl);
    const resolvedCaptions = entry.captionsUrl ? resolveSoundSource(entry.captionsUrl) : undefined;

    // Session-scoped prefs shared with videobook + 360 (mute, captions, size).
    // Ignores autoplay + speed (no chapters, no rate-changing here).
    const {
        muted, setMuted,
        captionsOn, setCaptionsOn,
        captionSizeIndex,
    } = useVideoBookSettings();

    // Every open starts on the cinematic intro; main audio waits for player phase.
    const [phase, setPhase] = useState<Phase>('intro');
    const [settingsOpen, setSettingsOpen] = useState(false);
    const {
        chromeVisible,
        chromeRootRef,
        resetControlsTimer,
        onChromeFocusCapture,
        onChromeBlurCapture,
    } = useControlsAutoHide(SSP_CONTROLS_AUTO_HIDE_MS);

    const player = useAmbisonicPlayer();
    const {
        load, play, pause, seek, setRotation,
        setMuted: setPlayerMuted,
        isPlaying, currentTime, duration, isReady,
        hasCaptions, activeCueText,
    } = player;

    const listenerYawRef = useRef(0);
    const listenerPitchRef = useRef(0);

    // Changing clip or listen spot replays the intro from the beginning.
    const mediaSessionKey = `${entry.primPath ?? ''}|${resolvedSource}`;

    useEffect(() => {
        setPhase('intro');
        pause();
        listenerYawRef.current = 0;
        listenerPitchRef.current = 0;
    }, [mediaSessionKey, pause]);

    // Preload during intro; playback is gated on `phase === 'player' && isReady`.
    useEffect(() => {
        load(resolvedSource, resolvedCaptions).catch((err) => {
            console.warn('[SpatialSoundOverlay] load failed:', err);
        });
    }, [resolvedSource, resolvedCaptions, load]);

    useEffect(() => {
        if (phase === 'intro') pause();
    }, [phase, pause]);

    useEffect(() => {
        setPlayerMuted(muted);
    }, [muted, resolvedSource, setPlayerMuted]);

    const toggleMuted = useCallback(() => {
        const next = !muted;
        setPlayerMuted(next);
        setMuted(next);
    }, [muted, setMuted, setPlayerMuted]);

    const toggleCaptions = useCallback(() => {
        if (!hasCaptions) return;
        setCaptionsOn(!captionsOn);
    }, [captionsOn, hasCaptions, setCaptionsOn]);

    const handleOpenSettings = useCallback(() => {
        setSettingsOpen(true);
    }, []);

    const handleCloseSettings = useCallback(() => {
        setSettingsOpen(false);
        resetControlsTimer();
    }, [resetControlsTimer]);

    const updateListenerOrientation = useCallback((dYaw: number, dPitch: number) => {
        listenerYawRef.current += dYaw;
        listenerPitchRef.current = Math.max(-89, Math.min(89, listenerPitchRef.current + dPitch));
        setRotation(listenerYawRef.current, listenerPitchRef.current);
    }, [setRotation]);

    // Device orientation drives listener rotation once the player phase is active
    const orientationSupported = isDeviceOrientationSupported();
    useDeviceOrientation(phase === 'player' && isPlaying, updateListenerOrientation);

    // Drag-to-look -> Kit camera + spatial audio listener
    const dragActive = useRef(false);
    const dragMoved = useRef(false);
    const lastPointer = useRef({ x: 0, y: 0 });

    const handleVisDragDown = useCallback((e: React.PointerEvent) => {
        if (phase !== 'player' || e.button !== 0) return;
        dragActive.current = true;
        dragMoved.current = false;
        lastPointer.current = { x: e.clientX, y: e.clientY };
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    }, [phase]);

    const handleVisDragMove = useCallback((e: React.PointerEvent) => {
        if (!dragActive.current) return;
        const dx = e.clientX - lastPointer.current.x;
        const dy = e.clientY - lastPointer.current.y;
        lastPointer.current = { x: e.clientX, y: e.clientY };
        if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
            dragMoved.current = true;
            // Rotate Kit camera + audio listener in lockstep so what the
            // user sees and hears stay aligned. exit_xform_view restores
            // the saved camera local pose verbatim, so any in-overlay
            // rotation is wiped on close — no leak risk.
            sendMessage('touchLookDelta', { dx, dy });
            updateListenerOrientation(-dx * KIT_SENSITIVITY, -(dy * KIT_SENSITIVITY));
        }
    }, [updateListenerOrientation]);

    const handleVisDragUp = useCallback(() => {
        dragActive.current = false;
    }, []);

    /** Tap (not drag) wakes the chrome. */
    const handleVisualizationTap = useCallback(() => {
        if (phase !== 'player') return;
        if (dragMoved.current) return;
        resetControlsTimer();
    }, [phase, resetControlsTimer]);

    useEffect(() => {
        sendMessage('movementInputControl', { enabled: false });
        return () => { sendMessage('movementInputControl', { enabled: true }); };
    }, []);

    const handleClose = useCallback(() => {
        pause();
        spatialSound.close();
    }, [spatialSound, pause]);

    const togglePlayPause = useCallback(() => {
        if (isPlaying) {
            pause();
        } else {
            void play();
        }
    }, [isPlaying, pause, play]);

    // Cinematic intro dwell — auto-advance to player (mirrors `Video360Overlay`).
    useEffect(() => {
        if (phase !== 'intro' || settingsOpen) return;
        const id = window.setTimeout(() => setPhase('player'), SSP_INTRO_DWELL_MS);
        return () => window.clearTimeout(id);
    }, [phase, settingsOpen]);

    // Main audio starts only after intro finishes and the buffer is ready.
    useEffect(() => {
        if (phase !== 'player' || !isReady) return;

        let cancelled = false;

        (async () => {
            if (orientationSupported) {
                await requestOrientationPermission();
            }
            if (cancelled) return;
            await play();
        })();

        return () => {
            cancelled = true;
        };
    }, [phase, isReady, orientationSupported, play]);

    // Teleport exit: `context.close()` only — no unmount cleanup (StrictMode).

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') handleClose();
            else if (phase === 'player' && (e.key === ' ' || e.key === 'k')) {
                e.preventDefault();
                togglePlayPause();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    });

    const handleSeekBarInteraction = useCallback((clientX: number) => {
        const bar = seekBarRef.current;
        if (!bar || !duration) return;
        const rect = bar.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const time = ratio * duration;
        seek(time);
    }, [duration, seek]);

    const handleSeekPointerDown = useCallback((e: React.PointerEvent) => {
        handleSeekBarInteraction(e.clientX);
        const onMove = (ev: PointerEvent) => handleSeekBarInteraction(ev.clientX);
        const onUp = () => {
            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerup', onUp);
        };
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
    }, [handleSeekBarInteraction]);

    const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

    const playerChromeVisible = phase === 'player' && chromeVisible && !settingsOpen;
    const topBarVisible = (phase === 'intro' && !settingsOpen) || playerChromeVisible;

    return (
        <div
            ref={chromeRootRef}
            className={`ssp-overlay ssp-overlay--${phase}`}
            onMouseMove={phase === 'player' ? resetControlsTimer : undefined}
            onFocusCapture={phase === 'player' ? onChromeFocusCapture : undefined}
            onBlurCapture={phase === 'player' ? onChromeBlurCapture : undefined}
        >
            {/* Top bar — visible in intro (unless settings modal); auto-hides with chrome in player. */}
            <div
                className={`ssp-top-bar${topBarVisible ? ' ssp-top-bar--visible' : ''}`}
            >
                <div className="ssp-top-bar-right">
                    <PanelCloseButton
                        className="ssp-close-btn"
                        title={t('common.close')}
                        onClick={(e) => { e.stopPropagation(); handleClose(); }}
                    />
                    <MediaSettingsButton
                        onClick={(e) => { e.stopPropagation(); handleOpenSettings(); }}
                        ariaLabel={t('spatialSound.openSettings', 'Open audio settings')}
                        title={t('spatialSound.openSettings', 'Open audio settings')}
                    />
                </div>
            </div>

            {/* Title block — intro only; hidden during playback. */}
            {phase === 'intro' && (
                <div className="ssp-header ssp-header--intro-center">
                    <span className="ssp-label">{t('spatialSound.label')}</span>
                    <h1 className="ssp-title">{t(entry.soundTitle) || t(entry.title)}</h1>
                </div>
            )}

            {/* Intro splash or player visualization. Click toggles chrome (drag is
                guarded by `dragMoved` so slow rotations don't keep flashing the UI). */}
            <div
                className={`ssp-visualization${
                    phase === 'player' ? ' ssp-visualization--draggable' : ''
                }${phase === 'intro' ? ' ssp-visualization--intro' : ''}`}
                onClick={handleVisualizationTap}
                onPointerDown={handleVisDragDown}
                onPointerMove={handleVisDragMove}
                onPointerUp={handleVisDragUp}
                onPointerCancel={handleVisDragUp}
            >
                {phase === 'intro' && (
                    <div className="ssp-onboarding-hint">
                        <SspIntroSwipeIcon className="ssp-intro-swipe-icon" />
                        <p className="ssp-onboarding-desc">
                            {orientationSupported
                                ? t('spatialSound.onboarding.description')
                                : t('spatialSound.onboarding.descriptionDesktop')}
                        </p>
                    </div>
                )}
                {phase === 'player' && <SspHeadphoneRings playing={isPlaying} />}

                {phase === 'player' && hasCaptions && captionsOn && activeCueText && (
                    <div
                        className={`ssp-captions${playerChromeVisible ? ' ssp-captions--with-controls' : ''}`}
                        role="status"
                        aria-live="polite"
                        data-caption-size={captionSizeIndex}
                    >
                        {activeCueText.split('\n').map((line, i) => (
                            <span key={i} className="ssp-caption-line">{line}</span>
                        ))}
                    </div>
                )}
            </div>

            {/* Bottom controls — player phase only, auto-fades. */}
            {phase === 'player' && <div
                className={`ssp-controls${playerChromeVisible ? ' ssp-controls--visible' : ''}`}
                onClick={(e) => e.stopPropagation()}
            >
                <div className="ssp-seek-row">
                    <div
                        className="ssp-seek-bar"
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
                        aria-label={t('spatialSound.seek')}
                        tabIndex={0}
                    >
                        <div className="ssp-seek-track" />
                        <div className="ssp-seek-fill" style={{ width: `${progress}%` }} />
                        <div className="ssp-seek-thumb" style={{ left: `${progress}%` }} />
                    </div>
                </div>

                <div className="ssp-time-row">
                    <span className="ssp-time">{formatTime(currentTime)}</span>
                    <span className="ssp-time">{formatTime(duration)}</span>
                </div>

                <div className="ssp-transport">
                    <MediaMuteButton
                        className="ssp-transport-btn"
                        muted={muted}
                        onClick={(e) => { e.stopPropagation(); toggleMuted(); resetControlsTimer(); }}
                        ariaLabel={muted ? t('spatialSound.unmute', 'Unmute') : t('spatialSound.mute', 'Mute')}
                    />

                    <MediaPlayPauseButton
                        className="ssp-transport-btn"
                        isPlaying={isPlaying}
                        onClick={togglePlayPause}
                        ariaLabel={isPlaying ? t('video.pause') : t('video.play')}
                    />

                    <MediaCaptionsButton
                        className="ssp-transport-btn"
                        captionsOn={captionsOn}
                        hasCaptions={hasCaptions}
                        onClick={(e) => { e.stopPropagation(); toggleCaptions(); resetControlsTimer(); }}
                        ariaLabel={captionsOn ? t('spatialSound.hideCaptions') : t('spatialSound.showCaptions')}
                        title={t('spatialSound.captions')}
                    />
                </div>
            </div>}

            {/* Captions card only — no autoplay/speed. */}
            {settingsOpen && (
                <VideoBookSettingsPanel
                    onClose={handleCloseSettings}
                    showAutoplay={false}
                    showPlaybackSpeed={false}
                    titleKey="spatialSound.settingsTitle"
                />
            )}
        </div>
    );
};

const SpatialSoundOverlay: React.FC = () => {
    const spatialSound = useSpatialSound();
    if (!spatialSound.isOpen || !spatialSound.entry) return null;
    return <SpatialSoundOverlayInner />;
};

export default SpatialSoundOverlay;
