import { useEffect, useRef } from 'react';
import { sendMessage } from '../messaging';

export function isDeviceOrientationSupported(): boolean {
    return 'DeviceOrientationEvent' in window &&
        ('ontouchstart' in window || navigator.maxTouchPoints > 0);
}

/**
 * Request permission for DeviceOrientationEvent on iOS 13+.
 * Must be called from a user-gesture handler (click/tap).
 * Returns true if granted or if no permission is required (Android, older iOS).
 */
export async function requestOrientationPermission(): Promise<boolean> {
    const DOE = DeviceOrientationEvent as any;
    if (typeof DOE.requestPermission === 'function') {
        try {
            const result = await DOE.requestPermission();
            return result === 'granted';
        } catch {
            return false;
        }
    }
    return true;
}

const SENSITIVITY = 0.6;
const NOISE_THRESHOLD = 0.15;
const KIT_SENSITIVITY = 0.15;

/**
 * Sends device orientation deltas as `touchLookDelta` messages to Kit.
 * Alpha (yaw) maps to dx, beta (pitch) maps to dy.
 * Only active on devices with a gyroscope; no-op on desktop.
 *
 * @param onOrientationDelta Optional callback receiving (dYaw, dPitch) in degrees,
 *   matching Kit's camera convention: positive yaw = look right, positive pitch = look up.
 *   Used by the spatial audio system to track listener orientation on the web side.
 * @param options.suppressKitDispatch When true, do **not** post `touchLookDelta` to
 *   Kit. Use this for purely browser-side experiences (e.g. the 360° video sphere)
 *   where the Kit camera must stay still while the local player rotates.
 */
export function useDeviceOrientation(
    enabled: boolean,
    onOrientationDelta?: (dYaw: number, dPitch: number) => void,
    options?: { suppressKitDispatch?: boolean },
): { isSupported: boolean } {
    const prevAlpha = useRef<number | null>(null);
    const prevBeta = useRef<number | null>(null);
    const isSupported = isDeviceOrientationSupported();
    const onDeltaRef = useRef(onOrientationDelta);
    onDeltaRef.current = onOrientationDelta;
    const suppressKitDispatch = options?.suppressKitDispatch === true;

    useEffect(() => {
        if (!enabled || !isSupported) return;

        prevAlpha.current = null;
        prevBeta.current = null;

        const handleOrientation = (e: DeviceOrientationEvent) => {
            if (e.alpha === null || e.beta === null) return;

            if (prevAlpha.current !== null && prevBeta.current !== null) {
                let dAlpha = e.alpha - prevAlpha.current;
                const dBeta = e.beta - prevBeta.current;

                if (dAlpha > 180) dAlpha -= 360;
                if (dAlpha < -180) dAlpha += 360;

                if (Math.abs(dAlpha) > NOISE_THRESHOLD || Math.abs(dBeta) > NOISE_THRESHOLD) {
                    const dx = -dAlpha * SENSITIVITY;
                    const dy = dBeta * SENSITIVITY;
                    if (!suppressKitDispatch) {
                        sendMessage('touchLookDelta', { dx, dy });
                    }

                    // Kit applies: yaw += -dx * 0.15, pitch += dy * 0.15
                    // then playerInputController negates pitch.
                    // Net: dYaw = -dx * 0.15 = dAlpha * SENSITIVITY * 0.15
                    //       dPitch = -(dy * 0.15) = -(dBeta * SENSITIVITY * 0.15)
                    if (onDeltaRef.current) {
                        onDeltaRef.current(
                            -dx * KIT_SENSITIVITY,
                            -(dy * KIT_SENSITIVITY),
                        );
                    }
                }
            }

            prevAlpha.current = e.alpha;
            prevBeta.current = e.beta;
        };

        window.addEventListener('deviceorientation', handleOrientation);
        return () => {
            window.removeEventListener('deviceorientation', handleOrientation);
            prevAlpha.current = null;
            prevBeta.current = null;
        };
    }, [enabled, isSupported, suppressKitDispatch]);

    return { isSupported };
}
