/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import InteractionButtons from './components/InteractionButtons';
import ChatWidget from './components/ChatWidget';
import seatNavPlayIcon from '@icons/seat-route/figma-5706-play.svg';
import seatNavPauseIcon from '@icons/seat-route/figma-april-pause.svg';
import StreamCloseXIcon from '@icons/seat-route/StreamCloseXIcon';
import FlagPennantIcon from '@icons/seat-navigation/FlagPennantIcon';
import NavArrivalCheckIcon from '@icons/seat-navigation/NavArrivalCheckIcon';
import SeatNavSpeakerMutedIcon from '@icons/seat-route/SeatNavSpeakerMutedIcon';
import { MediaVolumeOnIcon } from '../cu/controls/MediaPlayerControls';
import clockSvg from '@icons/seat-route/clock.svg';
import distanceSvg from '@icons/seat-route/distance.svg';
import mapPinSimpleAreaSvg from '@icons/seat-route/map-pin-simple-area.svg';
import arrowElbowUpRightSvg from '@icons/seat-route/arrow-elbow-up-right.svg';
import seatArrivalCelebrationImg from './assets/seat-arrival-celebration.png';
import {
    formatSeatLabel,
    formatSeatNavTimeRemainingLabel,
    seatNavigationPillText,
} from './seatNavigationLabels';
import type { SeatNavigationOverlayProps } from './appStreamTypes';

export interface AppStreamSeatOverlaysProps {
    isViewer: boolean;
    streamReady: boolean;
    handleCustomEvent: (event: any) => void;
    seatRouteStreamAudioMuted: boolean;
    setSeatRouteStreamAudioMuted: React.Dispatch<React.SetStateAction<boolean>>;
    seatArrivalCelebrationVisible: boolean;
    seatArrivalLabel: string | null;
    onArrivalDismiss?: () => void;
    poiArrivalVisible: boolean;
    poiArrivalLabel: string | null;
    onPoiArrivalDismiss?: () => void;
    seatNavigationOverlay: SeatNavigationOverlayProps | null;
}

const AppStreamSeatOverlays: React.FC<AppStreamSeatOverlaysProps> = ({
    isViewer,
    streamReady,
    handleCustomEvent,
    seatRouteStreamAudioMuted,
    setSeatRouteStreamAudioMuted,
    seatArrivalCelebrationVisible,
    seatArrivalLabel,
    onArrivalDismiss,
    poiArrivalVisible,
    poiArrivalLabel,
    onPoiArrivalDismiss,
    seatNavigationOverlay,
}) => {
    const { t } = useTranslation();

    return (
        <>
            {!isViewer && seatArrivalCelebrationVisible && (
                <div className="stream-seat-arrival-celebration" aria-hidden="true">
                    <img src={seatArrivalCelebrationImg} alt="" draggable={false} />
                </div>
            )}

            {!isViewer && seatArrivalCelebrationVisible && seatArrivalLabel && (
                <div className="stream-seat-nav-info">
                    <div className="stream-seat-nav-info__shell">
                        <div className="stream-seat-nav-info__route-row">
                            <div className="stream-seat-nav-info__header-row">
                                <div className="stream-seat-nav-info__title-block">
                                    <NavArrivalCheckIcon className="stream-seat-nav-info__route-flag" />
                                    <div className="cu-seat-panel__status">
                                        {formatSeatLabel(seatArrivalLabel, t)}
                                    </div>
                                </div>
                                <div className="stream-seat-nav-info__actions">
                                    <button
                                        type="button"
                                        className={`stream-seat-nav-info__speaker${
                                            seatRouteStreamAudioMuted
                                                ? ' stream-seat-nav-info__speaker--muted'
                                                : ''
                                        }`}
                                        aria-label={
                                            seatRouteStreamAudioMuted
                                                ? t('seat.unmuteAudio')
                                                : t('seat.muteAudio')
                                        }
                                        aria-pressed={seatRouteStreamAudioMuted}
                                        onClick={() => {
                                            const a = document.getElementById(
                                                'remote-audio',
                                            ) as HTMLAudioElement | null;
                                            if (!a) return;
                                            a.muted = !a.muted;
                                            setSeatRouteStreamAudioMuted(a.muted);
                                        }}
                                    >
                                        {seatRouteStreamAudioMuted ? (
                                            <SeatNavSpeakerMutedIcon />
                                        ) : (
                                            <MediaVolumeOnIcon className="stream-seat-nav-info__speaker-icon" />
                                        )}
                                    </button>
                                    <button
                                        type="button"
                                        className="stream-seat-nav-info__close"
                                        title={t('seat.dismissArrival')}
                                        aria-label={t('seat.dismissArrival')}
                                        onClick={() => onArrivalDismiss?.()}
                                    >
                                        <StreamCloseXIcon className="stream-seat-nav-info__close-icon" />
                                    </button>
                                </div>
                            </div>
                            <div className="stream-seat-nav-info__arrival-pill">{t('seat.arrived')}</div>
                        </div>
                    </div>
                </div>
            )}

            {!isViewer && poiArrivalVisible && poiArrivalLabel && (
                <div className="stream-seat-nav-info">
                    <div className="stream-seat-nav-info__shell">
                        <div className="stream-seat-nav-info__route-row">
                            <div className="stream-seat-nav-info__header-row">
                                <div className="stream-seat-nav-info__title-block">
                                    <NavArrivalCheckIcon className="stream-seat-nav-info__route-flag" />
                                    <div className="cu-seat-panel__status">{poiArrivalLabel}</div>
                                </div>
                                <div className="stream-seat-nav-info__actions">
                                    <button
                                        type="button"
                                        className={`stream-seat-nav-info__speaker${
                                            seatRouteStreamAudioMuted
                                                ? ' stream-seat-nav-info__speaker--muted'
                                                : ''
                                        }`}
                                        aria-label={
                                            seatRouteStreamAudioMuted
                                                ? t('seat.unmuteAudio')
                                                : t('seat.muteAudio')
                                        }
                                        aria-pressed={seatRouteStreamAudioMuted}
                                        onClick={() => {
                                            const a = document.getElementById(
                                                'remote-audio',
                                            ) as HTMLAudioElement | null;
                                            if (!a) return;
                                            a.muted = !a.muted;
                                            setSeatRouteStreamAudioMuted(a.muted);
                                        }}
                                    >
                                        {seatRouteStreamAudioMuted ? (
                                            <SeatNavSpeakerMutedIcon />
                                        ) : (
                                            <MediaVolumeOnIcon className="stream-seat-nav-info__speaker-icon" />
                                        )}
                                    </button>
                                    <button
                                        type="button"
                                        className="stream-seat-nav-info__close"
                                        title={t('seat.dismissArrival')}
                                        aria-label={t('seat.dismissArrival')}
                                        onClick={() => onPoiArrivalDismiss?.()}
                                    >
                                        <StreamCloseXIcon className="stream-seat-nav-info__close-icon" />
                                    </button>
                                </div>
                            </div>
                            <div className="stream-seat-nav-info__arrival-pill">{t('seat.arrived')}</div>
                        </div>
                    </div>
                </div>
            )}

            {!isViewer && !seatArrivalCelebrationVisible && !poiArrivalVisible && (
                <>
                    <InteractionButtons isActive={streamReady} onCustomEvent={handleCustomEvent} />
                    <ChatWidget isActive={streamReady} onCustomEvent={handleCustomEvent} />
                </>
            )}

            {seatNavigationOverlay && !isViewer && !seatArrivalCelebrationVisible && !poiArrivalVisible && (
                <>
                    <div
                        className="stream-seat-nav-info"
                        role="navigation"
                        aria-label={t('seat.navigationRoute')}
                    >
                        <div className="stream-seat-nav-info__shell">
                            <div className="stream-seat-nav-info__route-row">
                                <div className="stream-seat-nav-info__header-row">
                                    <div className="stream-seat-nav-info__title-block">
                                        <FlagPennantIcon className="stream-seat-nav-info__route-flag" />
                                        <div className="cu-seat-panel__status">
                                            {seatNavigationOverlay.displayLabel ??
                                                formatSeatLabel(seatNavigationOverlay.seatLabel, t)}
                                        </div>
                                    </div>
                                    <div className="stream-seat-nav-info__actions">
                                        <button
                                            type="button"
                                            className={`stream-seat-nav-info__speaker${
                                                seatRouteStreamAudioMuted
                                                    ? ' stream-seat-nav-info__speaker--muted'
                                                    : ''
                                            }`}
                                            aria-label={
                                                seatRouteStreamAudioMuted
                                                    ? t('seat.unmuteAudio')
                                                    : t('seat.muteAudio')
                                            }
                                            aria-pressed={seatRouteStreamAudioMuted}
                                            onClick={() => {
                                                const a = document.getElementById(
                                                    'remote-audio',
                                                ) as HTMLAudioElement | null;
                                                if (!a) return;
                                                a.muted = !a.muted;
                                                setSeatRouteStreamAudioMuted(a.muted);
                                            }}
                                        >
                                            {seatRouteStreamAudioMuted ? (
                                                <SeatNavSpeakerMutedIcon />
                                            ) : (
                                                <MediaVolumeOnIcon className="stream-seat-nav-info__speaker-icon" />
                                            )}
                                        </button>
                                        <button
                                            type="button"
                                            className="stream-seat-nav-info__close"
                                            title={t('seat.closeSeatRoute')}
                                            aria-label={t('seat.closeSeatRoute')}
                                            onClick={() => seatNavigationOverlay.onDismiss()}
                                        >
                                            <StreamCloseXIcon className="stream-seat-nav-info__close-icon" />
                                        </button>
                                    </div>
                                </div>
                                <div
                                    className="stream-seat-nav-info__metrics-block"
                                    aria-live="polite"
                                    aria-atomic="false"
                                >
                                    {(() => {
                                        const rmEnabled =
                                            seatNavigationOverlay.routeMeasureEnabled !== false;
                                        const rm = seatNavigationOverlay.routeMeasure;
                                        const hasMeasure =
                                            rmEnabled &&
                                            rm?.success &&
                                            (rm.distanceMetersBase > 0 ||
                                                (rm.distanceMetersActual ?? 0) > 0);
                                        if (!hasMeasure || !rm) return null;
                                        const secondsLeft =
                                            rm.estimatedTimeSecondsActual ?? rm.estimatedTimeSecondsBase;
                                        const metersLeft = Math.max(
                                            1,
                                            Math.round(
                                                rm.distanceMetersActual ?? rm.distanceMetersBase,
                                            ),
                                        );
                                        return (
                                            <div className="cu-seat-panel__measure">
                                                <div className="stream-seat-nav-info__metric-list">
                                                    <div className="stream-seat-nav-info__metric-row">
                                                        <img
                                                            src={clockSvg}
                                                            alt=""
                                                            className="stream-seat-nav-info__metric-icon"
                                                            width={16}
                                                            height={16}
                                                            draggable={false}
                                                        />
                                                        <span className="stream-seat-nav-info__metric-text">
                                                            {formatSeatNavTimeRemainingLabel(secondsLeft, t)}
                                                        </span>
                                                    </div>
                                                    <div className="stream-seat-nav-info__metric-row">
                                                        <img
                                                            src={distanceSvg}
                                                            alt=""
                                                            className="stream-seat-nav-info__metric-icon"
                                                            width={16}
                                                            height={16}
                                                            draggable={false}
                                                        />
                                                        <span className="stream-seat-nav-info__metric-text">
                                                            {t('seat.metersLeft', { count: metersLeft })}
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })()}
                                </div>
                                {(() => {
                                    const rmEnabled =
                                        seatNavigationOverlay.routeMeasureEnabled !== false;
                                    const rm = seatNavigationOverlay.routeMeasure;
                                    if (!rmEnabled || !rm) return null;
                                    const pillText = seatNavigationPillText(
                                        rm,
                                        t,
                                        !!seatNavigationOverlay.approachUsesGenericLabel,
                                    );
                                    if (!pillText) return null;
                                    const act = rm.navigationNextAction;
                                    const firstStep = rm.navigationSteps?.[0];
                                    const showPin =
                                        act === 'approach' ||
                                        (!act && firstStep?.action === 'approach');
                                    const iconClass = showPin
                                        ? 'stream-seat-nav-info__turns-icon'
                                        : act === 'turn_left'
                                          ? 'stream-seat-nav-info__turns-icon stream-seat-nav-info__turns-icon--mirror'
                                          : 'stream-seat-nav-info__turns-icon';
                                    return (
                                        <div
                                            className="stream-seat-nav-info__turns-hint"
                                            aria-live="polite"
                                            aria-atomic="true"
                                            aria-label={pillText}
                                        >
                                            <img
                                                src={showPin ? mapPinSimpleAreaSvg : arrowElbowUpRightSvg}
                                                alt=""
                                                className={iconClass}
                                                width={24}
                                                height={24}
                                                draggable={false}
                                            />
                                            <span className="stream-seat-nav-info__turns-text">{pillText}</span>
                                        </div>
                                    );
                                })()}
                                <div
                                    id="stream-seat-nav-cu-controls-root"
                                    className="stream-seat-nav-info__cu-slot"
                                />
                            </div>
                        </div>
                    </div>
                    <div className="stream-seat-nav-overlay" role="presentation">
                        <button
                            type="button"
                            className="stream-seat-nav-overlay__btn"
                            onClick={() =>
                                seatNavigationOverlay.isMoving
                                    ? seatNavigationOverlay.onStop()
                                    : seatNavigationOverlay.onPlay()
                            }
                            title={
                                seatNavigationOverlay.isMoving
                                    ? t('seat.pauseMovement')
                                    : t('seat.moveTo', {
                                          label:
                                              seatNavigationOverlay.displayLabel ??
                                              formatSeatLabel(seatNavigationOverlay.seatLabel, t),
                                      })
                            }
                            aria-label={
                                seatNavigationOverlay.isMoving
                                    ? 'Pause navigation'
                                    : t('seat.playMoveTo', {
                                          label:
                                              seatNavigationOverlay.displayLabel ??
                                              formatSeatLabel(seatNavigationOverlay.seatLabel, t),
                                      })
                            }
                        >
                            <img
                                src={
                                    seatNavigationOverlay.isMoving ? seatNavPauseIcon : seatNavPlayIcon
                                }
                                alt=""
                                width={32}
                                height={32}
                                draggable={false}
                                className="stream-seat-nav-overlay__icon"
                            />
                        </button>
                    </div>
                </>
            )}
        </>
    );
};

export default AppStreamSeatOverlays;
