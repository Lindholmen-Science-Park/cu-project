/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 */
import type { CSSProperties } from 'react';
import type { RouteMeasure } from './types';

/** Valid seat route (Find my seat) — top info card + bottom Play / Pause on #remote-video */
export interface SeatNavigationOverlayProps {
    isMoving: boolean;
    seatLabel: string;
    /** Shown in header and play tooltips instead of `formatSeatLabel(seatLabel)` (e.g. restroom “Toilets — section n”) */
    displayLabel?: string;
    onPlay: () => void;
    onStop: () => void;
    /** Dismiss the seat route entirely (same as SeatNavigateWidget dismiss) */
    onDismiss: () => void;
    routeMeasure?: RouteMeasure | null;
    routeMeasureEnabled?: boolean;
    /**
     * Bird-eye seat-directions swap mode: the `seat_nav` route is reversed and
     * the player is walking back to their previous FP position. Forces the
     * turn-by-turn approach pill to read "x m to destination" instead of
     * "x m to your seat" (Kit still sends `destinationKind: 'seat'`).
     */
    approachUsesGenericLabel?: boolean;
}

/** Full prop surface for the WebRTC canvas (used by `Window.tsx` and `AppStreamConnected`). */
export interface AppStreamCoreProps {
    sessionId: string;
    backendUrl: string;
    signalingserver: string;
    signalingport: number;
    mediaserver: string;
    mediaport: number;
    accessToken: string;
    style?: CSSProperties;
    onStarted: () => void;
    onStreamFailed: () => void;
    onLoggedIn: (userId: string) => void;
    handleCustomEvent: (event: any) => void;
    nextClickPlacesMarker?: boolean;
    nextClickPlacesIncident?: boolean;
    nextClickPlacesCamera?: boolean;
    incidentSizePreset?: '1x1' | '2x2' | '2x1';
    incidentShape?: 'cube' | 'cone' | 'torus';
    onMarkerClickConsumed?: () => void;
    onIncidentClickConsumed?: () => void;
    onCameraClickConsumed?: () => void;
    pointClickEnabled?: boolean;
    /** Dev: stream picks use ``osmRouteOverlayMarker`` so OSM route overlay hits resolve like navigation targets. */
    osmRouteOverlayActive?: boolean;
    osmNavigateActive?: boolean;
    isBirdEye?: boolean;
    /**
     * Bird-eye pin-anywhere is suppressed once a route polyline is already
     * drawn on the map (user has clicked "Get directions"). Without this
     * gate, taps on the streamed video re-snap the pin to the closest
     * waypoint and silently mutate the active route — the directions panel
     * is locked to its target at this point so re-pinning has no effect
     * the user can act on. The pin-marker-only phase (sheet open, no route
     * yet) still re-pins so the user can pick a different target before
     * confirming.
     */
    birdEyeRouteActive?: boolean;
    isViewer?: boolean;
    onLoadingStatus?: (text: string) => void;
    activeFixedCamera?: string | null;
    /** When set, shows Play (or Stop while moving) above stream bottom center */
    seatNavigationOverlay?: SeatNavigationOverlayProps | null;
    /** Figma 5691-2411 — confetti + seat graphic when user reaches seat */
    seatArrivalCelebrationVisible?: boolean;
    /** Seat key shown in the arrival overlay (e.g. "O-8-11"). */
    seatArrivalLabel?: string | null;
    /** Dismiss both celebration graphic and arrival overlay. */
    onArrivalDismiss?: () => void;
    /** POI (restroom/quiet zone) arrival top bar — no celebration image. */
    poiArrivalVisible?: boolean;
    poiArrivalLabel?: string | null;
    onPoiArrivalDismiss?: () => void;
    /** When true, swipe/drag direction is inverted (mobile-natural: swipe right → look left). */
    invertTouchLook?: boolean;
    /** When set, clicks send a pick request with this intent instead of normal navigation. */
    usdEditIntent?: string | null;
    /** When true, drag moves the selected vertex instead of rotating the camera. */
    vertexDragActive?: boolean;
}
