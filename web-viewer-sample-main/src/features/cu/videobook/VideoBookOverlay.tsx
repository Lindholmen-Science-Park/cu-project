import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useControl, useVideoBookSettings } from '../../streaming/contexts';
import { useModalAccessibility } from '../../streaming/hooks/useModalAccessibility';
import PanelCloseButton from '../controls/PanelCloseButton';
import VideoBookPlayer, { type PickedChapterSegment } from './VideoBookPlayer';
import { VideoBookFloatingBackToVideoIcon, VideoBookFloatingChipIcon } from './VideoBookChipIcons';
import VideoBookSettingsPanel from './VideoBookSettingsPanel';
import '../CUControls.css';
import './VideoBookOverlay.css';

/** Splash hero still — replace `assets/vbook-splash-bg.png` to update without code changes. */
import splashBgUrl from './assets/vbook-splash-bg.png';

/** After hero splash, auto-open player: full video from start with continuous autoplay (same as menu Autoplay). */
const VIDEO_BOOK_SPLASH_MS = 4000;

/** Chapter ids omitted from the chapter menu (`vbook-chapter-btn`); still in data for video / seek / player. */
const VBOOK_MENU_HIDDEN_CHAPTER_IDS = new Set<string>(['find_your_seat']);

export interface VideoBookEntry {
    id: string;
    iconId: string;
    title: string;
    subtitle: string;
    videoUrl: string;
    captionsUrl?: string;
    chapters: Array<{ id: string; label: string; timestampSeconds: number }>;
}

/** Hero / floating chip — uses currentColor from CSS */
function VideoBookHeroIcon({ className = 'vbook-hero-icon' }: { className?: string }) {
    return (
        <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
            <path
                fillRule="evenodd"
                clipRule="evenodd"
                d="M39.5 4C39.8978 4 40.2792 4.15815 40.5605 4.43945C40.8419 4.72076 41 5.10217 41 5.5V35.5C41 35.8978 40.8419 36.2792 40.5605 36.5605C40.2792 36.8419 39.8978 37 39.5 37H14C13.2044 37 12.4415 37.3163 11.8789 37.8789C11.3163 38.4415 11 39.2043 11 40H36.5C36.8978 40 37.2792 40.1581 37.5605 40.4395C37.8419 40.7208 38 41.1022 38 41.5C38 41.8978 37.8419 42.2792 37.5605 42.5605C37.2792 42.8419 36.8978 43 36.5 43H9.5C9.10218 43 8.72076 42.8419 8.43945 42.5605C8.15815 42.2792 8 41.8978 8 41.5V10C8 8.4087 8.63259 6.88303 9.75781 5.75781C10.883 4.63259 12.4087 4 14 4H39.5ZM21.2939 12C21.0674 11.9959 20.843 12.0508 20.6455 12.1582C20.4502 12.2639 20.2873 12.4179 20.1738 12.6045C20.0603 12.7913 20.0004 13.0041 20 13.2207V26.7783C20.0003 26.9949 20.0604 27.2078 20.1738 27.3945C20.2873 27.5813 20.45 27.736 20.6455 27.8418C20.843 27.9492 21.0674 28.0041 21.2939 28C21.5203 27.9959 21.7415 27.9327 21.9346 27.8184L33.3955 21.0391C33.5803 20.9311 33.7329 20.7786 33.8389 20.5967C33.9448 20.4146 34.0005 20.2089 34 20C34.0005 19.7911 33.9448 19.5854 33.8389 19.4033C33.733 19.2213 33.5803 19.069 33.3955 18.9609L21.9346 12.1807C21.7415 12.0664 21.5203 12.0041 21.2939 12Z"
                fill="currentColor"
            />
        </svg>
    );
}

/** Same icon shell as CUControls People / Groups (`cu-icon-btn`) */
function CuPeopleGroupsIcon() {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" width="23" height="23" viewBox="0 0 23 23" fill="none" className="cu-icon-btn-svg" aria-hidden>
            <path
                d="M2.875 7.18769C2.875 6.99706 2.95073 6.81424 3.08552 6.67944C3.22032 6.54465 3.40314 6.46892 3.59377 6.46892H6.93334C7.08826 5.94995 7.40654 5.49483 7.84085 5.17124C8.27515 4.84764 8.8023 4.67285 9.3439 4.67285C9.8855 4.67285 10.4126 4.84764 10.847 5.17124C11.2813 5.49483 11.5995 5.94995 11.7545 6.46892H19.4066C19.5973 6.46892 19.7801 6.54465 19.9149 6.67944C20.0497 6.81424 20.1254 6.99706 20.1254 7.18769C20.1254 7.37832 20.0497 7.56114 19.9149 7.69593C19.7801 7.83073 19.5973 7.90645 19.4066 7.90645H11.7545C11.5995 8.42543 11.2813 8.88054 10.847 9.20414C10.4126 9.52773 9.8855 9.70252 9.3439 9.70252C8.8023 9.70252 8.27515 9.52773 7.84085 9.20414C7.40654 8.88054 7.08826 8.42543 6.93334 7.90645H3.59377C3.40314 7.90645 3.22032 7.83073 3.08552 7.69593C2.95073 7.56114 2.875 7.37832 2.875 7.18769ZM19.4066 15.0941H17.5046C17.3497 14.5751 17.0314 14.12 16.5971 13.7964C16.1628 13.4728 15.6356 13.2981 15.094 13.2981C14.5524 13.2981 14.0253 13.4728 13.591 13.7964C13.1567 14.12 12.8384 14.5751 12.6835 15.0941H3.59377C3.40314 15.0941 3.22032 15.1698 3.08552 15.3046C2.95073 15.4394 2.875 15.6223 2.875 15.8129C2.875 16.0035 2.95073 16.1863 3.08552 16.3211C3.22032 16.4559 3.40314 16.5317 3.59377 16.5317H12.6835C12.8384 17.0506 13.1567 17.5057 13.591 17.8293C14.0253 18.1529 14.5524 18.3277 15.094 18.3277C15.6356 18.3277 16.1628 18.1529 16.5971 17.8293C17.0314 17.5057 17.3497 17.0506 17.5046 16.5317H19.4066C19.5973 16.5317 19.7801 16.4559 19.9149 16.3211C20.0497 16.1863 20.1254 16.0035 20.1254 15.8129C20.1254 15.6223 20.0497 15.4394 19.9149 15.3046C19.7801 15.1698 19.5973 15.0941 19.4066 15.0941Z"
                fill="currentColor"
            />
        </svg>
    );
}

function splitTitleForSplash(title: string): { line1: string; line2: string | null } {
    const idx = title.indexOf(' & ');
    if (idx >= 0) {
        return {
            line1: title.slice(0, idx).trim(),
            line2: `& ${title.slice(idx + 3).trim()}`,
        };
    }
    return { line1: title, line2: null };
}

const VideoBookOverlayInner: React.FC = () => {
    const { t } = useTranslation();
    const overlayRef = useRef<HTMLDivElement>(null);
    const playerRootRef = useRef<HTMLDivElement>(null);
    const ctrl = useControl();
    const entry = ctrl.videobookEntry;
    const [activeView, setActiveView] = useState<'splash' | 'menu' | 'playing'>(() =>
        ctrl.videobookShowEntrySplash ? 'splash' : 'menu',
    );
    const [startAtSeconds, setStartAtSeconds] = useState(0);
    /**
     * Continuous-playback mode lives in `VideoBookSettingsContext` so the settings panel
     * (`VideoBookSettingsPanel`) and the player share one source of truth across opens
     * and view transitions. Entry-point handlers below write to this setter to express
     * "this opening's intent" (chapter row → segment, splash / menu Autoplay → continuous);
     * the panel's PillSwitch writes to the same setter to flip the mode mid-playback.
     */
    const { autoplayEnabled, setAutoplayEnabled } = useVideoBookSettings();
    /** Dot-to-dot range for the chapter row that opened the player (sorted by time = left-to-right on the bar). */
    const [pickedChapterSegment, setPickedChapterSegment] = useState<PickedChapterSegment | null>(null);
    /**
     * Settings panel visibility — hoisted to the overlay so the same panel renders above
     * the chapter menu and the in-progress player without re-mounting per view.
     */
    const [settingsOpen, setSettingsOpen] = useState(false);
    useModalAccessibility(overlayRef, { enabled: activeView === 'splash' || activeView === 'menu' });
    useModalAccessibility(playerRootRef, { enabled: activeView === 'playing' && !settingsOpen });
    /**
     * Captions font-size lives at the app root in `VideoBookSettingsContext` so the value
     * survives videobook close/reopen cycles within a session (refresh resets to default).
     * The overlay just relays the current index down to the player.
     */
    const { captionSizeIndex } = useVideoBookSettings();

    const localizedEntry = useMemo(() => {
        if (!entry) return null;
        return {
            ...entry,
            title: t(entry.title),
            subtitle: t(entry.subtitle),
            chapters: entry.chapters.map((ch) => ({
                ...ch,
                label: t(ch.label),
            })),
        };
    }, [entry, t]);

    const dismiss = useCallback(() => {
        ctrl.setVideobookShowEntrySplash(false);
        ctrl.setVideobookOpen(false);
        ctrl.setVideobookEntry(null);
    }, [ctrl]);

    const goSplashToMenu = useCallback(() => {
        ctrl.setVideobookShowEntrySplash(false);
        setActiveView('menu');
    }, [ctrl]);

    /** Same as menu “Autoplay”: start at 0, full-video continuous mode, video plays in player. */
    const goSplashToVideoAutoplay = useCallback(() => {
        ctrl.setVideobookShowEntrySplash(false);
        setPickedChapterSegment(null);
        setAutoplayEnabled(true);
        setStartAtSeconds(0);
        setActiveView('playing');
    }, [ctrl, setAutoplayEnabled]);

    useEffect(() => {
        if (activeView !== 'splash') return;
        const id = window.setTimeout(goSplashToVideoAutoplay, VIDEO_BOOK_SPLASH_MS);
        return () => window.clearTimeout(id);
    }, [activeView, goSplashToVideoAutoplay]);

    const handleChapterClick = useCallback(
        (ch: VideoBookEntry['chapters'][number]) => {
            if (!localizedEntry) return;
            const sorted = [...localizedEntry.chapters].sort((a, b) => a.timestampSeconds - b.timestampSeconds);
            const idx = sorted.findIndex((c) => c.id === ch.id);
            const next = idx >= 0 && idx < sorted.length - 1 ? sorted[idx + 1] : null;
            setPickedChapterSegment({
                startSeconds: ch.timestampSeconds,
                endExclusiveSeconds: next != null ? next.timestampSeconds : null,
            });
            setAutoplayEnabled(false);
            setStartAtSeconds(ch.timestampSeconds);
            setActiveView('playing');
        },
        [localizedEntry, setAutoplayEnabled],
    );

    const handleFloatingSettings = useCallback(() => {
        setSettingsOpen(true);
    }, []);

    const handleCloseSettings = useCallback(() => {
        setSettingsOpen(false);
    }, []);

    const handlePlayerBack = useCallback(() => {
        setActiveView('menu');
    }, []);

    /** Chip click while the chapter library is open: return to the player without resetting playback state. */
    const handleMenuBackToVideo = useCallback(() => {
        setActiveView('playing');
    }, []);

    if (!localizedEntry) return null;

    const splashTitle = splitTitleForSplash(localizedEntry.title);

    if (activeView === 'splash') {
        return (
            <div ref={overlayRef} className="vbook-overlay vbook-overlay--splash" role="dialog" aria-modal="true" aria-label={localizedEntry.title}>
                <div className="vbook-splash" aria-hidden={false}>
                    <img className="vbook-splash-photo" src={splashBgUrl} alt="" draggable={false} />
                    <div className="vbook-splash-scrim" />
                    <div className="vbook-splash-center">
                        <p className="vbook-splash-kicker">{t('videobook.splashKicker', 'VIDEO BOOK')}</p>
                        <h1 className="vbook-splash-title">
                            <span className="vbook-splash-title-line">{splashTitle.line1}</span>
                            {splashTitle.line2 != null && (
                                <span className="vbook-splash-title-line">{splashTitle.line2}</span>
                            )}
                        </h1>
                    </div>
                </div>

                <div className="vbook-floating-stack" onClick={(e) => e.stopPropagation()}>
                    <PanelCloseButton
                        className="vbp-close-btn vbook-floating-close"
                        onClick={(e) => {
                            e.stopPropagation();
                            dismiss();
                        }}
                        ariaLabel={t('common.close')}
                        title={t('common.close')}
                    />
                    <button
                        type="button"
                        className="cu-icon-btn"
                        onClick={(e) => {
                            e.stopPropagation();
                            goSplashToMenu();
                        }}
                        title={t('videobook.openChapters')}
                        aria-label={t('videobook.openChapters')}
                    >
                        <CuPeopleGroupsIcon />
                    </button>
                    <button
                        type="button"
                        className="vbook-floating-btn vbook-floating-btn--videobook"
                        onClick={(e) => {
                            e.stopPropagation();
                            goSplashToMenu();
                        }}
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
        );
    }

    if (activeView === 'playing') {
        return (
            <div ref={playerRootRef} className="vbook-player-root">
                <VideoBookPlayer
                    entry={localizedEntry}
                    startAtSeconds={startAtSeconds}
                    fullVideoAutoplay={autoplayEnabled}
                    allowFullVideoModeToggle
                    pickedChapterSegment={pickedChapterSegment}
                    onBack={handlePlayerBack}
                    onClose={dismiss}
                    onOpenSettings={handleFloatingSettings}
                    topBarHidden={settingsOpen}
                    captionSizeIndex={captionSizeIndex}
                />
                {settingsOpen && <VideoBookSettingsPanel onClose={handleCloseSettings} />}
            </div>
        );
    }

    return (
        <>
        <div ref={overlayRef} className="vbook-overlay" role="dialog" aria-modal="true" aria-label={localizedEntry.title}>
            <div className="vbook-backdrop" onClick={dismiss} />

            <div
                className={`vbook-floating-stack${settingsOpen ? ' vbook-floating-stack--hidden' : ''}`}
                onClick={(e) => e.stopPropagation()}
                aria-hidden={settingsOpen || undefined}
            >
                <PanelCloseButton
                    className="vbp-close-btn vbook-floating-close"
                    onClick={(e) => {
                        e.stopPropagation();
                        dismiss();
                    }}
                    ariaLabel={t('common.close')}
                    title={t('common.close')}
                />
                <button
                    type="button"
                    className="cu-icon-btn"
                    onClick={(e) => {
                        e.stopPropagation();
                        handleFloatingSettings();
                    }}
                    title={t('videobook.openSettings', 'Open Video Book settings')}
                    aria-label={t('videobook.openSettings', 'Open Video Book settings')}
                >
                    <CuPeopleGroupsIcon />
                </button>
                <button
                    type="button"
                    className="vbook-floating-btn vbook-floating-btn--videobook vbook-floating-btn--videobook-back"
                    onClick={(e) => {
                        e.stopPropagation();
                        handleMenuBackToVideo();
                    }}
                    aria-label={t('videobook.backToVideo', 'Back to video')}
                    title={t('videobook.backToVideo', 'Back to video')}
                >
                    <VideoBookFloatingBackToVideoIcon />
                    <span className="vbook-floating-btn-label" aria-hidden="true">
                        {t('videobook.backToVideoLabel', 'Player')}
                    </span>
                </button>
            </div>

            <div className="vbook-content" onClick={(e) => e.stopPropagation()}>
                <div className="vbook-hero-wrap">
                    <div className="vbook-hero">
                        <VideoBookHeroIcon />
                    </div>
                </div>

                <h1 className="vbook-title">{localizedEntry.title}</h1>
                <p className="vbook-subtitle">{localizedEntry.subtitle}</p>

                <div className="vbook-chapters" role="group" aria-label={t('videobook.chaptersLabel')}>
                    {localizedEntry.chapters
                        .filter((ch) => !VBOOK_MENU_HIDDEN_CHAPTER_IDS.has(ch.id))
                        .map((ch) => (
                            <button
                                key={ch.id}
                                type="button"
                                className="vbook-chapter-btn"
                                onClick={() => handleChapterClick(ch)}
                            >
                                {ch.label}
                            </button>
                        ))}
                </div>
            </div>
        </div>
        {settingsOpen && <VideoBookSettingsPanel onClose={handleCloseSettings} />}
        </>
    );
};

const VideoBookOverlay: React.FC = () => {
    const ctrl = useControl();
    if (!ctrl.videobookOpen || !ctrl.videobookEntry) return null;
    return <VideoBookOverlayInner />;
};

export default VideoBookOverlay;
