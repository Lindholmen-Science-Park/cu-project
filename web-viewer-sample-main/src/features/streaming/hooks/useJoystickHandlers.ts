import { useCallback, useEffect, useRef } from 'react';
import { JOYSTICK_INPUT_THROTTLE_MS, sendMessage } from '../messaging';
import { ControlMode } from '../types';

export function useJoystickHandlers(streamReady: boolean, controlMode: ControlMode) {
    // Movement joystick (left stick)
    const joystickThrottleRef = useRef<{ lastSend: number; pending: { f: number; r: number } | null }>({ lastSend: 0, pending: null });

    const handleJoystickChange = useCallback((forward: number, right: number) => {
        if (!streamReady) return;
        const now = Date.now();
        const ref = joystickThrottleRef.current;
        const isRelease = Math.abs(forward) < 0.01 && Math.abs(right) < 0.01;
        if (isRelease) {
            ref.pending = null;
            ref.lastSend = now;
            try { sendMessage('joystickInput', { forward: 0, right: 0 }); } catch {}
            return;
        }
        ref.pending = { f: forward, r: right };
        if (now - ref.lastSend >= JOYSTICK_INPUT_THROTTLE_MS) {
            ref.lastSend = now;
            ref.pending = null;
            try { sendMessage('joystickInput', { forward, right }); } catch {}
        }
    }, [streamReady]);

    // Flush pending joystick updates
    useEffect(() => {
        if (!streamReady || controlMode !== 'joystick') return;
        const id = setInterval(() => {
            const ref = joystickThrottleRef.current;
            if (ref.pending && Date.now() - ref.lastSend >= JOYSTICK_INPUT_THROTTLE_MS) {
                ref.lastSend = Date.now();
                const { f, r } = ref.pending;
                ref.pending = null;
                try { sendMessage('joystickInput', { forward: f, right: r }); } catch {}
            }
        }, JOYSTICK_INPUT_THROTTLE_MS);
        return () => clearInterval(id);
    }, [streamReady, controlMode]);

    // Look joystick (right stick)
    const lookJoystickThrottleRef = useRef<{ lastSend: number; pending: { y: number; p: number } | null }>({ lastSend: 0, pending: null });

    const handleLookJoystickChange = useCallback((forward: number, right: number) => {
        if (!streamReady) return;
        const pitch = forward;
        const yaw = -right;
        const now = Date.now();
        const ref = lookJoystickThrottleRef.current;
        const isRelease = Math.abs(forward) < 0.01 && Math.abs(right) < 0.01;
        if (isRelease) {
            ref.pending = null;
            ref.lastSend = now;
            try { sendMessage('lookInput', { yaw: 0, pitch: 0 }); } catch {}
            return;
        }
        ref.pending = { y: yaw, p: pitch };
        if (now - ref.lastSend >= JOYSTICK_INPUT_THROTTLE_MS) {
            ref.lastSend = now;
            ref.pending = null;
            try { sendMessage('lookInput', { yaw, pitch }); } catch {}
        }
    }, [streamReady]);

    // Flush pending look joystick updates
    useEffect(() => {
        if (!streamReady || controlMode !== 'joystick') return;
        const id = setInterval(() => {
            const ref = lookJoystickThrottleRef.current;
            if (ref.pending && Date.now() - ref.lastSend >= JOYSTICK_INPUT_THROTTLE_MS) {
                ref.lastSend = Date.now();
                const { y, p } = ref.pending;
                ref.pending = null;
                try { sendMessage('lookInput', { yaw: y, pitch: p }); } catch {}
            }
        }, JOYSTICK_INPUT_THROTTLE_MS);
        return () => clearInterval(id);
    }, [streamReady, controlMode]);

    return {
        handleJoystickChange,
        handleLookJoystickChange,
    };
}
