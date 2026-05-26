import React, { useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { resolvePoiLocalizedTitle } from '../../streaming/utils/poiLocalizedTitle';
import closeXUrl from '@icons/restrooms/close-x.svg';
import sheetFeeUrl from '@icons/restrooms/sheet-fee.svg';
import sheetWheelchairDetailUrl from '@icons/restrooms/sheet-wheelchair-detail.svg';
import sheetSprayUrl from '@icons/restrooms/sheet-spray.svg';
import { parseElevatorRide, type ElevatorRideDestination } from './elevatorRideTypes';
import { useModalAccessibility } from '../../streaming/hooks/useModalAccessibility';
import './PoiInfoCard.css';

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

export interface PoiInfoCardProps {
    /** POI category — 'restroom' | 'quiet_zone' | 'exit' | future types. Drives which info rows render. */
    poiType: string;
    /** Full metadata entry (mirrors restroom_data / quiet_zone_data / exit_data row). */
    metadata: Record<string, unknown> | null | undefined;
    /** Legacy Kit English label; ignored when a structured localized title exists. */
    displayName?: string;
    /** Close handler — invoked on close button, backdrop tap, or Escape. */
    onClose: () => void;
    /** Teleport to another floor (NavShortcuts spawn); used for elevator coins only. */
    onElevatorRide?: (primPath: string) => void;
}

/**
 * Info-only POI detail card. Slides up from the bottom of the viewport,
 * matches the visual language of the restroom/quiet-zone widget detail
 * sheets but renders **no** action buttons (no Take Me There / Get
 * directions). Used by the coin-click flow where the user has already
 * physically approached the POI in 3D space; navigating to it would be
 * redundant.
 */
function destinationLabel(
    dest: ElevatorRideDestination,
    t: (k: string, o?: Record<string, unknown>) => string,
): string {
    const key = dest.i18n_key?.trim();
    if (key && key.length > 0) {
        const translated = t(key);
        if (translated !== key) return translated;
    }
    if (dest.label_en?.trim()) return dest.label_en.trim();
    return dest.node_id;
}

const PoiInfoCard: React.FC<PoiInfoCardProps> = ({
    poiType,
    metadata,
    displayName,
    onClose,
    onElevatorRide,
}) => {
    const { t } = useTranslation();

    const dialogRef = useRef<HTMLDivElement>(null);
    useModalAccessibility(dialogRef);

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [onClose]);

    const md = metadata || {};
    const title = useMemo(() => {
        const m = metadata || {};
        const localized = resolvePoiLocalizedTitle(poiType, m, t);
        if (localized) return localized;
        if (typeof displayName === 'string' && displayName.trim()) return displayName;
        if (typeof m.display_name === 'string' && (m.display_name as string).trim()) return m.display_name as string;
        if (poiType === 'quiet_zone') return t('search.findQuietArea');
        if (poiType === 'exit') return t('search.poiNameEmergencyExit');
        return t('search.findToilet');
    }, [poiType, metadata, t, displayName]);

    const isAccessible = md.is_accessible === true;
    const fee = md.fee;
    const cleaning = md.cleaning_schedule;
    const seats = typeof md.toilet_seats === 'number' ? md.toilet_seats : null;

    const showAccessibility = poiType === 'restroom' || poiType === 'quiet_zone';
    const showFee = poiType === 'restroom' || poiType === 'quiet_zone';
    const showCleaning = poiType === 'restroom' || poiType === 'quiet_zone';
    const showSeats = poiType === 'restroom' && seats !== null;

    const elevatorRide = useMemo(
        () => (poiType === 'elevator' ? parseElevatorRide(md) : null),
        [poiType, md],
    );
    const showElevatorRide = Boolean(elevatorRide?.destinations.length && onElevatorRide);

    return (
        <div
            ref={dialogRef}
            className="cu-poi-info-card-root"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cu-poi-info-card-title"
        >
            <button
                type="button"
                className="cu-poi-info-card__backdrop"
                aria-label={t('common.close')}
                onClick={onClose}
            />
            <div className="cu-poi-info-card__sheet" role="region">
                <div className="cu-poi-info-card__handle" aria-hidden />
                <div className="cu-poi-info-card__head">
                    <h2 id="cu-poi-info-card-title" className="cu-poi-info-card__title">
                        {title}
                    </h2>
                    <button
                        type="button"
                        className="cu-poi-info-card__close"
                        onClick={onClose}
                        aria-label={t('common.close')}
                    >
                        <img src={closeXUrl} alt="" className="cu-poi-info-card__close-img" width={23} height={23} />
                    </button>
                </div>
                {(showFee || showAccessibility || showCleaning || showSeats) && (
                    <div className="cu-poi-info-card__info">
                        {showFee && (
                            <div className="cu-poi-info-card__row">
                                <img src={sheetFeeUrl} alt="" className="cu-poi-info-card__row-icon" width={16} height={16} />
                                <span className="cu-poi-info-card__row-label">{t('search.toiletInfoFee')}</span>
                                <span className="cu-poi-info-card__row-value">{formatFee(fee, t)}</span>
                            </div>
                        )}
                        {showAccessibility && (
                            <div className="cu-poi-info-card__row">
                                <img src={sheetWheelchairDetailUrl} alt="" className="cu-poi-info-card__row-icon" width={16} height={16} />
                                <span className="cu-poi-info-card__row-label">{t('search.toiletInfoAccessible')}</span>
                                <span className="cu-poi-info-card__row-value">
                                    {isAccessible ? t('search.toiletInfoAccessibleYes') : t('search.toiletInfoAccessibleNo')}
                                </span>
                            </div>
                        )}
                        {showCleaning && (
                            <div className="cu-poi-info-card__row">
                                <img src={sheetSprayUrl} alt="" className="cu-poi-info-card__row-icon" width={16} height={16} />
                                <span className="cu-poi-info-card__row-label">{t('search.toiletInfoCleaning')}</span>
                                <span className="cu-poi-info-card__row-value">{formatCleaning(cleaning, t)}</span>
                            </div>
                        )}
                        {showSeats && (
                            <div className="cu-poi-info-card__row">
                                <img src={sheetSprayUrl} alt="" className="cu-poi-info-card__row-icon" width={16} height={16} />
                                <span className="cu-poi-info-card__row-label">{t('search.toiletInfoSeats')}</span>
                                <span className="cu-poi-info-card__row-value">{seats}</span>
                            </div>
                        )}
                    </div>
                )}
                {showElevatorRide && elevatorRide && (
                    <div className="cu-poi-info-card__elevator">
                        <h3 className="cu-poi-info-card__elevator-heading">{t('coin.elevatorUse')}</h3>
                        <ul className="cu-poi-info-card__elevator-list">
                            {elevatorRide.destinations.map((dest) => {
                                const label = destinationLabel(dest, t);
                                return (
                                    <li key={dest.node_id}>
                                        <button
                                            type="button"
                                            className="cu-poi-info-card__elevator-btn"
                                            onClick={() => onElevatorRide?.(dest.prim_path)}
                                        >
                                            {label}
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    </div>
                )}
            </div>
        </div>
    );
};

export default PoiInfoCard;
