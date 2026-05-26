import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PoiResult } from '../types';
import { useNavigation, useAppUI, useEnvironment } from '../contexts';
import { sendMessage } from '../messaging';
import closeXUrl from '@icons/restrooms/close-x.svg';
import filterBarCloseUrl from '@icons/restrooms/filter-bar-close.svg';
import filterTypeUnisexUrl from '@icons/restrooms/filter-type-unisex.svg';
import filterTypeMenUrl from '@icons/restrooms/filter-type-men.svg';
import filterTypeWomenUrl from '@icons/restrooms/filter-type-women.svg';
import filterTypeWheelchairUrl from '@icons/restrooms/filter-type-wheelchair.svg';
import filterTypeBabyChangingUrl from '@icons/restrooms/filter-type-baby-changing.svg';
import toiletsPublicUrl from '@icons/restrooms/toilets-public.svg';
import wheelchairGlyphUrl from '@icons/restrooms/wheelchair-glyph.svg';
import mapPinUrl from '@icons/restrooms/map-pin.svg';
import clockUrl from '@icons/restrooms/clock.svg';
import sheetSignpostUrl from '@icons/restrooms/sheet-signpost.svg';
import sheetFeeUrl from '@icons/restrooms/sheet-fee.svg';
import sheetWheelchairDetailUrl from '@icons/restrooms/sheet-wheelchair-detail.svg';
import sheetSprayUrl from '@icons/restrooms/sheet-spray.svg';
import funnelUrl from '@icons/restrooms/funnel.svg';
import QuickLoadingOverlay from '../components/loading/QuickLoadingOverlay';
import { resolvePoiLocalizedTitle } from '../utils/poiLocalizedTitle';
import { useModalAccessibility } from '../hooks/useModalAccessibility';
import RouteErrorAlert from './RouteErrorAlert';
import './RestroomWidget.css';

/** Unfiltered list shows only the nearest N; filters search the full Kit result set. */
const RESTROOM_DEFAULT_LIST_LIMIT = 10;

const RESTROOM_FILTER_KEYS = ['unisex', 'men', 'accessible', 'women', 'baby'] as const;
type RestroomFilterKey = (typeof RESTROOM_FILTER_KEYS)[number];

const RESTROOM_FILTER_I18N: Record<RestroomFilterKey, string> = {
    unisex: 'search.toiletFilterUnisex',
    men: 'search.toiletFilterMen',
    accessible: 'search.toiletFilterAccessible',
    women: 'search.toiletFilterWomen',
    baby: 'search.toiletFilterBaby',
};

const RESTROOM_FILTER_TYPE_ICON_SRC: Record<RestroomFilterKey, string> = {
    unisex: filterTypeUnisexUrl,
    men: filterTypeMenUrl,
    women: filterTypeWomenUrl,
    accessible: filterTypeWheelchairUrl,
    baby: filterTypeBabyChangingUrl,
};

function poiMatchesFilter(r: PoiResult, key: RestroomFilterKey): boolean {
    const m = r.metadata;
    if (!m) return false;
    switch (key) {
        case 'men':
            return m.for_men === true && m.for_women !== true && m.is_unisex !== true;
        case 'women':
            return m.for_women === true && m.for_men !== true && m.is_unisex !== true;
        case 'unisex':
            return m.is_unisex === true;
        case 'accessible':
            return m.is_accessible === true;
        case 'baby':
            return m.has_changing_table === true;
        default:
            return false;
    }
}

function cardGlyphUrl(r: PoiResult): string {
    return r.metadata?.is_accessible ? wheelchairGlyphUrl : toiletsPublicUrl;
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

function RestroomFilterTypeIcon({ filterKey }: { filterKey: RestroomFilterKey }) {
    const cls = 'cu-restroom-widget__filter-type-icon';
    const src = RESTROOM_FILTER_TYPE_ICON_SRC[filterKey];
    return <img src={src} alt="" className={cls} width={24} height={24} />;
}

function formatDistanceMeters(d: number): string {
    if (!Number.isFinite(d)) return '\u2014';
    if (d >= 1000) return `${(d / 1000).toFixed(1).replace('.', ',')} km`;
    return `${Math.round(d)} m`;
}

const RestroomWidget: React.FC = () => {
    const nav = useNavigation();
    const appUI = useAppUI();
    const env = useEnvironment();
    const { t } = useTranslation();
    const isBirdEye = env.currentCamera === 'bird_eye';
    const dialogRef = useRef<HTMLDivElement>(null);

    const {
        restroomResults: results,
        restroomPoiListLoading,
        activePoiRouteId: activeRouteId,
        movingToPoiId: movingToId,
        restroomTrackingScreen,
        enterRestroomTrackingScreen,
        handleRestroomWidgetClose: onClose,
        handlePoiClick: onItemClick,
        handlePoiGetDirections: onGetDirections,
        handlePoiMoveStop: onMoveStop,
        handlePoiTeleport: onTeleport,
        lastPoiDisplayNameRef,
    } = nav;
    const [activeFilterKeys, setActiveFilterKeys] = useState<RestroomFilterKey[]>([]);
    const [filterPanelOpen, setFilterPanelOpen] = useState(false);
    const restroomWidgetWasOpenRef = useRef(false);

    const widgetOpen =
        nav.restroomWidgetOpen &&
        !restroomTrackingScreen &&
        !appUI.seatArrivalCelebrationVisible &&
        !appUI.poiArrivalVisible;
    useModalAccessibility(dialogRef, { enabled: widgetOpen });

    useEffect(() => {
        if (nav.restroomWidgetOpen && !restroomWidgetWasOpenRef.current) {
            setActiveFilterKeys([]);
            setFilterPanelOpen(false);
        }
        restroomWidgetWasOpenRef.current = nav.restroomWidgetOpen;
    }, [nav.restroomWidgetOpen]);

    useEffect(() => {
        if (!filterPanelOpen) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setFilterPanelOpen(false);
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [filterPanelOpen]);

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && !filterPanelOpen) onClose();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [onClose, filterPanelOpen]);

    const sortedResults = useMemo(() => {
        const copy = [...results];
        copy.sort((a, b) => {
            const da = a.success ? (a.distanceMetersActual ?? a.distanceMetersBase) : Number.POSITIVE_INFINITY;
            const db = b.success ? (b.distanceMetersActual ?? b.distanceMetersBase) : Number.POSITIVE_INFINITY;
            return da - db;
        });
        return copy;
    }, [results]);

    const displayResults = useMemo(() => {
        const filtered =
            activeFilterKeys.length === 0
                ? sortedResults
                : sortedResults.filter((r) => activeFilterKeys.some((k) => poiMatchesFilter(r, k)));
        if (activeFilterKeys.length === 0) {
            return filtered.slice(0, RESTROOM_DEFAULT_LIST_LIMIT);
        }
        return filtered;
    }, [sortedResults, activeFilterKeys]);

    const toggleFilterKey = useCallback((key: RestroomFilterKey) => {
        setActiveFilterKeys((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
    }, []);

    const selectAllFilters = useCallback(() => {
        setActiveFilterKeys([...RESTROOM_FILTER_KEYS]);
    }, []);

    const resetFilters = useCallback(() => {
        setActiveFilterKeys([]);
    }, []);

    const itemKey = (r: PoiResult, i: number) => {
        const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
        return (r.poiId || primPath || `poi_${i}`) as string;
    };

    const isMoving = !!movingToId;

    const poiRouteReady = nav.routeReadyByRouteId['poi_nav'] === true;
    const poiRouteError = nav.routeErrorByRouteId['poi_nav'];

    const activePrimPath = useMemo(() => {
        if (!activeRouteId) return '';
        for (let i = 0; i < displayResults.length; i++) {
            const r = displayResults[i];
            const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
            const key = r.poiId || primPath || `poi_${i}`;
            if (key === activeRouteId) return primPath;
        }
        return '';
    }, [activeRouteId, displayResults]);

    const activeResult = useMemo(() => {
        if (!activeRouteId) return null;
        for (let i = 0; i < displayResults.length; i++) {
            const r = displayResults[i];
            const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
            const key = (r.poiId || primPath || `poi_${i}`) as string;
            if (key === activeRouteId) return r;
        }
        return null;
    }, [activeRouteId, displayResults]);

    const sheetTitle = activeResult?.metadata
        ? resolvePoiLocalizedTitle('restroom', activeResult.metadata as Record<string, unknown>, t)
            || t('search.findToilet')
        : t('search.findToilet');

    const dismissSheet = useCallback(() => {
        if (activePrimPath && activeRouteId) onItemClick(activePrimPath, activeRouteId);
    }, [activePrimPath, activeRouteId, onItemClick]);

    const showListLoadingOverlay = restroomPoiListLoading;
    const showRestroomEmpty = !restroomPoiListLoading && sortedResults.length === 0;
    const filterNoMatch =
        !restroomPoiListLoading &&
        sortedResults.length > 0 &&
        displayResults.length === 0 &&
        activeFilterKeys.length > 0;

    const filterSummaryText = useMemo(
        () => activeFilterKeys.map((k) => t(RESTROOM_FILTER_I18N[k])).join(', '),
        [activeFilterKeys, t],
    );

    const filterAnchorRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!filterPanelOpen) return;
        const onDoc = (e: MouseEvent) => {
            if (filterAnchorRef.current && !filterAnchorRef.current.contains(e.target as Node)) {
                setFilterPanelOpen(false);
            }
        };
        document.addEventListener('mousedown', onDoc);
        return () => document.removeEventListener('mousedown', onDoc);
    }, [filterPanelOpen]);

    if (!widgetOpen) return null;

    return (
        <div
            ref={dialogRef}
            className={`cu-restroom-widget${activeRouteId ? ' cu-restroom-widget--sheet-open' : ''}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="cu-restroom-widget-title"
        >
            <header className="cu-restroom-widget__header">
                <h1 id="cu-restroom-widget-title" className="cu-restroom-widget__title">
                    {t('search.findToilet')}
                </h1>
                <button type="button" className="cu-restroom-widget__close" onClick={onClose} aria-label={t('people.closePanel')}>
                    <img src={closeXUrl} alt="" className="cu-restroom-widget__close-img" width={23} height={23} />
                </button>
            </header>

            {poiRouteError ? (
                <RouteErrorAlert id="cu-restroom-route-error" error={poiRouteError} />
            ) : null}

            <div className="cu-restroom-widget__filter-slot">
                <div
                    ref={filterAnchorRef}
                    className={`cu-restroom-widget__filter-wrap${filterPanelOpen ? ' cu-restroom-widget__filter-wrap--open' : ''}`}
                >
                    <button
                        type="button"
                        id="cu-restroom-filter-trigger"
                        className="cu-restroom-widget__filter-bar"
                        aria-expanded={filterPanelOpen}
                        aria-haspopup="dialog"
                        aria-controls="cu-restroom-filter-popover"
                        onClick={() => setFilterPanelOpen((o) => !o)}
                    >
                        <span className="cu-restroom-widget__filter-bar-main">
                            <span
                                id={filterPanelOpen ? 'cu-restroom-filter-popover-title' : undefined}
                                className={`cu-restroom-widget__filter-bar-text${
                                    filterPanelOpen || activeFilterKeys.length === 0
                                        ? ' cu-restroom-widget__filter-bar-text--title'
                                        : ''
                                }`}
                            >
                                {filterPanelOpen || activeFilterKeys.length === 0
                                    ? t('search.toiletFilterBy')
                                    : filterSummaryText}
                            </span>
                        </span>
                        <span className="cu-restroom-widget__filter-bar-trail">
                            {filterPanelOpen ? (
                                <img
                                    src={filterBarCloseUrl}
                                    alt=""
                                    className="cu-restroom-widget__filter-bar-icon cu-restroom-widget__filter-bar-icon--close"
                                    width={23}
                                    height={23}
                                />
                            ) : (
                                <img src={funnelUrl} alt="" className="cu-restroom-widget__filter-bar-icon" width={24} height={24} />
                            )}
                        </span>
                    </button>
                    {filterPanelOpen ? (
                        <div
                            id="cu-restroom-filter-popover"
                            className="cu-restroom-widget__filter-popover"
                            role="dialog"
                            aria-modal="false"
                            aria-labelledby="cu-restroom-filter-popover-title"
                        >
                            <ul className="cu-restroom-widget__filter-row-list">
                                {RESTROOM_FILTER_KEYS.map((key) => {
                                    const checked = activeFilterKeys.includes(key);
                                    return (
                                        <li
                                            key={key}
                                            className={`cu-restroom-widget__filter-row-item${checked ? ' cu-restroom-widget__filter-row-item--checked' : ''}`}
                                        >
                                            <label className="cu-restroom-widget__filter-row">
                                                <input
                                                    type="checkbox"
                                                    className="cu-restroom-widget__filter-check"
                                                    checked={checked}
                                                    onChange={() => toggleFilterKey(key)}
                                                />
                                                <span className="cu-restroom-widget__filter-row-label">{t(RESTROOM_FILTER_I18N[key])}</span>
                                                <span className="cu-restroom-widget__filter-row-icon" aria-hidden>
                                                    <RestroomFilterTypeIcon filterKey={key} />
                                                </span>
                                            </label>
                                        </li>
                                    );
                                })}
                            </ul>
                            <div className="cu-restroom-widget__filter-popover-actions">
                                <button type="button" className="cu-restroom-widget__filter-footer-btn" onClick={selectAllFilters}>
                                    {t('search.toiletFilterSelectAll')}
                                </button>
                                <button type="button" className="cu-restroom-widget__filter-footer-btn" onClick={resetFilters}>
                                    {t('search.toiletFilterReset')}
                                </button>
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>

            <div className="cu-restroom-widget__scroll">
                {showListLoadingOverlay ? (
                    <QuickLoadingOverlay
                        layout="embedded"
                        spinnerSize={140}
                        message={t('search.toiletFinding')}
                    />
                ) : null}

                {filterNoMatch ? (
                    <p className="cu-restroom-widget__empty">{t('search.toiletFilterNoMatch')}</p>
                ) : showRestroomEmpty ? (
                    <p className="cu-restroom-widget__empty">{t('search.toiletEmpty')}</p>
                ) : (
                    <ul className="cu-restroom-widget__list">
                        {displayResults.map((r, i) => {
                            const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
                            const key = itemKey(r, i);
                            const isActive = activeRouteId === key;
                            const dist = r.distanceMetersActual ?? r.distanceMetersBase;
                            const sec = r.estimatedTimeSecondsActual ?? r.estimatedTimeSecondsBase;
                            const glyphSrc = cardGlyphUrl(r);
                            const title =
                                resolvePoiLocalizedTitle('restroom', (r.metadata || {}) as Record<string, unknown>, t)
                                || t('search.toiletSection', { n: i + 1 });
                            return (
                                <li key={key}>
                                    <button
                                        type="button"
                                        className={`cu-restroom-card${isActive ? ' cu-restroom-card--active' : ''}`}
                                        disabled={!r.success || !primPath}
                                        aria-describedby={!r.success ? `cu-restroom-card-error-${key}` : undefined}
                                        onClick={() => {
                                            if (!r.success || !primPath) return;
                                            const displayName =
                                                resolvePoiLocalizedTitle('restroom', (r.metadata || {}) as Record<string, unknown>, t)
                                                || t('search.toiletSection', { n: i + 1 });
                                            lastPoiDisplayNameRef.current = displayName;
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
                                        <div className="cu-restroom-card__icon-wrap">
                                            <div className="cu-restroom-card__icon-circle">
                                                <img src={glyphSrc} alt="" width={32} height={32} />
                                            </div>
                                        </div>
                                        <div className="cu-restroom-card__body">
                                            <div className="cu-restroom-card__title">{title}</div>
                                            {r.success ? (
                                                <div className="cu-restroom-card__meta">
                                                    <span className="cu-restroom-card__meta-item">
                                                        <img src={mapPinUrl} alt="" className="cu-restroom-card__meta-icon" width={16} height={16} />
                                                        {formatDistanceMeters(dist)}
                                                    </span>
                                                    <span className="cu-restroom-card__dot" aria-hidden />
                                                    <span className="cu-restroom-card__meta-item">
                                                        <img src={clockUrl} alt="" className="cu-restroom-card__meta-icon" width={16} height={16} />
                                                        {sec < 60
                                                            ? t('search.toiletSecAway', { count: Math.max(1, Math.round(sec)) })
                                                            : t('search.toiletMinAway', { count: Math.round(sec / 60) })}
                                                    </span>
                                                </div>
                                            ) : (
                                                <span
                                                    id={`cu-restroom-card-error-${key}`}
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
                        className="cu-restroom-widget__sheet-backdrop"
                        aria-label={t('search.toiletDismissSheet')}
                        onClick={dismissSheet}
                    />
                    <div
                        className="cu-restroom-widget__sheet"
                        role="region"
                        aria-labelledby="cu-restroom-sheet-title"
                    >
                        <div className="cu-restroom-widget__sheet-handle" aria-hidden />
                        <div className="cu-restroom-widget__sheet-head">
                            <h2 id="cu-restroom-sheet-title" className="cu-restroom-widget__sheet-title">
                                {sheetTitle}
                            </h2>
                            <button
                                type="button"
                                className="cu-restroom-widget__sheet-close"
                                onClick={dismissSheet}
                                aria-label={t('people.closePanel')}
                            >
                                <img src={closeXUrl} alt="" className="cu-restroom-widget__sheet-close-img" width={23} height={23} />
                            </button>
                        </div>
                        <div className="cu-restroom-widget__sheet-actions">
                            <button
                                type="button"
                                className={`cu-restroom-widget__btn ${isMoving ? 'cu-restroom-widget__btn--stop' : 'cu-restroom-widget__btn--go'}`}
                                disabled={!isMoving && restroomTrackingScreen && !poiRouteReady}
                                title={
                                    !isMoving && restroomTrackingScreen && !poiRouteReady
                                        ? t('search.poiWaitForRoute')
                                        : undefined
                                }
                                onClick={() => {
                                    if (isMoving) onMoveStop();
                                    else {
                                        if (activePrimPath && activeRouteId) {
                                            onGetDirections(activePrimPath, activeRouteId, sheetTitle);
                                        }
                                        enterRestroomTrackingScreen();
                                    }
                                }}
                            >
                                {!isMoving && (
                                    <img
                                        src={sheetSignpostUrl}
                                        alt=""
                                        className="cu-restroom-widget__btn-lead-icon"
                                        width={20}
                                        height={20}
                                    />
                                )}
                                {isMoving ? t('common.stop') : t('search.toiletGetDirections')}
                            </button>
                            {activePrimPath ? (
                                <button
                                    type="button"
                                    className="cu-restroom-widget__btn cu-restroom-widget__btn--tele"
                                    onClick={() => {
                                        try { sendMessage('navmeshRouteStop', { routeId: 'poi_nav' }); } catch { /* ignore */ }
                                        onTeleport(activePrimPath);
                                    }}
                                >
                                    {t('search.toiletTeleportThere')}
                                </button>
                            ) : null}
                        </div>
                        <div className="cu-restroom-widget__sheet-info">
                            <div className="cu-restroom-widget__sheet-info-row">
                                <img src={sheetFeeUrl} alt="" className="cu-restroom-widget__sheet-info-icon" width={16} height={16} />
                                <span className="cu-restroom-widget__sheet-info-label">{t('search.toiletInfoFee')}</span>
                                <span className="cu-restroom-widget__sheet-info-value">{formatFee(activeResult.metadata?.fee, t)}</span>
                            </div>
                            <div className="cu-restroom-widget__sheet-info-row">
                                <img src={sheetWheelchairDetailUrl} alt="" className="cu-restroom-widget__sheet-info-icon" width={16} height={16} />
                                <span className="cu-restroom-widget__sheet-info-label">{t('search.toiletInfoAccessible')}</span>
                                <span className="cu-restroom-widget__sheet-info-value">
                                    {activeResult.metadata?.is_accessible ? t('search.toiletInfoAccessibleYes') : t('search.toiletInfoAccessibleNo')}
                                </span>
                            </div>
                            <div className="cu-restroom-widget__sheet-info-row">
                                <img src={sheetSprayUrl} alt="" className="cu-restroom-widget__sheet-info-icon" width={16} height={16} />
                                <span className="cu-restroom-widget__sheet-info-label">{t('search.toiletInfoCleaning')}</span>
                                <span className="cu-restroom-widget__sheet-info-value">{formatCleaning(activeResult.metadata?.cleaning_schedule, t)}</span>
                            </div>
                            <div className="cu-restroom-widget__sheet-info-row">
                                <img src={sheetSprayUrl} alt="" className="cu-restroom-widget__sheet-info-icon" width={16} height={16} />
                                <span className="cu-restroom-widget__sheet-info-label">{t('search.toiletInfoSeats')}</span>
                                <span className="cu-restroom-widget__sheet-info-value">{activeResult.metadata?.toilet_seats ?? '\u2014'}</span>
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
};

export default RestroomWidget;
