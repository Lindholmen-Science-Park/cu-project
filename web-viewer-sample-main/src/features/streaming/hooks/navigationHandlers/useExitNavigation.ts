import { useState, useCallback, useRef } from 'react';
import { sendMessage } from '../../messaging';
import type { ExitResult } from '../../types';

export function useExitNavigation() {
    const [activeExitRouteId, setActiveExitRouteId] = useState<string | null>(null);
    const [movingToExitId, setMovingToExitId] = useState<string | null>(null);
    const lastExitPrimPathRef = useRef<string | null>(null);
    const [exitsWidgetOpen, setExitsWidgetOpen] = useState(false);
    const [exitsResults, setExitsResults] = useState<ExitResult[]>([]);

    const handleCalculateRoutesToExits = useCallback(() => {
        setExitsWidgetOpen(true);
        setExitsResults([]);
        try { sendMessage('navmeshRoutesToExitsRequest', {}); } catch {}
    }, []);

    const handleExitClick = useCallback((exitPrimPath: string, exitKey: string) => {
        const isSameExit = activeExitRouteId === exitKey;
        if (movingToExitId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToExitId(null);
        }
        if (activeExitRouteId) {
            try { sendMessage('navmeshRouteStop', { routeId: 'exit_nav' }); } catch {}
        }
        if (isSameExit) {
            setActiveExitRouteId(null);
            lastExitPrimPathRef.current = null;
            return;
        }
        setActiveExitRouteId(exitKey);
        lastExitPrimPathRef.current = exitPrimPath;
        try {
            sendMessage('navmeshRouteCalculate', {
                routeId: 'exit_nav', startpointPath: '/World/PlayerCharacter', endpointPath: exitPrimPath,
                drawPath: true, enablePeriodicRecalc: true, startUseGround: true,
            });
        } catch {}
    }, [activeExitRouteId, movingToExitId]);

    const handleExitMoveStart = useCallback(() => {
        if (!activeExitRouteId) return;
        const primPath = lastExitPrimPathRef.current;
        if (!primPath) return;
        setMovingToExitId(activeExitRouteId);
        try {
            sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: true, routeId: 'exit_nav', endpointPath: primPath, endPos: null });
        } catch {}
    }, [activeExitRouteId]);

    const handleExitMoveStop = useCallback(() => {
        if (!movingToExitId) return;
        const primPath = lastExitPrimPathRef.current;
        try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
        if (primPath) {
            try {
                sendMessage('navmeshRouteCalculate', {
                    routeId: 'exit_nav', startpointPath: '/World/PlayerCharacter', endpointPath: primPath,
                    drawPath: true, enablePeriodicRecalc: true, startUseGround: true,
                });
            } catch {}
        }
        try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
        setMovingToExitId(null);
    }, [movingToExitId]);

    const handleExitsWidgetClose = useCallback(() => {
        if (movingToExitId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToExitId(null);
        }
        if (activeExitRouteId) {
            try { sendMessage('navmeshRouteStop', { routeId: 'exit_nav' }); } catch {}
            setActiveExitRouteId(null);
            lastExitPrimPathRef.current = null;
        }
        setExitsWidgetOpen(false);
    }, [movingToExitId, activeExitRouteId]);

    const handleExitsWidgetRefresh = useCallback(() => {
        if (movingToExitId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToExitId(null);
        }
        if (activeExitRouteId) {
            try { sendMessage('navmeshRouteStop', { routeId: 'exit_nav' }); } catch {}
            setActiveExitRouteId(null);
            lastExitPrimPathRef.current = null;
        }
        setExitsResults([]);
        try { sendMessage('navmeshRoutesToExitsRequest', {}); } catch {}
    }, [movingToExitId, activeExitRouteId]);

    return {
        activeExitRouteId, setActiveExitRouteId,
        movingToExitId, setMovingToExitId,
        lastExitPrimPathRef,
        exitsWidgetOpen, setExitsWidgetOpen,
        exitsResults, setExitsResults,
        handleCalculateRoutesToExits,
        handleExitClick,
        handleExitMoveStart,
        handleExitMoveStop,
        handleExitsWidgetClose,
        handleExitsWidgetRefresh,
    };
}
