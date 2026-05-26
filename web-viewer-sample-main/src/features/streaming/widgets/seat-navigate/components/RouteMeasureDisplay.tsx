import React from 'react';
import { useTranslation } from 'react-i18next';
import type { RouteMeasure } from '../../../types';

interface RouteMeasureDisplayProps {
    isCu: boolean;
    routeMeasure: RouteMeasure;
    onRefresh?: () => void;
    refreshDisabled: boolean;
    onArmCooldown: () => void;
}

const fmt = (n: number) => (n < 10 ? n.toFixed(1) : Math.round(n).toString());

const RouteMeasureDisplay: React.FC<RouteMeasureDisplayProps> = ({
    isCu,
    routeMeasure,
    onRefresh,
    refreshDisabled,
    onArmCooldown,
}) => {
    const { t } = useTranslation();
    const hasCrowdDelta = (routeMeasure.distanceMetersCrowdDelta ?? 0) > 0.05 || (routeMeasure.estimatedTimeSecondsCrowdDelta ?? 0) > 0.05;
    const hasSoundDelta = (routeMeasure.distanceMetersSoundDelta ?? 0) > 0.05 || (routeMeasure.estimatedTimeSecondsSoundDelta ?? 0) > 0.05;
    const hasAnyDelta = hasCrowdDelta || hasSoundDelta;

    return (
        <div
            className={isCu ? 'cu-seat-panel__measure' : 'seat-panel-default__measure'}
        >
            <div className={isCu ? 'cu-seat-panel__measure-row' : 'seat-panel-default__measure-row'}>
                <span>
                    {fmt(routeMeasure.distanceMetersBase)} m {'\u00B7'} ~{fmt(routeMeasure.estimatedTimeSecondsBase)} s
                </span>
                {onRefresh && (
                    <button
                        type="button"
                        onClick={() => {
                            if (isCu) onArmCooldown();
                            onRefresh();
                        }}
                        disabled={refreshDisabled}
                        className={isCu ? 'cu-seat-panel__icon-btn' : 'seat-panel-default__icon-btn'}
                        title={t('seat.recalculate')}
                        aria-label={t('seat.recalculate')}
                    >
                        {'\u21BB'}
                    </button>
                )}
            </div>
            {hasAnyDelta && (
                <div className={isCu ? 'cu-seat-panel__measure-delta' : 'seat-panel-default__measure-delta'}>
                    (
                    {[
                        hasCrowdDelta
                            ? t('seat.crowdDelta', { dist: fmt(routeMeasure.distanceMetersCrowdDelta!), time: fmt(routeMeasure.estimatedTimeSecondsCrowdDelta!) })
                            : null,
                        hasSoundDelta
                            ? t('seat.soundDelta', { dist: fmt(routeMeasure.distanceMetersSoundDelta!), time: fmt(routeMeasure.estimatedTimeSecondsSoundDelta!) })
                            : null,
                    ]
                        .filter(Boolean)
                        .join(', ')}
                    )
                </div>
            )}
        </div>
    );
};

export default RouteMeasureDisplay;
