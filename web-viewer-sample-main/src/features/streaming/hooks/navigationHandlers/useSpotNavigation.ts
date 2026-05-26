import { useState, useCallback } from 'react';
import { sendMessage } from '../../messaging';
import { NavigationSpot } from '../../types';

export function useSpotNavigation(
    navigationSpots: NavigationSpot[],
    navigationSpotsRef: React.MutableRefObject<NavigationSpot[]>,
) {
    const [activeSpotRouteId, setActiveSpotRouteId] = useState<string | null>(null);
    const [movingToSpotId, setMovingToSpotId] = useState<string | null>(null);

    const handleSpotNavigate = useCallback((spot: NavigationSpot) => {
        const isSameSpot = activeSpotRouteId === spot.id;
        if (movingToSpotId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: true, routeId: 'player' }); } catch {}
            setMovingToSpotId(null);
        }
        if (activeSpotRouteId) {
            try { sendMessage('navmeshRouteStop', { routeId: activeSpotRouteId }); } catch {}
            try { sendMessage('interactionPointDeactivate', { pointId: activeSpotRouteId }); } catch {}
            console.log(`Spot route stopped: ${activeSpotRouteId}`);
        }
        if (isSameSpot) { setActiveSpotRouteId(null); return; }
        setActiveSpotRouteId(spot.id);
        try {
            sendMessage('navmeshRouteCalculate', {
                routeId: spot.id, startpointPath: '/World/PlayerCharacter', endpointPath: spot.primPath,
                drawPath: true, enablePeriodicRecalc: true, startUseGround: true,
            });
        } catch {}
        try { sendMessage('interactionPointActivate', { pointId: spot.id }); } catch {}
        console.log(`Spot route started: ${spot.id} -> ${spot.primPath}`);
    }, [activeSpotRouteId, movingToSpotId]);

    const handleRefreshRouteMeasure = useCallback(() => {
        if (!activeSpotRouteId) return;
        const spot = navigationSpots.find((s) => s.id === activeSpotRouteId);
        if (!spot) return;
        try {
            sendMessage('navmeshRouteCalculate', {
                routeId: spot.id, startpointPath: '/World/PlayerCharacter', endpointPath: spot.primPath,
                drawPath: true, enablePeriodicRecalc: true, startUseGround: true,
            });
        } catch {}
    }, [activeSpotRouteId, navigationSpots]);

    const handleSpotMoveStart = useCallback((spot: NavigationSpot) => {
        if (!activeSpotRouteId || activeSpotRouteId !== spot.id) return;
        setMovingToSpotId(spot.id);
        try {
            sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: true, routeId: spot.id, endpointPath: spot.primPath, endPos: null });
        } catch {}
        console.log(`Spot auto-move started: ${spot.id}`);
    }, [activeSpotRouteId]);

    const handleSpotMoveStop = useCallback(() => {
        const rid = movingToSpotId;
        if (!rid) return;
        try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
        const spot = navigationSpotsRef.current.find((s) => s.id === rid);
        if (spot) {
            try {
                sendMessage('navmeshRouteCalculate', {
                    routeId: rid, startpointPath: '/World/PlayerCharacter', endpointPath: spot.primPath,
                    drawPath: true, enablePeriodicRecalc: true, startUseGround: true,
                });
            } catch {}
        }
        try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
        setMovingToSpotId(null);
        console.log(`Spot auto-move stopped: ${rid}`);
    }, [movingToSpotId, navigationSpotsRef]);

    return {
        activeSpotRouteId, setActiveSpotRouteId,
        movingToSpotId, setMovingToSpotId,
        handleSpotNavigate,
        handleRefreshRouteMeasure,
        handleSpotMoveStart,
        handleSpotMoveStop,
    };
}
