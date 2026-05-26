/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 *
 * Shared domain types used by both CU and dev mode components.
 */

export const LENS_PRESETS = [
    { label: 'Wide', focalLength: 8 },
    { label: 'Normal', focalLength: 24 },
    { label: 'Zoom', focalLength: 50 },
    { label: 'Tele', focalLength: 100 },
] as const;

export const ZOOM_STEP = 4;

export type CameraType = 'first_person' | 'bird_eye' | 'space';
export type PhysicsState = 'disabled' | 'enabled';
export type ControlMode = 'pointClick' | 'wasd' | 'joystick';

export interface InteractionBehavior {
    type: string;
    sound?: string;
    message?: string;
    ui?: Record<string, any>;
    actions?: Record<string, any>;
}

export interface InteractionPointDef {
    id: string;
    label?: string;
    category?: string;
    scene?: string;
    position?: {
        type: string;
        primPath?: string;
        coordinates?: number[];
        latitude?: number;
        longitude?: number;
    };
    trigger?: {
        type: string;
        radius?: number;
        radiusMeters?: number;
        xzOnly?: boolean;
        oneShot?: boolean;
        activation?: string;
    };
    behaviors?: InteractionBehavior[];
}

export interface NavigationSpot {
    id: string;
    label: string;
    icon: string;
    primPath: string;
}

/** Values from Kit `navigation_guide` / `navmeshRouteMeasure` navigation fields */
export type NavigationGuideAction =
    | 'straight'
    | 'turn_left'
    | 'turn_right'
    | 'approach';

export interface NavigationGuideStep {
    action: NavigationGuideAction;
    distanceMeters?: number;
}

export interface RouteMeasure {
    success: boolean;
    error?: string;
    distanceMetersBase: number;
    estimatedTimeSecondsBase: number;
    distanceMetersActual?: number;
    estimatedTimeSecondsActual?: number;
    distanceMetersCrowdDelta?: number;
    estimatedTimeSecondsCrowdDelta?: number;
    distanceMetersSoundDelta?: number;
    estimatedTimeSecondsSoundDelta?: number;
    /** Turn-by-turn plan from `navmeshRouteGuide` */
    navigationDestinationKind?: 'seat' | 'exit' | 'restroom' | 'quiet_zone' | 'unknown';
    navigationSteps?: NavigationGuideStep[];
    navigationTotalMeters?: number;
    /** Live: distance along path to next maneuver (`navmeshRouteMeasure`) */
    navigationNextMeters?: number;
    /** Live: `turn_left` | `turn_right` | `approach` */
    navigationNextAction?: string;
}

export interface ExitResult {
    exitRef: string | number[];
    exitId: string;
    success: boolean;
    error?: string;
    distanceMetersBase: number;
    estimatedTimeSecondsBase: number;
    distanceMetersActual: number;
    estimatedTimeSecondsActual: number;
    metadata?: Record<string, any>;
}

export interface PoiResult {
    poiRef: string | number[];
    poiId: string;
    success: boolean;
    error?: string;
    distanceMetersBase: number;
    estimatedTimeSecondsBase: number;
    distanceMetersActual: number;
    estimatedTimeSecondsActual: number;
    metadata?: Record<string, any>;
}

export interface OsmRouteInfo {
    distanceMeters: number;
    estimatedTimeSeconds: number;
    poiId: string;
}

export interface CameraDataStats {
    current: number;
    unique_last_1m: number;
    avg_concurrent_1m: number;
    traffic_level?: string;
}

export type CameraDepthStatus = 'idle' | 'capturing' | 'done' | 'detecting' | 'obstacles_done' | 'error';

/** One vehicle row from Kit `transitLiveOverlayStatus.vehicles` (Västtrafik or GTFS-RT dev snapshot). */
export interface TransitLiveOverlayVehicleRow {
    token: string;
    sceneXyzCm: [number, number, number];
    yawDeg: number;
    feedId?: string;
    lat?: number;
    lon?: number;
    routeId?: string;
    bearing?: number | null;
    isTram?: boolean;
    line?: string;
    journeyName?: string;
    direction?: string;
    state?: string;
    delayMinutes?: number;
    tripId?: string;
    speedMps?: number;
    licensePlate?: string;
}

export interface TransitLiveOverlayStatusState {
    enabled: boolean;
    vehicleCount: number;
    lastError: string | null;
    lastFetchEpochMs: number;
    hasApiKey: boolean;
    transitSource?: string;
    hint?: string;
    vehicles: TransitLiveOverlayVehicleRow[];
}
