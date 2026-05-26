import { useEffect, useRef } from 'react';
import { useSpatialSound, useStream } from '../contexts';
import { getAmbientSoundEngine } from '../audio/ambientSoundEngine';
import { unlockSharedAudioContext } from '../audio/sharedAudioContext';

const AMBIENT_DUCK_LEVEL = 0.15;

/**
 * Wires the browser-side ambient sound engine to the streaming lifecycle.
 *
 * - Starts the engine once the stream is ready (so the shared AudioContext
 *   exists before we attempt to unlock it).
 * - Unlocks the shared AudioContext on the first document-level pointer /
 *   key / touch gesture — any audio-producing browser requires a user
 *   gesture before ``ctx.resume()`` succeeds.
 * - Ducks the ambient bus while the Spatial Sound Overlay is open so the
 *   ambisonic experience isn't fighting a crowd of ambient sources.
 *
 * The hook intentionally does not call ``setEmitters`` / ``updateListener``
 * itself — those are driven by ``worldStateHandlers`` and the central
 * custom-event dispatcher so any pose/emitter update routes through the
 * same pipeline other features use.
 */
export function useAmbientSoundEngine(): void {
    const stream = useStream();
    const spatialSound = useSpatialSound();
    const startedRef = useRef(false);
    const unlockedRef = useRef(false);

    useEffect(() => {
        if (!stream.streamReady || startedRef.current) return;
        getAmbientSoundEngine().start();
        startedRef.current = true;
    }, [stream.streamReady]);

    useEffect(() => {
        if (unlockedRef.current) return;

        const handleFirstGesture = () => {
            if (unlockedRef.current) return;
            unlockedRef.current = true;
            void unlockSharedAudioContext().then(() => {
                getAmbientSoundEngine().markUnlocked();
            });
            window.removeEventListener('pointerdown', handleFirstGesture, true);
            window.removeEventListener('keydown', handleFirstGesture, true);
            window.removeEventListener('touchstart', handleFirstGesture, true);
        };

        window.addEventListener('pointerdown', handleFirstGesture, true);
        window.addEventListener('keydown', handleFirstGesture, true);
        window.addEventListener('touchstart', handleFirstGesture, true);

        return () => {
            window.removeEventListener('pointerdown', handleFirstGesture, true);
            window.removeEventListener('keydown', handleFirstGesture, true);
            window.removeEventListener('touchstart', handleFirstGesture, true);
        };
    }, []);

    useEffect(() => {
        const engine = getAmbientSoundEngine();
        engine.setMasterGain(spatialSound.isOpen ? AMBIENT_DUCK_LEVEL : 1.0);
    }, [spatialSound.isOpen]);

    useEffect(() => () => {
        // Keep the singleton alive across unmounts; tearing it down would
        // force a full re-decode on every remount.  If the app is unmounting
        // entirely the browser will GC the context along with the page.
    }, []);
}
