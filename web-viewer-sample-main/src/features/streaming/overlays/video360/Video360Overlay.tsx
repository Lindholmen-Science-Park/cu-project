import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useVideo360, useVideoBookSettings } from '../../contexts';
import { sendMessage } from '../../messaging';
import {
    requestOrientationPermission,
    useDeviceOrientation,
    isDeviceOrientationSupported,
} from '../../hooks/useDeviceOrientation';
import PanelCloseButton from '../../../cu/controls/PanelCloseButton';
import {
    MediaSettingsButton,
    MediaMuteButton,
    MediaCaptionsButton,
    MediaPlayPauseButton,
} from '../../../cu/controls/MediaPlayerControls';
import VideoBookSettingsPanel from '../../../cu/videobook/VideoBookSettingsPanel';
import { PLAYBACK_SPEED_STEPS } from '../../../cu/videobook/videoBookSettings';
import { useControlsAutoHide } from '../../hooks/useControlsAutoHide';
import { useVideoSphere } from './useVideoSphere';
import './Video360Overlay.css';

/** Resolves a filename to its Vite-bundled URL via `@nucleus-videos`. */
const nucleusVideoModules: Record<string, string> = {};
const rawNucleusVideos = import.meta.glob(
    '@nucleus-videos/*.{mp4,webm,mov,vtt}',
    { eager: true, import: 'default' },
);
for (const [path, url] of Object.entries(rawNucleusVideos)) {
    const filename = path.split('/').pop();
    if (filename) nucleusVideoModules[filename] = url as string;
}

function resolveVideoSource(source: string): string {
    if (!source) return source;
    if (source.startsWith('http://') || source.startsWith('https://')) return source;
    return nucleusVideoModules[source] || source;
}

function formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/** Degrees per CSS pixel — calibrated to match SpatialSoundOverlay's feel. */
const DRAG_SENSITIVITY = 0.15;

/** Chrome auto-hide timeout — matches videobook + spatial sound. */
const V360_CONTROLS_AUTO_HIDE_MS = 3000;

/** Cinematic intro dwell before the sphere mounts. */
const INTRO_DWELL_MS = 3500;

type Phase = 'intro' | 'player';

/** Swipe-to-look phone gesture glyph (35.721 × 64). Off-white, currentColor. */
function IntroSwipePhoneIcon() {
    return (
        <svg
            className="v360-intro-helper-icon v360-intro-helper-icon--swipe"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 36 64"
            fill="none"
            aria-hidden
        >
            <path d="M10.9057 38.0248C10.9057 36.1229 11.6612 34.2989 13.006 32.9541C14.3508 31.6093 16.1748 30.8538 18.0767 30.8538C19.9786 30.8538 21.8025 31.6093 23.1474 32.9541C24.4922 34.2989 25.2477 36.1229 25.2477 38.0248C25.2477 38.3418 25.1218 38.6458 24.8977 38.8699C24.6735 39.094 24.3695 39.2199 24.0525 39.2199C23.7356 39.2199 23.4316 39.094 23.2074 38.8699C22.9833 38.6458 22.8574 38.3418 22.8574 38.0248C22.8574 36.7569 22.3537 35.5409 21.4571 34.6443C20.5606 33.7478 19.3446 33.2441 18.0767 33.2441C16.8088 33.2441 15.5928 33.7478 14.6962 34.6443C13.7997 35.5409 13.296 36.7569 13.296 38.0248C13.296 38.3418 13.1701 38.6458 12.946 38.8699C12.7218 39.094 12.4178 39.2199 12.1008 39.2199C11.7839 39.2199 11.4799 39.094 11.2557 38.8699C11.0316 38.6458 10.9057 38.3418 10.9057 38.0248ZM32.3037 46.391C31.0174 46.4507 30.0284 47.5592 30.0284 48.8455V49.9332C30.0325 50.2416 29.9198 50.5402 29.7127 50.7688C29.5057 50.9975 29.2197 51.1393 28.9124 51.1657C28.7489 51.1765 28.5849 51.1536 28.4307 51.0985C28.2764 51.0433 28.1351 50.957 28.0156 50.8449C27.8961 50.7328 27.8009 50.5973 27.736 50.4469C27.671 50.2965 27.6377 50.1343 27.6381 49.9705V46.4582C27.6381 45.1719 26.649 44.0679 25.3627 44.0036C25.0396 43.988 24.7166 44.0383 24.4133 44.1512C24.1101 44.2641 23.833 44.4375 23.5987 44.6607C23.3645 44.8839 23.178 45.1524 23.0506 45.4498C22.9231 45.7472 22.8574 46.0674 22.8574 46.391V48.741C22.8615 49.0494 22.7487 49.348 22.5417 49.5766C22.3347 49.8053 22.0487 49.9471 21.7414 49.9735C21.5779 49.9843 21.4139 49.9615 21.2597 49.9063C21.1054 49.8511 20.9641 49.7648 20.8446 49.6527C20.7251 49.5406 20.6299 49.4052 20.565 49.2547C20.5 49.1043 20.4667 48.9422 20.467 48.7783V38.092C20.467 36.8057 19.478 35.7017 18.1917 35.6374C17.8685 35.6219 17.5455 35.6721 17.2423 35.785C16.9391 35.898 16.662 36.0713 16.4277 36.2945C16.1935 36.5177 16.007 36.7862 15.8795 37.0836C15.7521 37.381 15.6864 37.7012 15.6864 38.0248V55.9135C15.69 56.2025 15.5912 56.4835 15.4074 56.7067C15.2236 56.9298 14.9668 57.0807 14.6824 57.1326H14.6645C14.4862 57.1525 14.306 57.1194 14.1465 57.0373C13.987 56.9551 13.8554 56.8277 13.7681 56.6709L10.6308 51.2269C9.98838 50.1124 8.57808 49.6478 7.43371 50.2379C7.14454 50.385 6.88833 50.5894 6.68068 50.8386C6.47304 51.0879 6.31832 51.3768 6.22593 51.6878C6.13354 51.9988 6.10542 52.3254 6.14329 52.6476C6.18116 52.9698 6.28422 53.2809 6.4462 53.562L11.07 62.5332C11.1755 62.7129 11.3261 62.8619 11.5069 62.9654C11.6878 63.0689 11.8925 63.1234 12.1008 63.1233H32.4187C32.6408 63.1235 32.8585 63.0618 33.0474 62.9452C33.2363 62.8285 33.389 62.6616 33.4884 62.463C33.5422 62.3554 34.8091 60.2131 34.8091 56.3901V48.7813C34.8094 48.4575 34.744 48.137 34.6168 47.8392C34.4895 47.5414 34.3031 47.2726 34.0688 47.0491C33.8345 46.8255 33.5572 46.6519 33.2538 46.5388C32.9504 46.4257 32.6271 46.3754 32.3037 46.391Z" fill="currentColor" />
            <path d="M31.4043 29.4795L27.5328 33.3818C27.4726 33.4425 27.3959 33.4838 27.3125 33.5006C27.229 33.5174 27.1424 33.5088 27.0638 33.4759C26.9851 33.4431 26.9179 33.3874 26.8707 33.3161C26.8234 33.2447 26.7982 33.1608 26.7983 33.075V29.6063H21.6362C21.5221 29.6063 21.4127 29.5606 21.332 29.4793C21.2514 29.398 21.2061 29.2877 21.2061 29.1727C21.2061 29.0577 21.2514 28.9474 21.332 28.8661C21.4127 28.7848 21.5221 28.7391 21.6362 28.7391H26.7983V25.2704C26.7982 25.1846 26.8234 25.1007 26.8707 25.0293C26.9179 24.9579 26.9851 24.9023 27.0638 24.8695C27.1424 24.8366 27.229 24.828 27.3125 24.8448C27.3959 24.8615 27.4726 24.9029 27.5328 24.9636L31.4043 28.8659C31.4443 28.9062 31.476 28.954 31.4977 29.0066C31.5193 29.0593 31.5305 29.1157 31.5305 29.1727C31.5305 29.2297 31.5193 29.2861 31.4977 29.3387C31.476 29.3914 31.4443 29.4392 31.4043 29.4795Z" fill="currentColor" />
            <path d="M4.39255 28.866L8.26409 24.9637C8.32425 24.903 8.40093 24.8616 8.48442 24.8449C8.56791 24.8281 8.65445 24.8367 8.7331 24.8695C8.81174 24.9024 8.87895 24.958 8.92622 25.0294C8.97348 25.1007 8.99867 25.1846 8.9986 25.2704L8.9986 28.7392L14.1607 28.7392C14.2747 28.7392 14.3842 28.7849 14.4648 28.8662C14.5455 28.9475 14.5908 29.0578 14.5908 29.1728C14.5908 29.2878 14.5455 29.3981 14.4648 29.4794C14.3842 29.5607 14.2747 29.6064 14.1607 29.6064L8.9986 29.6064L8.9986 33.0751C8.99867 33.1609 8.97348 33.2448 8.92622 33.3162C8.87895 33.3875 8.81174 33.4432 8.7331 33.476C8.65445 33.5089 8.56791 33.5174 8.48442 33.5007C8.40093 33.4839 8.32425 33.4426 8.26409 33.3819L4.39255 29.4795C4.35256 29.4393 4.32083 29.3914 4.29918 29.3388C4.27753 29.2862 4.26639 29.2298 4.26639 29.1728C4.26639 29.1158 4.27753 29.0594 4.29918 29.0067C4.32083 28.9541 4.35256 28.9063 4.39255 28.866Z" fill="currentColor" />
            <path d="M17.7045 15.593L21.6069 19.4645C21.6676 19.5247 21.7089 19.6014 21.7257 19.6849C21.7425 19.7683 21.7339 19.8549 21.701 19.9335C21.6682 20.0122 21.6125 20.0794 21.5412 20.1267C21.4698 20.1739 21.3859 20.1991 21.3001 20.199L17.8314 20.199L17.8314 25.3611C17.8314 25.4752 17.7857 25.5846 17.7044 25.6653C17.6231 25.7459 17.5128 25.7913 17.3978 25.7913C17.2828 25.7913 17.1725 25.7459 17.0912 25.6653C17.0099 25.5846 16.9642 25.4752 16.9642 25.3611L16.9642 20.199L13.4955 20.199C13.4097 20.1991 13.3258 20.1739 13.2544 20.1267C13.183 20.0794 13.1274 20.0122 13.0945 19.9335C13.0617 19.8549 13.0531 19.7683 13.0699 19.6849C13.0866 19.6014 13.128 19.5247 13.1887 19.4645L17.091 15.593C17.1313 15.553 17.1791 15.5213 17.2317 15.4996C17.2844 15.478 17.3408 15.4668 17.3978 15.4668C17.4548 15.4668 17.5112 15.478 17.5638 15.4996C17.6165 15.5213 17.6643 15.553 17.7045 15.593Z" fill="currentColor" />
            <rect x="1" y="1" width="33.7209" height="62" rx="5" stroke="currentColor" strokeWidth="2" />
        </svg>
    );
}

/** Gyro-mode tap glyph (24 × 24). Lemon, currentColor. */
function IntroGyroIcon() {
    return (
        <svg
            className="v360-intro-helper-icon v360-intro-helper-icon--gyro"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden
        >
            <path d="M11.9617 1.00008C13.2973 0.985712 14.4769 1.7231 15.3923 2.84774C16.3074 3.97198 17.0016 5.52295 17.4421 7.28524C17.5761 7.82099 17.2503 8.36412 16.7146 8.49813C16.1788 8.63207 15.6357 8.30635 15.5017 7.77059C15.1077 6.19446 14.5167 4.93993 13.8416 4.11044C13.1669 3.2816 12.5136 2.99438 11.9832 3.00008C11.4502 3.00599 10.7938 3.31027 10.1199 4.15829C9.44656 5.00565 8.86107 6.27532 8.47535 7.86044C8.09166 9.4374 7.9335 11.2138 8.02515 12.9806C8.1169 14.7487 8.45388 16.4067 8.98121 17.7667C9.51395 19.1406 10.1889 20.0773 10.8582 20.5733C11.4869 21.0393 12.0692 21.0978 12.6218 20.8722C13.1331 20.6634 13.7168 20.9087 13.9255 21.42C14.1343 21.9313 13.889 22.5149 13.3777 22.7237C12.1019 23.2446 10.7878 23.0116 9.66675 22.1807C8.58607 21.3798 7.72695 20.0659 7.11597 18.4903C6.49966 16.901 6.12896 15.0283 6.02808 13.0841C5.92714 11.1383 6.09907 9.16707 6.53199 7.38778C6.96285 5.61704 7.6474 4.05452 8.55347 2.91415C9.45884 1.77475 10.6287 1.01459 11.9617 1.00008ZM14.2947 13.2686C14.5368 12.7722 15.1362 12.5656 15.6326 12.8077L19.446 14.6681C19.9423 14.9101 20.1488 15.5086 19.907 16.005L18.0466 19.8194C17.8045 20.3157 17.2061 20.5214 16.7097 20.2794C16.2134 20.0373 16.0067 19.4389 16.2488 18.9425L17.6707 16.0274L14.7556 14.6056C14.2593 14.3635 14.0527 13.765 14.2947 13.2686Z" fill="currentColor" />
            <path d="M12.5029 6.00529C14.8246 6.06096 17.0759 6.5017 18.9023 7.28459C20.7 8.05521 22.1366 9.18371 22.7236 10.6225C22.9322 11.1338 22.6871 11.7176 22.1758 11.9262C21.6645 12.1346 21.0807 11.8886 20.8721 11.3774C20.5702 10.6381 19.6923 9.79859 18.1152 9.12248C16.5664 8.45854 14.5741 8.05611 12.4551 8.00529C10.3374 7.95451 8.2673 8.25932 6.57909 8.85295C4.86531 9.45558 3.7714 10.2734 3.291 11.058C3.06109 11.4335 2.98166 11.7815 3.00291 12.1C3.02446 12.4216 3.15366 12.7828 3.45018 13.1723C4.06317 13.9774 5.2996 14.7686 7.09666 15.3149C8.87123 15.8542 10.982 16.0893 13.0859 15.9682C15.1937 15.8469 17.1186 15.379 18.5605 14.6723C19.0564 14.4294 19.6554 14.6345 19.8984 15.1303C20.1412 15.6261 19.9362 16.2252 19.4404 16.4682C17.7074 17.3176 15.5102 17.8323 13.2012 17.9653C10.8885 18.0984 8.53902 17.8442 6.51463 17.2289C4.5126 16.6204 2.82721 15.6566 1.85838 14.3842C1.36424 13.7352 1.05947 13.0069 1.0078 12.2328C0.955949 11.4556 1.1643 10.7013 1.58494 10.0141C2.40597 8.67309 3.99315 7.64235 5.916 6.96623C7.86448 6.28111 10.1797 5.94959 12.5029 6.00529Z" fill="currentColor" />
        </svg>
    );
}

const Video360OverlayInner: React.FC = () => {
    const { t } = useTranslation();
    const video360 = useVideo360();
    const entry = video360.entry!;
    const seekBarRef = useRef<HTMLDivElement>(null);
    const sphereContainerRef = useRef<HTMLDivElement | null>(null);

    const resolvedSource = resolveVideoSource(entry.videoUrl);
    const resolvedCaptions = entry.captionsUrl ? resolveVideoSource(entry.captionsUrl) : undefined;

    // Session-scoped prefs shared with videobook. Ignores autoplay (no chapters).
    const {
        muted, setMuted,
        captionsOn, setCaptionsOn,
        captionSizeIndex,
        playbackSpeedIndex,
    } = useVideoBookSettings();

    // Every open lands on the cinematic intro splash; the sphere mounts after
    // the dwell. (Onboarding card was removed in favour of the Gyro toggle in
    // the top bar, which doubles as the iOS orientation-permission gesture.)
    const [phase, setPhase] = useState<Phase>('intro');
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [gyroEnabled, setGyroEnabled] = useState(false);
    const {
        chromeVisible,
        chromeRootRef,
        resetControlsTimer,
        onChromeFocusCapture,
        onChromeBlurCapture,
    } = useControlsAutoHide(V360_CONTROLS_AUTO_HIDE_MS);

    const sphere = useVideoSphere();
    const {
        mount, load, play, pause, seek, addRotation,
        setMuted: setVideoMuted, setPlaybackRate,
        isPlaying, isReady, currentTime, duration,
        hasCaptions, activeCueText,
    } = sphere;

    // Preload so the sphere can mount the moment we hit player phase.
    // `isReady` gates the sphere div so VideoTexture binds against a
    // populated <video> (see useVideoSphere header).
    useEffect(() => {
        load(resolvedSource, resolvedCaptions).catch((err) => {
            console.warn('[Video360Overlay] load failed:', err);
        });
    }, [resolvedSource, resolvedCaptions, load]);

    const sphereHostRef = useCallback((node: HTMLDivElement | null) => {
        sphereContainerRef.current = node;
        if (node) mount(node);
    }, [mount]);

    useEffect(() => {
        setVideoMuted(muted);
    }, [muted, resolvedSource, setVideoMuted]);

    useEffect(() => {
        const rate = PLAYBACK_SPEED_STEPS[playbackSpeedIndex]?.rate ?? 1;
        setPlaybackRate(rate);
    }, [playbackSpeedIndex, resolvedSource, setPlaybackRate]);

    /** Sphere tap wakes the chrome. Play/pause is the play button. */
    const handleSphereTap = useCallback(() => {
        resetControlsTimer();
    }, [resetControlsTimer]);

    const toggleMuted = useCallback(() => {
        const next = !muted;
        setVideoMuted(next);
        setMuted(next);
    }, [muted, setMuted, setVideoMuted]);

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

    // Device orientation drives the sphere only, never Kit. Gated on the user
    // explicitly opting in via the Gyro toggle (iOS 13+ also needs the permission
    // grant the same toggle requests).
    const orientationSupported = isDeviceOrientationSupported();
    useDeviceOrientation(
        gyroEnabled && phase === 'player',
        (dYaw, dPitch) => addRotation(dYaw, dPitch),
        { suppressKitDispatch: true },
    );

    const handleGyroToggle = useCallback(async () => {
        if (gyroEnabled) {
            setGyroEnabled(false);
            return;
        }
        if (orientationSupported) {
            const granted = await requestOrientationPermission();
            if (!granted) return;
        }
        setGyroEnabled(true);
        resetControlsTimer();
    }, [gyroEnabled, orientationSupported, resetControlsTimer]);

    const dragActive = useRef(false);
    const lastPointer = useRef({ x: 0, y: 0 });

    const handleDragDown = useCallback((e: React.PointerEvent) => {
        if (phase !== 'player' || e.button !== 0) return;
        dragActive.current = true;
        lastPointer.current = { x: e.clientX, y: e.clientY };
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    }, [phase]);

    const handleDragMove = useCallback((e: React.PointerEvent) => {
        if (!dragActive.current) return;
        const dx = e.clientX - lastPointer.current.x;
        const dy = e.clientY - lastPointer.current.y;
        lastPointer.current = { x: e.clientX, y: e.clientY };
        if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
            // Negate dx for "grab the world and pull it" feel.
            addRotation(-dx * DRAG_SENSITIVITY, dy * DRAG_SENSITIVITY);
        }
    }, [addRotation]);

    const handleDragUp = useCallback(() => {
        dragActive.current = false;
    }, []);

    // Lock Kit movement so a stray WASD step doesn't corrupt the saved
    // pose restored on close. The sphere owns all rotation client-side.
    useEffect(() => {
        sendMessage('movementInputControl', { enabled: false });
        return () => { sendMessage('movementInputControl', { enabled: true }); };
    }, []);

    const handleClose = useCallback(() => {
        pause();
        video360.close();
    }, [video360, pause]);

    const togglePlayPause = useCallback(() => {
        if (isPlaying) pause();
        else void play();
    }, [isPlaying, pause, play]);

    // Cinematic intro dwell — auto-advance to player after a short hold.
    useEffect(() => {
        if (phase !== 'intro') return;
        const id = window.setTimeout(() => setPhase('player'), INTRO_DWELL_MS);
        return () => window.clearTimeout(id);
    }, [phase]);

    // Auto-play once player phase + video are both ready. Gating on isReady
    // covers second-open (waits for VideoTexture to bind against a populated
    // <video>). The cinematic title is shown earlier in the `intro` phase, so
    // playback starts cleanly with no in-sphere title overlay.
    useEffect(() => {
        if (phase !== 'player' || !isReady) return;
        void play();
    }, [phase, isReady, play]);

    // Teleport ownership: enter via context.open() (skip-onboarding) or
    // handleStartExperience (first-open). Exit on unmount. Mirrors
    // SpatialSoundOverlay.
    useEffect(() => {
        return () => {
            sendMessage('playerExitXformView', {});
        };
    }, []);

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
        seek(ratio * duration);
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
    const titleText = t(entry.videoTitle) || t(entry.title);

    const playerChromeVisible = phase === 'player' && chromeVisible && !settingsOpen;

    return (
        <div
            ref={chromeRootRef}
            className={`v360-overlay v360-overlay--${phase}`}
            onMouseMove={phase === 'player' ? resetControlsTimer : undefined}
            onFocusCapture={phase === 'player' ? onChromeFocusCapture : undefined}
            onBlurCapture={phase === 'player' ? onChromeBlurCapture : undefined}
        >
            <div
                className={`v360-top-bar${phase !== 'player' || playerChromeVisible ? ' v360-top-bar--visible' : ''}`}
            >
                <div className="v360-top-bar-right">
                    <PanelCloseButton
                        className="v360-close-btn"
                        onClick={(e) => { e.stopPropagation(); handleClose(); }}
                    />
                    <MediaSettingsButton
                        onClick={(e) => { e.stopPropagation(); handleOpenSettings(); }}
                        ariaLabel={t('video360.openSettings', 'Open video settings')}
                    />
                    {orientationSupported && (
                        <button
                            type="button"
                            className={`v360-gyro-btn${gyroEnabled ? ' v360-gyro-btn--active' : ''}`}
                            onClick={(e) => { e.stopPropagation(); void handleGyroToggle(); }}
                            aria-pressed={gyroEnabled}
                            aria-label={gyroEnabled
                                ? t('video360.gyro.disable', 'Disable Gyro mode')
                                : t('video360.gyro.enable', 'Enable Gyro mode')}
                            title={gyroEnabled
                                ? t('video360.gyro.disable', 'Disable Gyro mode')
                                : t('video360.gyro.enable', 'Enable Gyro mode')}
                        >
                            <IntroGyroIcon />
                            <span className="v360-gyro-btn-label" aria-hidden="true">
                                {t('video360.gyro.label', 'Gyro')}
                            </span>
                        </button>
                    )}
                </div>
            </div>

            <div className="v360-stage">
                {phase === 'intro' && (
                    <>
                        <video
                            className="v360-onboarding-bg-video"
                            src={resolvedSource}
                            preload="metadata"
                            playsInline
                            muted
                            aria-hidden
                            onLoadedMetadata={(e) => {
                                const video = e.currentTarget;
                                video.pause();
                                video.currentTime = 0;
                            }}
                        />
                        <div className="v360-intro-scrim" aria-hidden />
                        <div className="v360-intro-content">
                            <p className="v360-intro-kicker">{t('video360.label')}</p>
                            <h1 className="v360-intro-title">{titleText}</h1>
                        </div>
                        <div className="v360-intro-helper">
                            <IntroSwipePhoneIcon />
                            <div className="v360-intro-helper-text">
                                <p className="v360-intro-helper-line">
                                    {t('video360.intro.swipeHelp1', 'Swipe to look around. You can tap')}
                                </p>
                                <p className="v360-intro-helper-line v360-intro-helper-line--gyro">
                                    <IntroGyroIcon />
                                    <span>{t('video360.intro.swipeHelp2', 'to activate Gyro mode.')}</span>
                                </p>
                            </div>
                        </div>
                    </>
                )}

                {phase === 'player' && (
                    <>
                        {/* Sphere gated on isReady (see useVideoSphere header). */}
                        {isReady ? (
                            <div
                                ref={sphereHostRef}
                                className="v360-sphere"
                                onClick={handleSphereTap}
                                onPointerDown={handleDragDown}
                                onPointerMove={handleDragMove}
                                onPointerUp={handleDragUp}
                                onPointerCancel={handleDragUp}
                            />
                        ) : (
                            <div className="v360-loading" role="status" aria-live="polite">
                                <span className="v360-loading-spinner essential-motion" aria-hidden="true" />
                                <span className="sr-only">{t('loading.loadingScene')}</span>
                            </div>
                        )}
                        {hasCaptions && captionsOn && activeCueText && (
                            <div
                                className={`v360-captions${playerChromeVisible ? ' v360-captions--with-controls' : ''}`}
                                role="status"
                                aria-live="polite"
                                data-caption-size={captionSizeIndex}
                            >
                                {activeCueText.split('\n').map((line, i) => (
                                    <span key={i} className="v360-caption-line">{line}</span>
                                ))}
                            </div>
                        )}
                    </>
                )}
            </div>

            {phase === 'player' && (
                <div
                    className={`v360-controls${playerChromeVisible ? ' v360-controls--visible' : ''}`}
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="v360-seek-row">
                        <div className="v360-seek-dot-left" aria-hidden />
                        <div
                            className="v360-seek-bar"
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
                            aria-label={t('video360.seek')}
                            tabIndex={0}
                        >
                            <div className="v360-seek-track" />
                            <div className="v360-seek-fill" style={{ width: `${progress}%` }} />
                            <div className="v360-seek-thumb" style={{ left: `${progress}%` }} />
                        </div>
                    </div>

                    <div className="v360-time-row">
                        <span className="v360-time">{formatTime(currentTime)}</span>
                        <span className="v360-time">{formatTime(duration)}</span>
                    </div>

                    <div className="v360-transport">
                        <MediaMuteButton
                            className="v360-transport-btn"
                            muted={muted}
                            onClick={(e) => { e.stopPropagation(); toggleMuted(); resetControlsTimer(); }}
                            ariaLabel={muted ? t('video360.unmute', 'Unmute') : t('video360.mute', 'Mute')}
                        />

                        <MediaPlayPauseButton
                            className="v360-transport-btn"
                            isPlaying={isPlaying}
                            onClick={togglePlayPause}
                            ariaLabel={isPlaying ? t('video.pause') : t('video.play')}
                        />

                        <MediaCaptionsButton
                            className="v360-transport-btn"
                            captionsOn={captionsOn}
                            hasCaptions={hasCaptions}
                            onClick={(e) => { e.stopPropagation(); toggleCaptions(); resetControlsTimer(); }}
                            ariaLabel={captionsOn ? t('video360.hideCaptions') : t('video360.showCaptions')}
                            title={t('video360.captions')}
                        />
                    </div>
                </div>
            )}

            {/* Autoplay card hidden — no chapters in 360°. */}
            {settingsOpen && (
                <VideoBookSettingsPanel
                    onClose={handleCloseSettings}
                    showAutoplay={false}
                    titleKey="video360.settingsTitle"
                />
            )}
        </div>
    );
};

const Video360Overlay: React.FC = () => {
    const video360 = useVideo360();
    if (!video360.isOpen || !video360.entry) return null;
    return <Video360OverlayInner />;
};

export default Video360Overlay;
