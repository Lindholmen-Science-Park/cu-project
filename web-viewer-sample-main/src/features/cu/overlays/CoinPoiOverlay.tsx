import React, { useCallback } from 'react';
import { useControl, useNavigation } from '../../streaming/contexts';
import PoiInfoCard from '../widgets/PoiInfoCard';

/**
 * CU-only listener that surfaces a `PoiInfoCard` whenever a POI coin
 * (round sign) is clicked in 3D. State + payload live on `ControlContext`
 * (`coinPoiOpen`, `coinPoiPayload`) and are populated by the
 * `coinPoi.open` interaction action handler in `ChatContext`.
 */
const CoinPoiOverlay: React.FC = () => {
    const ctrl = useControl();
    const nav = useNavigation();

    const handleClose = useCallback(() => {
        ctrl.setCoinPoiOpen(false);
        ctrl.setCoinPoiPayload(null);
    }, [ctrl.setCoinPoiOpen, ctrl.setCoinPoiPayload]);

    const handleElevatorRide = useCallback(
        (primPath: string) => {
            handleClose();
            nav.handlePoiTeleport(primPath, { transitionMessageKey: 'coin.elevatorRiding' });
        },
        [handleClose, nav.handlePoiTeleport],
    );

    if (!ctrl.coinPoiOpen || !ctrl.coinPoiPayload) return null;
    const p = ctrl.coinPoiPayload;
    return (
        <PoiInfoCard
            poiType={p.poiType}
            metadata={p.metadata}
            displayName={p.displayName}
            onClose={handleClose}
            onElevatorRide={p.poiType === 'elevator' ? handleElevatorRide : undefined}
        />
    );
};

export default CoinPoiOverlay;
