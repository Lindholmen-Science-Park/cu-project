import React, { useMemo } from 'react';
import type { ExitResult, PoiResult } from '../types';
import { useNavigation, useAppUI } from '../contexts';
import PoiRoutesWidget from './PoiRoutesWidget';

function exitToPoiResult(r: ExitResult): PoiResult {
    return {
        poiRef: r.exitRef,
        poiId: r.exitId,
        success: r.success,
        error: r.error,
        distanceMetersBase: r.distanceMetersBase,
        estimatedTimeSecondsBase: r.estimatedTimeSecondsBase,
        distanceMetersActual: r.distanceMetersActual,
        estimatedTimeSecondsActual: r.estimatedTimeSecondsActual,
        metadata: r.metadata,
    };
}

const exitIcon = (_r: PoiResult, i: number) => (i === 0 ? '\uD83D\uDFE2' : '\uD83D\uDEAA');

const ExitsWidget: React.FC = () => {
    const nav = useNavigation();
    const appUI = useAppUI();
    const poiResults = useMemo(() => nav.exitsResults.map(exitToPoiResult), [nav.exitsResults]);

    if (appUI.seatArrivalCelebrationVisible || appUI.poiArrivalVisible) return null;
    if (!nav.exitsWidgetOpen) return null;

    return (
        <PoiRoutesWidget
            title="Nearest exits (top 5)"
            results={poiResults}
            activeRouteId={nav.activeExitRouteId}
            movingToId={nav.movingToExitId}
            onClose={nav.handleExitsWidgetClose}
            onRefresh={nav.handleExitsWidgetRefresh}
            onItemClick={nav.handleExitClick}
            onMoveStart={nav.handleExitMoveStart}
            onMoveStop={nav.handleExitMoveStop}
            onTeleport={nav.handlePoiTeleport}
            itemIcon={exitIcon}
        />
    );
};

export default ExitsWidget;
