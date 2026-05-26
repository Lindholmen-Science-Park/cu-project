import { useState, useCallback, useRef } from 'react';
import i18n from '../../../../i18n';
import { sendMessage } from '../../messaging';
import type { RouteMeasure } from '../../types';
import { SeatQuery } from '../../widgets/SeatNavigateWidget';
import { beginViewTransition } from '../../viewTransition';

export function useSeatNavigation(
    setRouteMeasureByRouteId: React.Dispatch<React.SetStateAction<Record<string, RouteMeasure>>>,
    revertWheelchairMode: () => void,
    markRouteCalculating: (routeId: string) => void,
) {
    const [activeSeatRouteId, setActiveSeatRouteId] = useState<string | null>(null);
    const [movingToSeatId, setMovingToSeatId] = useState<string | null>(null);
    const lastSeatPositionRef = useRef<number[] | null>(null);
    /**
     * When true, the active `seat_nav` route uses the seat as the *start*
     * (bird-eye seat directions, swap mode) — the actual destination is the
     * player's last position. Both the `seatTeleportResult` toast (fires when
     * we hop to the seat) and the `seat_nav` arrival celebration (fires when
     * the auto-move reaches the player position) must be suppressed in this
     * mode, otherwise the user sees a misleading "arrived at your seat"
     * celebration even though they're navigating *away* from it.
     */
    const seatRouteFromSeatRef = useRef<boolean>(false);
    /**
     * Optional override for the in-flight seat navigation pill label.
     * Used by the bird-eye seat-directions swap case ("Current position")
     * where the destination is the player's previous position rather than
     * the seat itself; falls back to the formatted seat label otherwise.
     */
    const [seatRouteDisplayLabel, setSeatRouteDisplayLabel] = useState<string | null>(null);
    const [seatingLayout, setSeatingLayout] = useState<string | null>(null);
    const [availableSeatingLayouts, setAvailableSeatingLayouts] = useState<string[]>([]);
    const [seatedCrowdLayout, setSeatedCrowdLayout] = useState<string | null>(null);
    const [availableSeatedCrowdLayouts, setAvailableSeatedCrowdLayouts] = useState<string[]>([]);
    const [seatWidgetOpen, setSeatWidgetOpen] = useState(false);

    /**
     * Paired setter for the swap-mode fields — `seatRouteFromSeatRef` (handler-time
     * read, drives arrival-celebration suppression) and `seatRouteDisplayLabel`
     * (re-renders the in-flight pill text). The two always describe the same
     * swap decision and would silently desync if mutated independently, so all
     * external callers should go through this pair instead of touching the ref
     * and the state setter directly.
     */
    const setSeatRouteSwapState = useCallback(
        (opts: { fromSeat: boolean; displayLabel: string | null }) => {
            seatRouteFromSeatRef.current = opts.fromSeat;
            setSeatRouteDisplayLabel(opts.displayLabel);
        },
        [],
    );
    const clearSeatRouteSwapState = useCallback(() => {
        seatRouteFromSeatRef.current = false;
        setSeatRouteDisplayLabel(null);
    }, []);

    const handleSeatNavigate = useCallback((query: SeatQuery) => {
        const seatPayload: Record<string, any> = { section: query.section, row: query.row, seat: query.seat };
        if (query.useWaypoints === false) seatPayload.useWaypoints = false;
        const seatKey = `${query.section}-${query.row}-${query.seat}`;
        if (activeSeatRouteId === seatKey) {
            if (movingToSeatId) {
                try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
                setMovingToSeatId(null);
            }
            try { sendMessage('seatNavigate', { ...seatPayload, action: 'stop' }); } catch {}
            try { sendMessage('navmeshRouteStop', { routeId: 'player' }); } catch {}
            setActiveSeatRouteId(null);
            lastSeatPositionRef.current = null;
            markRouteCalculating('seat_nav');
            revertWheelchairMode();
            console.log(`Seat route stopped: ${seatKey}`);
            return;
        }
        if (movingToSeatId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
            setMovingToSeatId(null);
        }
        if (activeSeatRouteId && !activeSeatRouteId.startsWith('not_found:') && !activeSeatRouteId.startsWith('not_available:')) {
            try { sendMessage('seatNavigate', { section: activeSeatRouteId.split('-')[0], row: activeSeatRouteId.split('-')[1], seat: activeSeatRouteId.split('-').slice(2).join('-'), action: 'stop' }); } catch {}
        }
        lastSeatPositionRef.current = null;
        clearSeatRouteSwapState();
        setActiveSeatRouteId(seatKey);
        // Reset the ready gate so the play FAB stays hidden until Kit
        // confirms the new route via `navmeshRouteReady` (see
        // AppUIContext.seatStreamOverlayActive).
        markRouteCalculating('seat_nav');
        try { sendMessage('seatNavigate', seatPayload); } catch {}
        console.log(`Seat navigate request sent: ${seatKey}`);
    }, [activeSeatRouteId, movingToSeatId, revertWheelchairMode, clearSeatRouteSwapState, markRouteCalculating]);

    const handleSeatMoveStart = useCallback(() => {
        if (!activeSeatRouteId || activeSeatRouteId.includes(':')) return;
        const pos = lastSeatPositionRef.current;
        if (!pos || pos.length < 3) return;
        setMovingToSeatId(activeSeatRouteId);
        try {
            sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: true, routeId: 'seat_nav', endPos: pos, endpointPath: null });
        } catch {}
        console.log(`Seat auto-move started: seat ${activeSeatRouteId}`);
    }, [activeSeatRouteId]);

    const handleSeatMoveStop = useCallback(() => {
        if (!movingToSeatId) return;
        const seatNum = movingToSeatId;
        try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
        setMovingToSeatId(null);
        console.log(`Seat auto-move stopped: seat ${seatNum}`);
    }, [movingToSeatId]);

    const handleSeatRouteDismiss = useCallback(() => {
        if (movingToSeatId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
            setMovingToSeatId(null);
        }
        const rid = activeSeatRouteId;
        if (!rid) return;
        if (!rid.includes(':')) {
            const parts = rid.split('-');
            if (parts.length >= 3) {
                try {
                    sendMessage('seatNavigate', {
                        section: parts[0],
                        row: parts[1],
                        seat: parts.slice(2).join('-'),
                        action: 'stop',
                    });
                } catch {}
            }
        }
        try { sendMessage('navmeshRouteStop', { routeId: 'player' }); } catch {}
        try { sendMessage('navmeshRouteStop', { routeId: 'seat_nav' }); } catch {}
        setActiveSeatRouteId(null);
        lastSeatPositionRef.current = null;
        clearSeatRouteSwapState();
        markRouteCalculating('seat_nav');
        revertWheelchairMode();
        setRouteMeasureByRouteId((prev) => {
            const next = { ...prev };
            delete next['seat_nav'];
            return next;
        });
    }, [activeSeatRouteId, movingToSeatId, revertWheelchairMode, setRouteMeasureByRouteId, clearSeatRouteSwapState, markRouteCalculating]);

    const handleSeatTeleport = useCallback((query: SeatQuery) => {
        if (!query.section || !query.row || !query.seat) return;
        if (movingToSeatId) {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', autoMove: false, routeId: 'player', endPos: null, endpointPath: null }); } catch {}
            setMovingToSeatId(null);
        }
        if (activeSeatRouteId && !activeSeatRouteId.includes(':')) {
            try { sendMessage('seatNavigate', { section: activeSeatRouteId.split('-')[0], row: activeSeatRouteId.split('-')[1], seat: activeSeatRouteId.split('-').slice(2).join('-'), action: 'stop' }); } catch {}
            setActiveSeatRouteId(null);
            lastSeatPositionRef.current = null;
        }
        const seatPayload = { section: query.section, row: query.row, seat: query.seat };
        beginViewTransition({
            target: 'firstPerson',
            message: i18n.t('streaming.switchingFirstPerson'),
            onFadeOutComplete: () => {
                try {
                    sendMessage('seatTeleport', seatPayload);
                } catch {
                    /* stream channel */
                }
                console.log(`Seat teleport request sent: ${query.section}-${query.row}-${query.seat}`);
            },
        });
    }, [activeSeatRouteId, movingToSeatId]);

    const handleRefreshSeatRouteMeasure = useCallback(() => {
        if (!activeSeatRouteId || activeSeatRouteId.includes(':')) return;
        const parts = activeSeatRouteId.split('-');
        if (parts.length < 3) return;
        try { sendMessage('seatNavigate', { section: parts[0], row: parts[1], seat: parts.slice(2).join('-') }); } catch {}
    }, [activeSeatRouteId]);

    const handleSeatingLayoutChange = useCallback((variant: string) => {
        try { sendMessage('seatLayoutChange', { variant }); } catch {}
        console.log(`Seating layout change request sent: ${variant}`);
    }, []);

    const handleSeatedCrowdLayoutChange = useCallback((variant: string) => {
        try { sendMessage('seatedCrowdLayoutChange', { variant }); } catch {}
        console.log(`Seated crowd density change request sent: ${variant}`);
    }, []);

    return {
        activeSeatRouteId, setActiveSeatRouteId,
        movingToSeatId, setMovingToSeatId,
        lastSeatPositionRef,
        seatRouteFromSeatRef,
        seatRouteDisplayLabel,
        setSeatRouteSwapState,
        clearSeatRouteSwapState,
        seatingLayout, setSeatingLayout,
        availableSeatingLayouts, setAvailableSeatingLayouts,
        seatedCrowdLayout, setSeatedCrowdLayout,
        availableSeatedCrowdLayouts, setAvailableSeatedCrowdLayouts,
        seatWidgetOpen, setSeatWidgetOpen,
        handleSeatNavigate,
        handleSeatMoveStart,
        handleSeatMoveStop,
        handleSeatRouteDismiss,
        handleSeatTeleport,
        handleRefreshSeatRouteMeasure,
        handleSeatingLayoutChange,
        handleSeatedCrowdLayoutChange,
    };
}
