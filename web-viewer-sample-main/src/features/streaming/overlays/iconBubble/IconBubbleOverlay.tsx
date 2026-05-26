import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppUI, useControl, useStream, useSpatialSound, useVideo360 } from '../../contexts';
import { resolvePoiLocalizedTitle } from '../../utils/poiLocalizedTitle';
import './IconBubbleOverlay.css';
import type { NearestIconInfo } from '../../hooks/useControlHandlers';
import { resolveIconBubbleAvatarUrl } from '@icons/iconBubbleAvatars';

const IconBubbleOverlayInner: React.FC<{ icon: NearestIconInfo }> = ({ icon }) => {
    const { t } = useTranslation();
    const appUI = useAppUI();
    const ctrl = useControl();
    const spatialSound = useSpatialSound();
    const video360 = useVideo360();
    const cfg = icon.iconConfig;

    const bubbleText = t(cfg.greeting || '');

    const resolveConfigLine = (value: unknown) => {
        const s = String(value ?? '');
        if (!s) return '';
        return s.startsWith('interactions.') ? t(s) : s;
    };

    /** Video book proximity bubble: two-line CTA + Group 163 icon (see `interactions.icon_ipad`). */
    const isIpadVideoBookBubble = String(cfg.iconId || '') === 'ipad' && cfg.mediaType !== 'spatialSound';
    const isSpatialSoundBubble = cfg.mediaType === 'spatialSound';
    const isVr360Bubble = cfg.mediaType === 'video360';
    const isCoinPoiBubble = cfg.mediaType === 'coinPoi';

    const spatialBubbleLine1 = t('interactions.icon_headphones.bubbleLine1');
    const spatialLine2 = resolveConfigLine(cfg.soundTitle ?? cfg.title);
    const spatialBubbleAriaLabel =
        isSpatialSoundBubble && spatialLine2 ? `${spatialBubbleLine1} ${spatialLine2}` : undefined;

    const vrBubbleLine1 = t('interactions.icon_vr.bubbleLine1');
    const vrLine2 = resolveConfigLine(cfg.videoTitle ?? cfg.title);
    const vrBubbleAriaLabel =
        isVr360Bubble && vrLine2 ? `${vrBubbleLine1} ${vrLine2}` : undefined;

    const ipadBubbleLine1 = t('interactions.icon_ipad.bubbleLine1', 'Watch Video Book:');
    const ipadTitle = t(cfg.title || '');
    const ipadBubbleAriaLabel =
        isIpadVideoBookBubble && cfg.title ? `${ipadBubbleLine1} ${ipadTitle}` : undefined;

    /** POI coin proximity pill: localized title from metadata, else Kit label. */
    const coinTitle = useMemo(() => {
        if (!isCoinPoiBubble) return '';
        const md = (cfg.metadata && typeof cfg.metadata === 'object' ? cfg.metadata : {}) as Record<string, unknown>;
        const localized = resolvePoiLocalizedTitle(String(cfg.poiType || ''), md, t);
        return localized || String(cfg.title || cfg.displayName || '');
    }, [isCoinPoiBubble, cfg.metadata, cfg.poiType, cfg.title, cfg.displayName, cfg.mediaType, t]);
    const coinBubbleAriaLabel = isCoinPoiBubble && coinTitle ? coinTitle : undefined;

    const pillCtaLayout = isIpadVideoBookBubble || isSpatialSoundBubble || isVr360Bubble || isCoinPoiBubble;

    const iconSrc = useMemo(
        () => resolveIconBubbleAvatarUrl(cfg.iconImage || ''),
        [cfg.iconImage],
    );

    const handleClick = () => {
        if (cfg.mediaType === 'coinPoi') {
            ctrl.setCoinPoiPayload({
                poiType: String(cfg.poiType || ''),
                xformId: String(cfg.xformId || ''),
                coinType: String(cfg.coinType || ''),
                primPath: cfg.primPath ? String(cfg.primPath) : undefined,
                displayName: cfg.displayName ? String(cfg.displayName) : (coinTitle || undefined),
                labelIcon: cfg.labelIcon ? String(cfg.labelIcon) : undefined,
                metadata: (cfg.metadata && typeof cfg.metadata === 'object')
                    ? (cfg.metadata as Record<string, unknown>)
                    : {},
            });
            ctrl.setCoinPoiOpen(true);
            return;
        }
        if (cfg.mediaType === 'spatialSound') {
            spatialSound.open({
                id: String(cfg.iconId || ''),
                iconId: String(cfg.iconId || ''),
                title: String(cfg.title || ''),
                soundUrl: String(cfg.soundUrl || ''),
                soundTitle: String(cfg.soundTitle || ''),
                captionsUrl: cfg.captionsUrl ? String(cfg.captionsUrl) : undefined,
                primPath: cfg.primPath || undefined,
            });
            return;
        }
        if (cfg.mediaType === 'video360') {
            video360.open({
                id: String(cfg.iconId || ''),
                iconId: String(cfg.iconId || ''),
                title: String(cfg.title || ''),
                videoUrl: String(cfg.videoUrl || ''),
                videoTitle: String(cfg.videoTitle || ''),
                captionsUrl: cfg.captionsUrl ? String(cfg.captionsUrl) : undefined,
                primPath: cfg.primPath || undefined,
            });
            return;
        }
        /* Same flow as 3D ipad click (`videobook.open`): hero splash → auto-open player with full autoplay. */
        ctrl.setVideobookShowEntrySplash(true);
        ctrl.setVideobookEntry({
            id: String(cfg.iconId || ''),
            iconId: String(cfg.iconId || ''),
            title: String(cfg.title || ''),
            subtitle: String(cfg.subtitle || ''),
            videoUrl: String(cfg.videoUrl || ''),
            captionsUrl: cfg.captionsUrl ? String(cfg.captionsUrl) : undefined,
            chapters: Array.isArray(cfg.chapters) ? cfg.chapters : [],
        });
        ctrl.setVideobookOpen(true);
    };

    return (
        <div className={`icon-bubble-wrap${appUI.streamNavOverlayActive ? ' icon-bubble-wrap--automove' : ''}`}>
            <button
                type="button"
                tabIndex={appUI.streamNavOverlayActive ? -1 : 0}
                className={`icon-bubble-btn${pillCtaLayout ? ' icon-bubble-btn--videobook-cta' : ''}`}
                aria-label={ipadBubbleAriaLabel ?? spatialBubbleAriaLabel ?? vrBubbleAriaLabel ?? coinBubbleAriaLabel}
                onClick={handleClick}
            >
                <span className={`icon-bubble-avatar-wrap${isIpadVideoBookBubble ? ' icon-bubble-avatar-wrap--videobook' : ''}`} aria-hidden>
                    {iconSrc ? (
                        <img src={iconSrc} alt="" draggable={false} />
                    ) : (
                        <span className="icon-bubble-avatar-placeholder" />
                    )}
                </span>
                {isIpadVideoBookBubble ? (
                    <span className="icon-bubble-text icon-bubble-text--stack">
                        <span className="icon-bubble-text-line">{ipadBubbleLine1}</span>
                        <span className="icon-bubble-text-line">{ipadTitle}</span>
                    </span>
                ) : isSpatialSoundBubble ? (
                    <span className="icon-bubble-text icon-bubble-text--stack">
                        <span className="icon-bubble-text-line">{spatialBubbleLine1}</span>
                        <span className="icon-bubble-text-line">{spatialLine2}</span>
                    </span>
                ) : isVr360Bubble ? (
                    <span className="icon-bubble-text icon-bubble-text--stack">
                        <span className="icon-bubble-text-line">{vrBubbleLine1}</span>
                        <span className="icon-bubble-text-line">{vrLine2}</span>
                    </span>
                ) : isCoinPoiBubble ? (
                    <span className="icon-bubble-text">{coinTitle}</span>
                ) : (
                    <span className="icon-bubble-text">{bubbleText}</span>
                )}
            </button>
        </div>
    );
};

const IconBubbleOverlay: React.FC = () => {
    const ctrl = useControl();
    const stream = useStream();
    const spatialSound = useSpatialSound();
    const video360 = useVideo360();
    if (
        ctrl.avatarChatOpen ||
        stream.sceneLoading ||
        ctrl.nearestNpc ||
        !ctrl.nearestIcon ||
        ctrl.videobookOpen ||
        spatialSound.isOpen ||
        video360.isOpen
    ) {
        return null;
    }
    return <IconBubbleOverlayInner icon={ctrl.nearestIcon} />;
};

export default IconBubbleOverlay;
