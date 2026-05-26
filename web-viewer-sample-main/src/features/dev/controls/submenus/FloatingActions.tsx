import React from 'react';
import { useNavigation } from '../../../streaming/contexts';
import type { RouteMeasure } from './types';

const fmt = (n: number) => (n < 10 ? n.toFixed(1) : Math.round(n).toString());

const DistanceBadge: React.FC<{
    label: string;
    measure: RouteMeasure;
    onRefresh?: () => void;
}> = ({ label, measure: m, onRefresh }) => {
    const hasDistance = (m.distanceMetersBase > 0) || ((m.distanceMetersActual ?? 0) > 0);
    if (!hasDistance) return null;
    return (
        <div className="distance-measurement-list-item">
            <div className="distance-measurement-header">
                <span className="distance-measurement-title">{label}</span>
                {onRefresh != null && (
                    <button type="button" onClick={onRefresh} title="Recalculate distance" className="distance-measurement-refresh">↻</button>
                )}
            </div>
            <div className="distance-measurement-value">
                {fmt(m.distanceMetersBase)} m · ~{fmt(m.estimatedTimeSecondsBase)} s
                {m.distanceMetersActual != null && Math.abs((m.distanceMetersActual ?? 0) - m.distanceMetersBase) > 0.05 && (
                    <span className="distance-measurement-crowd"> (crowd: ~{fmt(m.estimatedTimeSecondsActual ?? 0)} s)</span>
                )}
            </div>
        </div>
    );
};

const FloatingActions: React.FC = () => {
    const nav = useNavigation();

    const navigationSpots = nav.navigationSpots;
    const activeSpotRouteId = nav.activeSpotRouteId;
    const movingToSpotId = nav.movingToSpotId;
    const onSpotMoveStart = nav.handleSpotMoveStart;
    const onSpotMoveStop = nav.handleSpotMoveStop;
    const activeSeatRouteId = nav.activeSeatRouteId ?? null;
    const movingToSeatId = nav.movingToSeatId ?? null;
    const onSeatMoveStart = nav.handleSeatMoveStart;
    const onSeatMoveStop = nav.handleSeatMoveStop;
    const routeMeasureEnabled = nav.routeMeasureEnabled;
    const routeMeasureByRouteId = nav.routeMeasureByRouteId ?? {};
    const onRefreshRouteMeasure = nav.handleRefreshRouteMeasure;

    const activeSpot = activeSpotRouteId
        ? navigationSpots.find(s => s.id === activeSpotRouteId) ?? null
        : null;

    const isMovingToSpot = !!(activeSpot && movingToSpotId === activeSpotRouteId);
    const seatRouteSimple = activeSeatRouteId && !activeSeatRouteId.includes(':');
    const isMovingToSeat = !!(seatRouteSimple && movingToSeatId === activeSeatRouteId);

    return (
        <>
            {/* Spot move FAB */}
            {activeSpot && (
                <button
                    className={`spot-move-fab ${isMovingToSpot ? 'moving' : ''}`}
                    onClick={() => {
                        if (isMovingToSpot) onSpotMoveStop?.();
                        else onSpotMoveStart?.(activeSpot);
                    }}
                >
                    <span className="spot-move-fab-icon">{isMovingToSpot ? '⏹' : '🚶'}</span>
                    <span className="spot-move-fab-label">
                        {isMovingToSpot ? 'Stop moving' : `Move to ${activeSpot.label}`}
                    </span>
                </button>
            )}

            {/* Seat move FAB */}
            {seatRouteSimple && onSeatMoveStart && (
                <button
                    className={`spot-move-fab ${isMovingToSeat ? 'moving' : ''}`}
                    onClick={() => {
                        if (isMovingToSeat) onSeatMoveStop?.();
                        else onSeatMoveStart();
                    }}
                >
                    <span className="spot-move-fab-icon">{isMovingToSeat ? '⏹' : '🚶'}</span>
                    <span className="spot-move-fab-label">
                        {isMovingToSeat ? 'Stop moving' : `Move to seat ${activeSeatRouteId}`}
                    </span>
                </button>
            )}

            {/* Distance: seat */}
            {seatRouteSimple && routeMeasureEnabled && (() => {
                const m = routeMeasureByRouteId['seat_nav'];
                if (!m?.success) return null;
                return <DistanceBadge label={`Distance to seat ${activeSeatRouteId}:`} measure={m} />;
            })()}

            {/* Distance: spot */}
            {activeSpotRouteId && routeMeasureEnabled && (() => {
                const m = routeMeasureByRouteId[activeSpotRouteId];
                if (!m?.success) return null;
                return <DistanceBadge label="Distance measurement:" measure={m} onRefresh={onRefreshRouteMeasure ?? undefined} />;
            })()}
        </>
    );
};

export default FloatingActions;
