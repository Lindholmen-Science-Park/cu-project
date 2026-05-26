import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useControl } from '../../contexts';
import { sendMessage } from '../../messaging';
import './VideoPlayerOverlay.css';

export interface VideoConfig {
    id: string;
    title: string;
    description?: string;
    source: string;
    durationSeconds?: number;
    onCompleteAction?: { type: string; payload: Record<string, any> };
}

const videoModules: Record<string, string> = {};
/** Relative glob — sibling `../kit-app-template-main` from web-viewer root; alias + glob breaks on Windows. */
const rawVideoModules = import.meta.glob(
    '../../../../../../kit-app-template-main/source/data/Assets/Videos/*.{mp4,webm,ogg}',
    { eager: true, import: 'default' },
);
for (const [path, url] of Object.entries(rawVideoModules)) {
    const filename = path.split('/').pop();
    if (filename) videoModules[filename] = url as string;
}

function resolveVideoSource(source: string): string {
    if (source.startsWith('http://') || source.startsWith('https://')) {
        return source;
    }
    return videoModules[source] || source;
}

const VideoPlayerOverlayInner: React.FC = () => {
    const ctrl = useControl();
    const { t } = useTranslation();
    const config = ctrl.videoPlayerConfig!;
    const onClose = ctrl.handleVideoClose;
    const onComplete = ctrl.handleVideoComplete;
    const videoRef = useRef<HTMLVideoElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const closeBtnRef = useRef<HTMLButtonElement>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [showControls, setShowControls] = useState(true);
    const controlsTimerRef = useRef<number | null>(null);

    const closeLabel = t('video.close');
    const playLabel = t('video.play');
    const pauseLabel = t('video.pause');

    const resolvedSource = resolveVideoSource(config.source);

    useEffect(() => {
        sendMessage('movementInputControl', { enabled: false });
        sendMessage('videoPlaybackEvent', { videoId: config.id, action: 'opened' });

        return () => {
            sendMessage('movementInputControl', { enabled: true });
        };
    }, [config.id]);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                handleClose();
            } else if (e.key === ' ' || e.key === 'k') {
                e.preventDefault();
                togglePlayPause();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    });

    const resetControlsTimer = useCallback(() => {
        setShowControls(true);
        if (controlsTimerRef.current) window.clearTimeout(controlsTimerRef.current);
        controlsTimerRef.current = window.setTimeout(() => {
            if (isPlaying) setShowControls(false);
        }, 3000);
    }, [isPlaying]);

    const togglePlayPause = useCallback(() => {
        const video = videoRef.current;
        if (!video) return;
        if (video.paused) {
            video.play();
        } else {
            video.pause();
        }
    }, []);

    const handleClose = useCallback(() => {
        sendMessage('videoPlaybackEvent', { videoId: config.id, action: 'closed' });
        onClose();
    }, [config.id, onClose]);

    const handleVideoEnded = useCallback(() => {
        setIsPlaying(false);
        setShowControls(true);
        sendMessage('videoPlaybackEvent', { videoId: config.id, action: 'ended' });
        onComplete?.(config);
    }, [config, onComplete]);

    const handleTimeUpdate = useCallback(() => {
        const video = videoRef.current;
        if (video) setCurrentTime(video.currentTime);
    }, []);

    const handleLoadedMetadata = useCallback(() => {
        const video = videoRef.current;
        if (video) setDuration(video.duration);
    }, []);

    const handleSeek = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const video = videoRef.current;
        if (video) {
            video.currentTime = parseFloat(e.target.value);
        }
    }, []);

    const formatTime = (seconds: number): string => {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    /**
     * Reveal controls whenever any keyboard focus moves into the overlay so
     * keyboard / screen-reader users get the same affordances as mouse users
     * (WCAG 2.1.1, 2.4.7).
     */
    const handleFocusIn = useCallback(() => {
        setShowControls(true);
        if (controlsTimerRef.current) window.clearTimeout(controlsTimerRef.current);
    }, []);

    // Move initial focus to the close button so Esc / Tab cycle starts inside
    // the modal (WCAG 2.4.3 Focus Order).
    useEffect(() => {
        closeBtnRef.current?.focus();
    }, []);

    return (
        <div
            ref={containerRef}
            className="video-overlay"
            role="dialog"
            aria-modal="true"
            aria-label={t('video.watchTitle', { title: config.title })}
            onMouseMove={resetControlsTimer}
            onFocus={handleFocusIn}
            onClick={(e) => {
                if (e.target === e.currentTarget) handleClose();
            }}
        >
            <div className="video-overlay-container">
                <div className="video-overlay-header">
                    <div className="video-overlay-title">{config.title}</div>
                    <button
                        ref={closeBtnRef}
                        type="button"
                        className="video-overlay-close"
                        onClick={handleClose}
                        title={`${closeLabel} (Esc)`}
                        aria-label={closeLabel}
                    >
                        <span aria-hidden>&times;</span>
                    </button>
                </div>

                {/*
                  Play/pause is exposed as a real button overlaid on the video
                  rather than relying on a click handler on the surrounding div
                  so keyboard users can reach and toggle it (WCAG 2.1.1).
                */}
                <div className="video-overlay-player">
                    <video
                        ref={videoRef}
                        src={resolvedSource}
                        onPlay={() => { setIsPlaying(true); resetControlsTimer(); }}
                        onPause={() => { setIsPlaying(false); setShowControls(true); }}
                        onEnded={handleVideoEnded}
                        onTimeUpdate={handleTimeUpdate}
                        onLoadedMetadata={handleLoadedMetadata}
                        autoPlay
                        playsInline
                        aria-label={config.title}
                    />

                    <button
                        type="button"
                        className={`video-overlay-play-overlay${isPlaying ? ' video-overlay-play-overlay--playing' : ''}`}
                        onClick={(e) => { e.stopPropagation(); togglePlayPause(); }}
                        aria-label={isPlaying ? pauseLabel : playLabel}
                    >
                        {!isPlaying && (
                            <span className="video-overlay-play-btn" aria-hidden>
                                <svg viewBox="0 0 24 24" width="64" height="64">
                                    <polygon points="5,3 19,12 5,21" fill="white" />
                                </svg>
                            </span>
                        )}
                    </button>
                </div>

                <div className={`video-overlay-controls ${showControls ? 'visible' : ''}`}>
                    <button
                        type="button"
                        className="video-control-btn"
                        onClick={(e) => { e.stopPropagation(); togglePlayPause(); }}
                        title={isPlaying ? pauseLabel : playLabel}
                        aria-label={isPlaying ? pauseLabel : playLabel}
                    >
                        <span aria-hidden>{isPlaying ? '⏸' : '▶'}</span>
                    </button>
                    <span className="video-time" aria-hidden>
                        {formatTime(currentTime)}
                    </span>
                    <input
                        type="range"
                        className="video-seek-bar"
                        min={0}
                        max={duration || 0}
                        step={0.1}
                        value={currentTime}
                        onChange={handleSeek}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={t('video.videoLabel')}
                        aria-valuemin={0}
                        aria-valuemax={Math.max(0, duration)}
                        aria-valuenow={currentTime}
                        aria-valuetext={`${formatTime(currentTime)} / ${formatTime(duration)}`}
                    />
                    <span className="video-time" aria-hidden>
                        {formatTime(duration)}
                    </span>
                    <button
                        type="button"
                        className="video-control-btn"
                        onClick={(e) => { e.stopPropagation(); handleClose(); }}
                        title={closeLabel}
                        aria-label={closeLabel}
                    >
                        <span aria-hidden>✕</span>
                    </button>
                </div>
            </div>
        </div>
    );
};

const VideoPlayerOverlay: React.FC = () => {
    const ctrl = useControl();
    if (!ctrl.videoPlayerOpen || !ctrl.videoPlayerConfig) return null;
    return <VideoPlayerOverlayInner />;
};

export default VideoPlayerOverlay;
