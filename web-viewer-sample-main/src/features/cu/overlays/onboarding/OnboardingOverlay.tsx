import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useCuModalBackgroundInert } from '../../hooks/useCuModalBackgroundInert';
import { SettingsLanguageId } from '../../types';
import { SETTINGS_LANGUAGES } from '../../constants';
import LanguageDropdown from '../../controls/LanguageDropdown';
import aLetterSvg from '@icons/map-markers/a_letter.svg';
import { useTranslation } from 'react-i18next';
import { sendMessage } from '../../../streaming/messaging';
import { useAppUI } from '../../../streaming/contexts';
import { aiLanguageFor } from '../../../../services/aiLanguage';
import './OnboardingOverlay.css';

import screen1Url from '@icons/chat/backgrounds/screen1.png';
import screen2Url from '@icons/chat/backgrounds/screen2.png';
import screen3Url from '@icons/chat/backgrounds/screen3.png';

const SLIDE_AVATARS: { src: string; mirrored?: boolean }[] = [
    { src: screen1Url },
    { src: screen2Url },
    { src: screen3Url, mirrored: true },
];

const SLIDE_COUNT = 3;
const SWIPE_THRESHOLD = 50;

const INTERACTIVE_SELECTOR =
    '.onboarding-language-wrap, .onboarding-dots, .onboarding-cta, .cu-lang-dropdown-anchor';

const OnboardingOverlay: React.FC = () => {
    const appUI = useAppUI();
    const onDone = appUI.handleOnboardingDone;
    const { t, i18n } = useTranslation();
    useCuModalBackgroundInert(true);
    const overlayRef = useRef<HTMLDivElement>(null);
    const [slide, setSlide] = useState(0);
    const [language, setLanguage] = useState<SettingsLanguageId>(
        () => SETTINGS_LANGUAGES.find((o) => o.i18nCode === i18n.language)?.id ?? 'english',
    );
    const [dragOffset, setDragOffset] = useState(0);
    const [dragging, setDragging] = useState(false);
    const dragStartX = useRef(0);
    const dragStartSlide = useRef(0);

    const handleLanguageChange = useCallback((id: SettingsLanguageId) => {
        setLanguage(id);
        const lang = SETTINGS_LANGUAGES.find((o) => o.id === id);
        sendMessage('ai.agent.setLanguage', { language: aiLanguageFor(lang?.i18nCode) });
        if (lang?.i18nCode) i18n.changeLanguage(lang.i18nCode);
    }, [i18n]);

    const handleDone = useCallback(() => {
        onDone();
    }, [onDone]);

    const goTo = useCallback((idx: number) => {
        setSlide(Math.max(0, Math.min(SLIDE_COUNT - 1, idx)));
    }, []);

    const onPointerDown = useCallback((e: React.PointerEvent) => {
        if ((e.target as HTMLElement).closest('.onboarding-language-wrap')) return;
        if ((e.target as HTMLElement).closest('button')) return;
        dragStartX.current = e.clientX;
        dragStartSlide.current = slide;
        setDragging(true);
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    }, [slide]);

    const onPointerMove = useCallback((e: React.PointerEvent) => {
        if (!dragging) return;
        const dx = e.clientX - dragStartX.current;
        setDragOffset(dx);
    }, [dragging]);

    const onPointerUp = useCallback(() => {
        if (!dragging) return;
        setDragging(false);
        if (Math.abs(dragOffset) > SWIPE_THRESHOLD) {
            const dir = dragOffset < 0 ? 1 : -1;
            goTo(dragStartSlide.current + dir);
        }
        setDragOffset(0);
    }, [dragging, dragOffset, goTo]);

    const slidePct = 100 / SLIDE_COUNT;
    const trackPct = -(slide * slidePct);
    const dragPx = dragging ? dragOffset : 0;
    const trackTransform = dragPx
        ? `translateX(calc(${trackPct}% + ${dragPx}px))`
        : `translateX(${trackPct}%)`;

    /**
     * Keyboard arrows move between slides anywhere on the overlay (WCAG 2.1.1
     * Keyboard). Pointer/swipe still works via the existing handlers above.
     */
    const onOverlayKeyDown = useCallback(
        (e: React.KeyboardEvent<HTMLDivElement>) => {
            if ((e.target as HTMLElement).closest(INTERACTIVE_SELECTOR)) return;
            if (e.key === 'ArrowRight') {
                e.preventDefault();
                goTo(slide + 1);
            } else if (e.key === 'ArrowLeft') {
                e.preventDefault();
                goTo(slide - 1);
            } else if (e.key === 'Home') {
                e.preventDefault();
                goTo(0);
            } else if (e.key === 'End') {
                e.preventDefault();
                goTo(SLIDE_COUNT - 1);
            }
        },
        [goTo, slide],
    );

    useEffect(() => {
        const raf = requestAnimationFrame(() => {
            const trigger = overlayRef.current?.querySelector<HTMLButtonElement>(
                '.cu-lang-dropdown-trigger',
            );
            trigger?.focus({ preventScroll: true });
        });
        return () => cancelAnimationFrame(raf);
    }, []);

    return (
        <div
            ref={overlayRef}
            className="onboarding-overlay"
            aria-label={t('onboarding.ariaLabel')}
            aria-roledescription="carousel"
            onKeyDown={onOverlayKeyDown}
        >
            <div className="onboarding-carousel">
                <div
                    className={`onboarding-track${dragging ? ' onboarding-track--dragging' : ''}`}
                    style={{ transform: trackTransform }}
                    onPointerDown={onPointerDown}
                    onPointerMove={onPointerMove}
                    onPointerUp={onPointerUp}
                    onPointerCancel={onPointerUp}
                >
                {/* Slide 1: Language */}
                <div
                    className="onboarding-slide"
                    role="tabpanel"
                    id="onboarding-panel-0"
                    aria-labelledby="onboarding-tab-0"
                    aria-roledescription="slide"
                    aria-hidden={slide !== 0}
                    {...(slide !== 0 ? { inert: '' as const } : {})}
                >
                    <div className="onboarding-avatar-bg" aria-hidden="true">
                        <img className="onboarding-avatar-img" src={SLIDE_AVATARS[0].src} alt="" draggable={false} />
                    </div>
                    <div className="onboarding-panel">
                        <div className="onboarding-panel-content">
                            <h2 className="onboarding-heading">{t('onboarding.selectLanguage')}</h2>
                            <div className="onboarding-language-wrap">
                                <LanguageDropdown
                                    value={language}
                                    onChange={handleLanguageChange}
                                />
                            </div>
                        </div>
                    </div>
                </div>

                {/* Slide 2: Welcome */}
                <div
                    className="onboarding-slide"
                    role="tabpanel"
                    id="onboarding-panel-1"
                    aria-labelledby="onboarding-tab-1"
                    aria-roledescription="slide"
                    aria-hidden={slide !== 1}
                    {...(slide !== 1 ? { inert: '' as const } : {})}
                >
                    <div className="onboarding-avatar-bg" aria-hidden="true">
                        <img className="onboarding-avatar-img" src={SLIDE_AVATARS[1].src} alt="" draggable={false} />
                    </div>
                    <div className="onboarding-panel">
                        <div className="onboarding-panel-content">
                            <h2 className="onboarding-heading">
                                {t('onboarding.welcomeHeading')}
                            </h2>
                            <p className="onboarding-body">
                                {t('onboarding.welcomeBody')}
                            </p>
                        </div>
                    </div>
                </div>

                {/* Slide 3: Start exploring */}
                <div
                    className="onboarding-slide"
                    role="tabpanel"
                    id="onboarding-panel-2"
                    aria-labelledby="onboarding-tab-2"
                    aria-roledescription="slide"
                    aria-hidden={slide !== 2}
                    {...(slide !== 2 ? { inert: '' as const } : {})}
                >
                    <div className="onboarding-avatar-bg" aria-hidden="true">
                        <img className="onboarding-avatar-img onboarding-avatar-img--mirrored" src={SLIDE_AVATARS[2].src} alt="" draggable={false} />
                    </div>
                    <div className="onboarding-panel">
                        <div className="onboarding-panel-content">
                            <h2 className="onboarding-heading">{t('onboarding.allSet')}</h2>
                            <button
                                type="button"
                                className="onboarding-cta"
                                onClick={handleDone}
                            >
                                <img className="onboarding-cta-logo" src={aLetterSvg} alt="" aria-hidden="true" draggable={false} />
                                <span className="onboarding-cta-label">{t('onboarding.startExploring')}</span>
                            </button>
                        </div>
                    </div>
                </div>
                </div>
            </div>
            <Dots current={slide} onDotClick={goTo} />
        </div>
    );
};

const Dots: React.FC<{ current: number; onDotClick: (idx: number) => void }> = ({
    current,
    onDotClick,
}) => {
    const { t } = useTranslation();
    return (
        <div
            className="onboarding-dots"
            role="tablist"
            aria-label={t('onboarding.slidesAriaLabel')}
            onKeyDown={(e) => {
                let next = current;
                if (e.key === 'ArrowRight') next = (current + 1) % SLIDE_COUNT;
                else if (e.key === 'ArrowLeft') next = (current - 1 + SLIDE_COUNT) % SLIDE_COUNT;
                else if (e.key === 'Home') next = 0;
                else if (e.key === 'End') next = SLIDE_COUNT - 1;
                else return;
                e.preventDefault();
                onDotClick(next);
                e.currentTarget
                    .querySelector<HTMLButtonElement>(`[data-slide-idx="${next}"]`)
                    ?.focus();
            }}
        >
            {Array.from({ length: SLIDE_COUNT }, (_, i) => (
                <button
                    key={i}
                    type="button"
                    role="tab"
                    id={`onboarding-tab-${i}`}
                    data-slide-idx={i}
                    aria-selected={current === i}
                    aria-controls={`onboarding-panel-${i}`}
                    aria-label={t('onboarding.slide', { number: i + 1 })}
                    tabIndex={current === i ? 0 : -1}
                    className={`onboarding-dot${current === i ? ' onboarding-dot--active' : ''}`}
                    onClick={(e) => {
                        e.stopPropagation();
                        onDotClick(i);
                    }}
                    /*
                     * Prevent the button from receiving focus from a pointer
                     * (mouse/touch). `mousedown.preventDefault()` is the only
                     * reliably-specced way to skip focus-on-click — touch
                     * platforms synthesise mousedown, so this covers both.
                     * Keyboard activation (Tab + Enter/Space, Arrow keys)
                     * still focuses the dot because it goes through keydown,
                     * not mousedown.
                     */
                    onMouseDown={(e) => {
                        e.preventDefault();
                    }}
                />
            ))}
        </div>
    );
};

export default OnboardingOverlay;
