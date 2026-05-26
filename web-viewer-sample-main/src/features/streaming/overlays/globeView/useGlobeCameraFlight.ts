import { useState, useCallback, useRef } from 'react';
import { Cartesian3, Math as CesiumMath, type Viewer } from 'cesium';

export interface FlightWaypoint {
    lat: number;
    lon: number;
    alt: number;
    duration: number;
    heading?: number;
    pitch?: number;
    maxHeight?: number;
}

/**
 * Drives sequential camera.flyTo() calls through waypoints.
 * Uses Cesium's native flyTo for smooth GPU-optimized interpolation.
 * Attaches a preUpdate listener to report altitude each frame
 * (for cloud layer effects). Disables user input during flight.
 */
export function useGlobeCameraFlight(waypoints: FlightWaypoint[]) {
    const [flightComplete, setFlightComplete] = useState(false);
    const flyingRef = useRef(false);
    const viewerRef = useRef<Viewer | null>(null);
    const preUpdateRef = useRef<(() => void) | null>(null);
    const onProgressRef = useRef<((alt: number) => void) | null>(null);

    const startFlight = useCallback((
        viewer: Viewer,
        onProgress?: (altitude: number) => void,
    ) => {
        if (flyingRef.current || waypoints.length === 0) return;
        flyingRef.current = true;
        viewerRef.current = viewer;
        onProgressRef.current = onProgress ?? null;
        setFlightComplete(false);

        viewer.scene.screenSpaceCameraController.enableInputs = false;

        const handler = () => {
            const alt = viewer.camera.positionCartographic.height;
            onProgressRef.current?.(alt);
        };
        viewer.scene.preUpdate.addEventListener(handler);
        preUpdateRef.current = handler;

        let idx = 0;
        const flyNext = () => {
            if (idx >= waypoints.length) {
                flyingRef.current = false;
                setFlightComplete(true);
                return;
            }
            const wp = waypoints[idx];

            viewer.camera.flyTo({
                destination: Cartesian3.fromDegrees(wp.lon, wp.lat, wp.alt),
                orientation: {
                    heading: CesiumMath.toRadians(wp.heading ?? 0),
                    pitch: CesiumMath.toRadians(wp.pitch ?? -90),
                    roll: 0,
                },
                duration: wp.duration,
                maximumHeight: wp.maxHeight,
                complete: () => { idx++; flyNext(); },
                cancel: () => { idx++; flyNext(); },
            });
        };
        flyNext();
    }, [waypoints]);

    const reset = useCallback(() => {
        if (viewerRef.current && preUpdateRef.current) {
            try {
                viewerRef.current.scene.preUpdate.removeEventListener(preUpdateRef.current);
            } catch { /* viewer may be destroyed */ }
        }
        preUpdateRef.current = null;
        onProgressRef.current = null;
        if (viewerRef.current) {
            try {
                viewerRef.current.scene.screenSpaceCameraController.enableInputs = true;
            } catch { /* viewer may be destroyed */ }
        }
        flyingRef.current = false;
        viewerRef.current = null;
        setFlightComplete(false);
    }, []);

    return { flightComplete, startFlight, reset };
}
