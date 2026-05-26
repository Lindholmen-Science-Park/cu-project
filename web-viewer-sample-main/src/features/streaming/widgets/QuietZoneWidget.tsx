import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { PoiResult } from '../types';
import { useNavigation, useAppUI, useEnvironment } from '../contexts';
import { sendMessage } from '../messaging';
import demoCloseXUrl from '@icons/quiet-zone/X.svg';
import demoBellSlashUrl from '@icons/quiet-zone/BellSlash.svg';
import demoMapPinUrl from '@icons/quiet-zone/MapPinSimpleArea.svg';
import demoClockUrl from '@icons/quiet-zone/Clock.svg';
import sheetSignpostUrl from '@icons/restrooms/sheet-signpost.svg';
import sheetFeeUrl from '@icons/restrooms/sheet-fee.svg';
import sheetWheelchairDetailUrl from '@icons/restrooms/sheet-wheelchair-detail.svg';
import sheetSprayUrl from '@icons/restrooms/sheet-spray.svg';
import QuickLoadingOverlay from '../components/loading/QuickLoadingOverlay';
import { resolvePoiLocalizedTitle } from '../utils/poiLocalizedTitle';
import { useModalAccessibility } from '../hooks/useModalAccessibility';
import RouteErrorAlert from './RouteErrorAlert';
import './QuietZoneWidget.css';

function formatDistanceMeters(d: number): string {
    if (!Number.isFinite(d)) return '\u2014';
    if (d >= 1000) return `${(d / 1000).toFixed(1).replace('.', ',')} km`;
    return `${Math.round(d)} m`;
}

const CLEANING_SCHEDULE_I18N: Record<string, string> = {
    once_daily: 'search.poiCleaningOnceDaily',
    twice_daily: 'search.poiCleaningTwiceDaily',
};

function formatFee(fee: unknown, t: (k: string, o?: Record<string, unknown>) => string): string {
    if (typeof fee !== 'number') return '\u2014';
    return fee === 0 ? t('search.poiFeeFree') : t('search.poiFeeAmount', { amount: fee });
}

function formatCleaning(code: unknown, t: (k: string) => string): string {
    if (typeof code !== 'string') return '\u2014';
    const key = CLEANING_SCHEDULE_I18N[code];
    return key ? t(key) : String(code);
}

const QuietZoneWidget: React.FC = () => {
    const nav = useNavigation();
    const appUI = useAppUI();
    const env = useEnvironment();
    const { t } = useTranslation();
    const isBirdEye = env.currentCamera === 'bird_eye';
    const dialogRef = useRef<HTMLDivElement>(null);

    const {
        quietZoneResults: results,
        quietZonePoiListLoading,
        activeQuietZoneRouteId: activeRouteId,
        movingToQuietZoneId: movingToId,
        quietZoneWidgetOpen,
        quietZoneTrackingScreen,
        enterQuietZoneTrackingScreen,
        handleQuietZoneWidgetClose: onClose,
        handleQuietZoneClick: onItemClick,
        handleQuietZoneGetDirections: onGetDirections,
        handleQuietZoneMoveStop: onMoveStop,
        handlePoiTeleport: onTeleport,
        lastQuietZoneDisplayNameRef,
    } = nav;

    const widgetOpen =
        quietZoneWidgetOpen &&
        !quietZoneTrackingScreen &&
        !appUI.seatArrivalCelebrationVisible &&
        !appUI.poiArrivalVisible;
    useModalAccessibility(dialogRef, { enabled: widgetOpen });

    useEffect(() => {
        if (!widgetOpen) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [widgetOpen, onClose]);

    const sortedResults = useMemo(() => {
        const copy = [...results];
        copy.sort((a, b) => {
            const da = a.success ? (a.distanceMetersActual ?? a.distanceMetersBase) : Number.POSITIVE_INFINITY;
            const db = b.success ? (b.distanceMetersActual ?? b.distanceMetersBase) : Number.POSITIVE_INFINITY;
            return da - db;
        });
        return copy;
    }, [results]);

    const itemKey = (r: PoiResult, i: number) => {
        const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
        return (r.poiId || primPath || `poi_${i}`) as string;
    };

    const isMoving = !!movingToId;
    const quietRouteReady = nav.routeReadyByRouteId['quiet_zone_nav'] === true;
    const quietRouteError = nav.routeErrorByRouteId['quiet_zone_nav'];

    const activePrimPath = useMemo(() => {
        if (!activeRouteId) return '';
        for (let i = 0; i < sortedResults.length; i++) {
            const r = sortedResults[i];
            const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
            const key = r.poiId || primPath || `poi_${i}`;
            if (key === activeRouteId) return primPath;
        }
        return '';
    }, [activeRouteId, sortedResults]);

    const activeResult = useMemo(() => {
        if (!activeRouteId) return null;
        for (let i = 0; i < sortedResults.length; i++) {
            const r = sortedResults[i];
            const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
            const key = (r.poiId || primPath || `poi_${i}`) as string;
            if (key === activeRouteId) return r;
        }
        return null;
    }, [activeRouteId, sortedResults]);

    const sheetTitle = activeResult?.metadata
        ? resolvePoiLocalizedTitle('quiet_zone', activeResult.metadata as Record<string, unknown>, t)
            || t('search.findQuietArea')
        : t('search.findQuietArea');

    const dismissSheet = useCallback(() => {
        if (activePrimPath && activeRouteId) onItemClick(activePrimPath, activeRouteId);
    }, [activePrimPath, activeRouteId, onItemClick]);

    const showListLoadingOverlay = quietZonePoiListLoading;
    const showQuietEmpty = !quietZonePoiListLoading && sortedResults.length === 0;

    if (!widgetOpen) return null;

    return (
        <div
            ref={dialogRef}
            className={`cu-quiet-widget${activeRouteId ? ' cu-quiet-widget--sheet-open' : ''}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="cu-quiet-widget-title"
        >
            <header className="cu-quiet-widget__header">
                <h1 id="cu-quiet-widget-title" className="cu-quiet-widget__title">
                    {t('search.findQuietArea')}
                </h1>
                <button type="button" className="cu-quiet-widget__close" onClick={onClose} aria-label={t('people.closePanel')}>
                    <img src={demoCloseXUrl} alt="" className="cu-quiet-widget__close-img" width={23} height={23} />
                </button>
            </header>

            {quietRouteError ? (
                <RouteErrorAlert id="cu-quiet-route-error" error={quietRouteError} />
            ) : null}

            <div className="cu-quiet-widget__scroll">
                {showListLoadingOverlay ? (
                    <QuickLoadingOverlay
                        layout="embedded"
                        spinnerSize={140}
                        message={t('search.quietFinding')}
                    />
                ) : null}

                {showQuietEmpty ? (
                    <p className="cu-quiet-widget__empty">{t('search.quietEmpty')}</p>
                ) : (
                    <ul className="cu-quiet-widget__list">
                        {sortedResults.map((r, i) => {
                            const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
                            const key = itemKey(r, i);
                            const isActive = activeRouteId === key;
                            const dist = r.distanceMetersActual ?? r.distanceMetersBase;
                            const sec = r.estimatedTimeSecondsActual ?? r.estimatedTimeSecondsBase;
                            const title =
                                resolvePoiLocalizedTitle('quiet_zone', (r.metadata || {}) as Record<string, unknown>, t)
                                || t('search.quietAreaPlaceholder', { n: i + 1 });
                            const hideUnreachable = nav.navmeshMode === 'wheelchair';
                            if (hideUnreachable && !r.success) return null;
                            return (
                                <li key={key}>
                                    <button
                                        type="button"
                                        className={`cu-quiet-card${isActive ? ' cu-quiet-card--active' : ''}`}
                                        disabled={!r.success || !primPath}
                                        aria-describedby={!r.success ? `cu-quiet-card-error-${key}` : undefined}
                                        onClick={() => {
                                            if (!r.success || !primPath) return;
                                            const displayName =
                                                resolvePoiLocalizedTitle('quiet_zone', (r.metadata || {}) as Record<string, unknown>, t)
                                                || t('search.quietAreaPlaceholder', { n: i + 1 });
                                            lastQuietZoneDisplayNameRef.current = displayName;
                                            // Bird-eye: skip the FP route (PlayerCharacter is the
                                            // orbit camera, not on the navmesh) and reuse the same
                                            // bottom sheet flow as the Foyer / arena map markers —
                                            // Get directions draws the dashed bird-eye polyline +
                                            // opens MapMarkerDirectionsPanel; Teleport me there
                                            // fades to first-person and dispatches `poiTeleport`.
                                            if (isBirdEye) {
                                                onClose();
                                                nav.openMapMarkerSheet({
                                                    id: key,
                                                    title: displayName,
                                                    spawnPoint: '',
                                                    primPath,
                                                    isAccessible: r.metadata?.is_accessible === true,
                                                    useNavmeshPoiTeleport: true,
                                                });
                                                // Show the destination flag immediately so the user knows
                                                // where the POI is on the bird-eye map before "Get
                                                // directions". The pin is cleared on sheet dismiss
                                                // (birdEyePinDismiss) or replaced by the route's
                                                // destination bubble on Get directions.
                                                try { sendMessage('birdEyePinShowAtPrim', { primPath }); } catch { /* ignore */ }
                                                return;
                                            }
                                            onItemClick(primPath, key);
                                        }}
                                    >
                                        <div className="cu-quiet-card__icon-wrap">
                                            <div className="cu-quiet-card__icon-circle">
                                                <img src={demoBellSlashUrl} alt="" width={32} height={32} />
                                            </div>
                                        </div>
                                        <div className="cu-quiet-card__body">
                                            <div className="cu-quiet-card__title">{title}</div>
                                            {r.success ? (
                                                <div className="cu-quiet-card__meta">
                                                    <span className="cu-quiet-card__meta-item">
                                                        <img src={demoMapPinUrl} alt="" className="cu-quiet-card__meta-icon" width={16} height={16} />
                                                        {formatDistanceMeters(dist)}
                                                    </span>
                                                    <span className="cu-quiet-card__meta-item">
                                                        <img src={demoClockUrl} alt="" className="cu-quiet-card__meta-icon" width={16} height={16} />
                                                        {sec < 60
                                                            ? t('search.toiletSecAway', { count: Math.max(1, Math.round(sec)) })
                                                            : t('search.toiletMinAway', { count: Math.round(sec / 60) })}
                                                    </span>
                                                </div>
                                            ) : (
                                                <span
                                                    id={`cu-quiet-card-error-${key}`}
                                                    className="sr-only"
                                                    role="alert"
                                                    aria-live="assertive"
                                                >
                                                    {r.error || t('search.toiletUnreachable')}
                                                </span>
                                            )}
                                        </div>
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>

            {activeRouteId && activeResult && (
                <>
                    <button
                        type="button"
                        className="cu-quiet-widget__sheet-backdrop"
                        aria-label={t('search.quietDismissSheet')}
                        onClick={dismissSheet}
                    />
                    <div className="cu-quiet-widget__sheet" role="region" aria-labelledby="cu-quiet-sheet-title">
                        <div className="cu-quiet-widget__sheet-handle" aria-hidden />
                        <div className="cu-quiet-widget__sheet-head">
                            <h2 id="cu-quiet-sheet-title" className="cu-quiet-widget__sheet-title">
                                {sheetTitle}
                            </h2>
                            <button
                                type="button"
                                className="cu-quiet-widget__sheet-close"
                                onClick={dismissSheet}
                                aria-label={t('people.closePanel')}
                            >
                                <img src={demoCloseXUrl} alt="" className="cu-quiet-widget__sheet-close-img" width={23} height={23} />
                            </button>
                        </div>
                        <div className="cu-quiet-widget__sheet-actions">
                            <button
                                type="button"
                                className={`cu-quiet-widget__btn ${isMoving ? 'cu-quiet-widget__btn--stop' : 'cu-quiet-widget__btn--go'}`}
                                disabled={!isMoving && quietZoneTrackingScreen && !quietRouteReady}
                                title={
                                    !isMoving && quietZoneTrackingScreen && !quietRouteReady
                                        ? t('search.poiWaitForRoute')
                                        : undefined
                                }
                                onClick={() => {
                                    if (isMoving) onMoveStop();
                                    else {
                                        if (activePrimPath && activeRouteId) {
                                            onGetDirections(activePrimPath, activeRouteId, sheetTitle);
                                        }
                                        enterQuietZoneTrackingScreen();
                                    }
                                }}
                            >
                                {!isMoving && (
                                    <img
                                        src={sheetSignpostUrl}
                                        alt=""
                                        className="cu-quiet-widget__btn-lead-icon"
                                        width={20}
                                        height={20}
                                    />
                                )}
                                {isMoving ? t('common.stop') : t('search.toiletGetDirections')}
                            </button>
                            {activePrimPath ? (
                                <button
                                    type="button"
                                    className="cu-quiet-widget__btn cu-quiet-widget__btn--tele"
                                    onClick={() => {
                                        try { sendMessage('navmeshRouteStop', { routeId: 'quiet_zone_nav' }); } catch { /* ignore */ }
                                        onTeleport(activePrimPath);
                                    }}
                                >
                                    {t('search.toiletTeleportThere')}
                                </button>
                            ) : null}
                        </div>
                        <div className="cu-quiet-widget__sheet-info">
                            <div className="cu-quiet-widget__sheet-info-row">
                                <img src={sheetFeeUrl} alt="" className="cu-quiet-widget__sheet-info-icon" width={16} height={16} />
                                <span className="cu-quiet-widget__sheet-info-label">{t('search.toiletInfoFee')}</span>
                                <span className="cu-quiet-widget__sheet-info-value">{formatFee(activeResult.metadata?.fee, t)}</span>
                            </div>
                            <div className="cu-quiet-widget__sheet-info-row">
                                <img src={sheetWheelchairDetailUrl} alt="" className="cu-quiet-widget__sheet-info-icon" width={16} height={16} />
                                <span className="cu-quiet-widget__sheet-info-label">{t('search.toiletInfoAccessible')}</span>
                                <span className="cu-quiet-widget__sheet-info-value">
                                    {activeResult.metadata?.is_accessible ? t('search.toiletInfoAccessibleYes') : t('search.toiletInfoAccessibleNo')}
                                </span>
                            </div>
                            <div className="cu-quiet-widget__sheet-info-row">
                                <img src={sheetSprayUrl} alt="" className="cu-quiet-widget__sheet-info-icon" width={16} height={16} />
                                <span className="cu-quiet-widget__sheet-info-label">{t('search.toiletInfoCleaning')}</span>
                                <span className="cu-quiet-widget__sheet-info-value">{formatCleaning(activeResult.metadata?.cleaning_schedule, t)}</span>
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
};

export default QuietZoneWidget;
