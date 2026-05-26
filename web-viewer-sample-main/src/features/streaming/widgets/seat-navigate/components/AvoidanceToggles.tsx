import React from 'react';
import { useTranslation } from 'react-i18next';
import { PRESET_COST_VALUE } from '../../../messaging';

interface AvoidanceTogglesProps {
    avoidCrowds: boolean;
    avoidNoise: boolean;
    onAvoidCrowdsToggle: () => void;
    onAvoidNoiseToggle: () => void;
    useWaypoints: boolean;
    onUseWaypointsToggle: () => void;
    hasValidRoute: boolean;
    isMoving: boolean;
    activeSeatRouteId: string | null;
    onMoveStart: () => void;
    onMoveStop: () => void;
    moveDisabled: boolean;
}

const AvoidanceToggles: React.FC<AvoidanceTogglesProps> = ({
    avoidCrowds,
    avoidNoise,
    onAvoidCrowdsToggle,
    onAvoidNoiseToggle,
    useWaypoints,
    onUseWaypointsToggle,
    hasValidRoute,
    isMoving,
    activeSeatRouteId,
    onMoveStart,
    onMoveStop,
    moveDisabled,
}) => {
    const { t } = useTranslation();
    return (
    <>
        <label className="seat-panel-default__checkbox-label">
            <input
                type="checkbox"
                checked={useWaypoints}
                onChange={onUseWaypointsToggle}
                className="seat-panel-default__checkbox"
            />
            {t('seat.useCorridorWaypoints')}
        </label>
        <div className="seat-panel-default__toggle-row">
            <button
                type="button"
                onClick={onAvoidCrowdsToggle}
                className={`seat-panel-default__toggle${avoidCrowds ? ' seat-panel-default__toggle--crowd-on' : ''}`}
                aria-pressed={avoidCrowds}
                aria-label={
                    avoidCrowds
                        ? t('seat.disableCrowdAvoidance')
                        : t('seat.enableCrowdAvoidance', { value: PRESET_COST_VALUE })
                }
                title={
                    avoidCrowds
                        ? t('seat.disableCrowdAvoidance')
                        : t('seat.enableCrowdAvoidance', { value: PRESET_COST_VALUE })
                }
            >
                {avoidCrowds ? t('seat.avoidCrowdsActive') : t('seat.avoidCrowds')}
            </button>
            <button
                type="button"
                onClick={onAvoidNoiseToggle}
                className={`seat-panel-default__toggle${avoidNoise ? ' seat-panel-default__toggle--noise-on' : ''}`}
                aria-pressed={avoidNoise}
                aria-label={
                    avoidNoise
                        ? t('seat.disableNoiseAvoidance')
                        : t('seat.enableNoiseAvoidance', { value: PRESET_COST_VALUE })
                }
                title={
                    avoidNoise
                        ? t('seat.disableNoiseAvoidance')
                        : t('seat.enableNoiseAvoidance', { value: PRESET_COST_VALUE })
                }
            >
                {avoidNoise ? t('seat.avoidNoiseActive') : t('seat.avoidNoise')}
            </button>
        </div>
        {hasValidRoute && (
            <button
                type="button"
                onClick={() => {
                    if (isMoving) onMoveStop();
                    else onMoveStart();
                }}
                disabled={moveDisabled}
                className={`seat-panel-default__move-btn ${isMoving ? 'seat-panel-default__move-btn--stop' : 'seat-panel-default__move-btn--go'}`}
            >
                {isMoving ? t('seat.stopMoving') : t('seat.moveToSeat', { id: activeSeatRouteId })}
            </button>
        )}
    </>
    );
};

export default AvoidanceToggles;
