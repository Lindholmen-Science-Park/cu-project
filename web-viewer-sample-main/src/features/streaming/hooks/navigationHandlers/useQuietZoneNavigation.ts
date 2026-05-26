import { useState, useCallback, useRef, useEffect } from 'react';
import { sendMessage } from '../../messaging';
import type { PoiResult } from '../../types';

export function useQuietZoneNavigation(markRouteCalculating: (routeId: string) => void) {
    const [quietZoneWidgetOpen, setQuietZoneWidgetOpen] = useState(false);
    const [quietZoneTrackingScreen, setQuietZoneTrackingScreen] = useState(false);
    const [quietZoneResults, setQuietZoneResults] = useState<PoiResult[]>([]);
    /** True after `navmeshRoutesToPoisRequest` until final `navmeshRoutesToPoisResult` for quiet zones. */
    const [quietZonePoiListLoading, setQuietZonePoiListLoading] = useState(false);
    const [activeQuietZoneRouteId, setActiveQuietZoneRouteId] = useState<string | null>(null);
    const [movingToQuietZoneId, setMovingToQuietZoneId] = useState<string | null>(null);
    const lastQuietZonePrimPathRef = useRef<string | null>(null);
    const lastQuietZoneDisplayNameRef = useRef<string | null>(null);
    const quietZoneResultsRef = useRef<PoiResult[]>([]);
    const activeQuietZoneRouteIdRef = useRef<string | null>(null);
    useEffect(() => {
        quietZoneResultsRef.current = quietZoneResults;
    }, [quietZoneResults]);
    useEffect(() => {
        activeQuietZoneRouteIdRef.current = activeQuietZoneRouteId;
    }, [activeQuietZoneRouteId]);

    const enterQuietZoneTrackingScreen = useCallback(() => {
        setQuietZoneTrackingScreen(true);
    }, []);

    const handleOpenQuietZoneWidget = useCallback(() => {
        setQuietZoneWidgetOpen(true);
        setQuietZoneTrackingScreen(false);
        setQuietZoneResults([]);
        setQuietZonePoiListLoading(true);
        try { sendMessage('navmeshRoutesToPoisRequest', { poiType: 'quiet_zone' }); } catch {}
    }, []);

    const dispatchQuietZoneRouteCalculate = useCallback((primPath: string) => {
        markRouteCalculating('quiet_zone_nav');
        try {
            sendMessage('navmeshRouteCalculate', {
                routeId: 'quiet_zone_nav',
                startpointPath: '/World/PlayerCharacter',
                endpointPath: primPath,
                drawPath: true,
                enablePeriodicRecalc: true,
                startUseGround: true,
                fromPoiList: true,
            });
        } catch { /* stream */ }
    }, [markRouteCalculating]);

    const handleQuietZoneClick = useCallback((primPath: string, key: string) => {
        const isSame = activeQuietZoneRouteId === key;
        if (movingToQuietZoneId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToQuietZoneId(null);
        }
        if (activeQuietZoneRouteId) {
            try { sendMessage('navmeshRouteStop', { routeId: 'quiet_zone_nav' }); } catch {}
        }
        if (isSame) {
            setActiveQuietZoneRouteId(null);
            lastQuietZonePrimPathRef.current = null;
            lastQuietZoneDisplayNameRef.current = null;
            setQuietZoneTrackingScreen(false);
            markRouteCalculating('quiet_zone_nav');
            return;
        }
        setQuietZoneTrackingScreen(false);
        setActiveQuietZoneRouteId(key);
        lastQuietZonePrimPathRef.current = primPath;
        markRouteCalculating('quiet_zone_nav');
    }, [activeQuietZoneRouteId, movingToQuietZoneId, markRouteCalculating]);

    const handleQuietZoneGetDirections = useCallback((
        primPath: string,
        key: string,
        displayName?: string | null,
    ) => {
        if (!primPath || !key) return;
        if (movingToQuietZoneId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToQuietZoneId(null);
        }
        setActiveQuietZoneRouteId(key);
        lastQuietZonePrimPathRef.current = primPath;
        const label = displayName?.trim() || null;
        if (label) {
            lastQuietZoneDisplayNameRef.current = label;
        }
        dispatchQuietZoneRouteCalculate(primPath);
    }, [movingToQuietZoneId, dispatchQuietZoneRouteCalculate]);

    const handleQuietZoneMoveStart = useCallback(() => {
        if (!activeQuietZoneRouteId) return;
        const primPath = lastQuietZonePrimPathRef.current;
        if (!primPath) return;
        setMovingToQuietZoneId(activeQuietZoneRouteId);
        try {
            sendMessage('navigationStateSet', {
                movementMode: 'pointClick',
                autoMove: true,
                routeId: 'quiet_zone_nav',
                endpointPath: primPath,
                endPos: null,
            });
        } catch {}
    }, [activeQuietZoneRouteId]);

    const handleQuietZoneMoveStop = useCallback(() => {
        if (!movingToQuietZoneId) return;
        try {
            sendMessage('navigationStateSet', {
                movementMode: 'pointClick',
                autoMove: false,
                routeId: 'quiet_zone_nav',
            });
        } catch {}
        setMovingToQuietZoneId(null);
    }, [movingToQuietZoneId]);

    const handleQuietZoneWidgetClose = useCallback(() => {
        if (movingToQuietZoneId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToQuietZoneId(null);
        }
        if (activeQuietZoneRouteId) {
            try { sendMessage('navmeshRouteStop', { routeId: 'quiet_zone_nav' }); } catch {}
            setActiveQuietZoneRouteId(null);
            lastQuietZonePrimPathRef.current = null;
            lastQuietZoneDisplayNameRef.current = null;
        }
        markRouteCalculating('quiet_zone_nav');
        setQuietZoneWidgetOpen(false);
        setQuietZoneTrackingScreen(false);
        setQuietZonePoiListLoading(false);
    }, [movingToQuietZoneId, activeQuietZoneRouteId, markRouteCalculating]);

    const handleQuietZoneWidgetRefresh = useCallback(() => {
        if (movingToQuietZoneId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false }); } catch {}
            setMovingToQuietZoneId(null);
        }
        if (activeQuietZoneRouteId) {
            try { sendMessage('navmeshRouteStop', { routeId: 'quiet_zone_nav' }); } catch {}
            setActiveQuietZoneRouteId(null);
            lastQuietZonePrimPathRef.current = null;
            lastQuietZoneDisplayNameRef.current = null;
        }
        markRouteCalculating('quiet_zone_nav');
        setQuietZoneResults([]);
        setQuietZonePoiListLoading(true);
        try { sendMessage('navmeshRoutesToPoisRequest', { poiType: 'quiet_zone' }); } catch {}
    }, [movingToQuietZoneId, activeQuietZoneRouteId, markRouteCalculating]);

    return {
        quietZoneWidgetOpen, setQuietZoneWidgetOpen,
        quietZoneTrackingScreen,
        setQuietZoneTrackingScreen,
        enterQuietZoneTrackingScreen,
        quietZoneResults, setQuietZoneResults,
        quietZonePoiListLoading, setQuietZonePoiListLoading,
        activeQuietZoneRouteId, setActiveQuietZoneRouteId,
        movingToQuietZoneId, setMovingToQuietZoneId,
        lastQuietZonePrimPathRef,
        lastQuietZoneDisplayNameRef,
        quietZoneResultsRef,
        activeQuietZoneRouteIdRef,
        handleOpenQuietZoneWidget,
        handleQuietZoneClick,
        handleQuietZoneGetDirections,
        handleQuietZoneMoveStart,
        handleQuietZoneMoveStop,
        handleQuietZoneWidgetClose,
        handleQuietZoneWidgetRefresh,
    };
}
