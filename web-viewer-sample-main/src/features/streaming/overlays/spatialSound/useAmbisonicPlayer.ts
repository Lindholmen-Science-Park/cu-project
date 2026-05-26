import { useCallback, useEffect, useRef, useState } from 'react';
import omnitoneScriptUrl from 'omnitone/build/omnitone.js?url';
import type { FOARenderer, OmnitoneApi } from '../../../../types/omnitone';
import { getSharedAudioContext, unlockSharedAudioContext } from '../../audio/sharedAudioContext';
import { parseVtt, findActiveCue, type VttCue } from './parseVtt';

/*
 * Omnitone ships as a UMD/IIFE script with no ESM exports, so we cannot
 * `import Omnitone from 'omnitone'` (the production Rollup build rejects it).
 * Inject the bundled script once, then read the global `window.Omnitone`.
 */
let omnitonePromise: Promise<OmnitoneApi> | null = null;
function loadOmnitone(): Promise<OmnitoneApi> {
    if (window.Omnitone) return Promise.resolve(window.Omnitone);
    if (omnitonePromise) return omnitonePromise;
    omnitonePromise = new Promise<OmnitoneApi>((resolve, reject) => {
        const existing = document.querySelector(
            `script[data-omnitone="1"]`,
        ) as HTMLScriptElement | null;
        const onResolve = () => {
            if (window.Omnitone) resolve(window.Omnitone);
            else reject(new Error('Omnitone script loaded but window.Omnitone is undefined'));
        };
        if (existing) {
            existing.addEventListener('load', onResolve, { once: true });
            existing.addEventListener('error', () => reject(new Error('Omnitone script failed to load')), { once: true });
            return;
        }
        const s = document.createElement('script');
        s.src = omnitoneScriptUrl;
        s.async = true;
        s.dataset.omnitone = '1';
        s.onload = onResolve;
        s.onerror = () => reject(new Error('Omnitone script failed to load'));
        document.head.appendChild(s);
    }).catch((err) => {
        omnitonePromise = null;
        throw err;
    });
    return omnitonePromise;
}

/**
 * React hook that owns the audio graph for the Spatial Sound Overlay.
 *
 * Pipeline:
 *   fetch(url) -> ArrayBuffer -> ctx.decodeAudioData -> AudioBuffer
 *     4 channels (AmbiX FOA) -> AudioBufferSourceNode -> FOARenderer -> destination
 *     1 / 2 channels         -> AudioBufferSourceNode -> destination (no spatialization)
 *
 * `setRotation(yawDeg, pitchDeg)` rotates the sound field so the listener's
 * head tracks the same drag / device-orientation deltas that are sent to Kit
 * as `touchLookDelta`. The matrix passed to Omnitone is the **world-to-listener**
 * rotation in Three.js Y-up convention, flattened **column-major** — see the
 * comment in `buildRotationMatrix3` for the gotcha.
 */

const DEG_TO_RAD = Math.PI / 180;

export type AmbisonicPlayerApi = {
    load: (url: string, captionsUrl?: string) => Promise<void>;
    play: () => Promise<void>;
    pause: () => void;
    seek: (seconds: number) => void;
    setRotation: (yawDeg: number, pitchDeg: number) => void;
    /**
     * Mute / unmute the output by flipping the post-renderer gain node between 0 and 1.
     * Bypassing the in-flight buffer source means the playhead keeps advancing — the
     * user just hears silence — so we don't desync from the rest of the player state.
     */
    setMuted: (muted: boolean) => void;
    isPlaying: boolean;
    currentTime: number;
    duration: number;
    isSpatial: boolean;
    isReady: boolean;
    /** True when a captions track was successfully loaded for the current source. */
    hasCaptions: boolean;
    /** Active cue text at the current playhead, or empty string when no cue is active. */
    activeCueText: string;
};

function buildRotationMatrix3(yawRad: number, pitchRad: number): Float32Array {
    const cy = Math.cos(yawRad);
    const sy = Math.sin(yawRad);
    const cp = Math.cos(pitchRad);
    const sp = Math.sin(pitchRad);
    // World->listener rotation = Ry(yaw) * Rx(pitch) in Three.js Y-up convention.
    // Matrix rows:
    //   row 0: [ cy,     sy*sp,   sy*cp ]
    //   row 1: [ 0,      cp,     -sp    ]
    //   row 2: [-sy,     cy*sp,   cy*cp ]
    // Omnitone reads the Float32Array as a Three.js-style column-major 3x3
    // (FOARenderer.setRotationMatrixFromCamera inverts a camera matrix and
    // feeds .elements into setRotationMatrix4, which is column-major). Flatten
    // column-by-column or the rotation comes out transposed (= inverse) and
    // listener head movement barely affects the sound field.
    return new Float32Array([
        cy,        0,    -sy,        // column 0
        sy * sp,   cp,    cy * sp,   // column 1
        sy * cp,  -sp,    cy * cp,   // column 2
    ]);
}

export function useAmbisonicPlayer(): AmbisonicPlayerApi {
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [isSpatial, setIsSpatial] = useState(false);
    const [isReady, setIsReady] = useState(false);
    const [hasCaptions, setHasCaptions] = useState(false);
    const [activeCueText, setActiveCueText] = useState('');

    const ctxRef = useRef<AudioContext | null>(null);
    const bufferRef = useRef<AudioBuffer | null>(null);
    const sourceRef = useRef<AudioBufferSourceNode | null>(null);
    const foaRef = useRef<FOARenderer | null>(null);
    const foaReadyRef = useRef(false);
    // Set true on unmount. Every async path must check this after each
    // await and bail before touching the audio graph, or an in-flight
    // play() can leak an orphan AudioBufferSourceNode that keeps
    // playing after the overlay is closed.
    const destroyedRef = useRef(false);
    /**
     * Single GainNode sitting between the renderer/source and `ctx.destination`. Gives
     * us a clean, sample-accurate mute toggle that survives reload/seek/spatial-vs-stereo
     * branch changes — both connect their tail end to this node instead of the
     * destination directly. Initial gain = current `mutedRef.current` value so a mute
     * preference applied before audio actually starts is honoured the first frame the
     * source hits the graph.
     */
    const gainRef = useRef<GainNode | null>(null);
    const mutedRef = useRef(false);
    const pauseOffsetRef = useRef(0);
    const startCtxTimeRef = useRef(0);
    const isPlayingRef = useRef(false);
    const rafRef = useRef<number | null>(null);
    const rotYawRef = useRef(0);
    const rotPitchRef = useRef(0);
    const loadPromiseRef = useRef<Promise<void> | null>(null);
    const cuesRef = useRef<VttCue[]>([]);
    const lastCueTextRef = useRef('');

    const stopRafLoop = useCallback(() => {
        if (rafRef.current != null) {
            cancelAnimationFrame(rafRef.current);
            rafRef.current = null;
        }
    }, []);

    const tick = useCallback(() => {
        if (!isPlayingRef.current) {
            rafRef.current = null;
            return;
        }
        const ctx = ctxRef.current;
        const buf = bufferRef.current;
        if (ctx && buf) {
            const t = pauseOffsetRef.current + (ctx.currentTime - startCtxTimeRef.current);
            const clamped = Math.min(Math.max(t, 0), buf.duration);
            setCurrentTime(clamped);

            const cues = cuesRef.current;
            if (cues.length) {
                const active = findActiveCue(cues, clamped);
                const next = active ? active.text : '';
                if (next !== lastCueTextRef.current) {
                    lastCueTextRef.current = next;
                    setActiveCueText(next);
                }
            }
        }
        rafRef.current = requestAnimationFrame(tick);
    }, []);

    const startRafLoop = useCallback(() => {
        if (rafRef.current == null) {
            rafRef.current = requestAnimationFrame(tick);
        }
    }, [tick]);

    const ensureContext = useCallback(async () => {
        if (!ctxRef.current) {
            ctxRef.current = getSharedAudioContext();
        }
        if (!gainRef.current) {
            const ctx = ctxRef.current;
            const gain = ctx.createGain();
            gain.gain.value = mutedRef.current ? 0 : 1;
            gain.connect(ctx.destination);
            gainRef.current = gain;
        }
        await unlockSharedAudioContext();
    }, []);

    const ensureFoa = useCallback(async () => {
        if (foaRef.current && foaReadyRef.current) return;
        const ctx = ctxRef.current!;
        const Omnitone = await loadOmnitone();
        const foa = Omnitone.createFOARenderer(ctx, { ambisonicOrder: 1 });
        await foa.initialize();
        // Route through the mute gain so toggling mute affects spatial playback too.
        // `ensureContext()` always runs before `ensureFoa()` (callers await it in
        // `load()`), so `gainRef.current` is guaranteed non-null here.
        foa.output.connect(gainRef.current!);
        foaRef.current = foa;
        foaReadyRef.current = true;
        const yaw = rotYawRef.current * DEG_TO_RAD;
        const pitch = rotPitchRef.current * DEG_TO_RAD;
        foa.setRotationMatrix3(buildRotationMatrix3(yaw, pitch));
    }, []);

    const stopCurrentSource = useCallback(() => {
        const src = sourceRef.current;
        if (src) {
            src.onended = null;
            try { src.stop(); } catch { /* already stopped */ }
            try { src.disconnect(); } catch { /* already disconnected */ }
        }
        sourceRef.current = null;
    }, []);

    const loadCaptions = useCallback(async (captionsUrl: string | undefined) => {
        cuesRef.current = [];
        lastCueTextRef.current = '';
        setActiveCueText('');
        setHasCaptions(false);
        if (!captionsUrl) return;
        try {
            const res = await fetch(captionsUrl);
            if (!res.ok) {
                console.warn(`[useAmbisonicPlayer] captions fetch ${res.status}: ${captionsUrl}`);
                return;
            }
            const text = await res.text();
            const cues = parseVtt(text);
            if (cues.length) {
                cuesRef.current = cues;
                setHasCaptions(true);
            } else {
                console.warn('[useAmbisonicPlayer] captions file parsed but contained zero cues');
            }
        } catch (err) {
            console.warn('[useAmbisonicPlayer] captions fetch failed', err);
        }
    }, []);

    const load = useCallback(async (url: string, captionsUrl?: string) => {
        setIsReady(false);
        const loadTask = (async () => {
            await ensureContext();
            if (destroyedRef.current) return;

            // Captions and audio fetch are independent — kick the captions
            // request off in parallel so we don't pay its latency twice.
            const captionsTask = loadCaptions(captionsUrl);

            let response: Response;
            try {
                response = await fetch(url);
            } catch (err) {
                console.error('[useAmbisonicPlayer] fetch failed', err);
                await captionsTask;
                return;
            }
            if (destroyedRef.current) return;
            const arrayBuf = await response.arrayBuffer();
            if (destroyedRef.current) return;
            const ctxForDecode = ctxRef.current;
            if (!ctxForDecode) return;
            const audioBuf = await ctxForDecode.decodeAudioData(arrayBuf);
            if (destroyedRef.current) return;

            bufferRef.current = audioBuf;
            setDuration(audioBuf.duration);
            pauseOffsetRef.current = 0;
            setCurrentTime(0);

            const channels = audioBuf.numberOfChannels;
            const spatial = channels === 4;
            setIsSpatial(spatial);
            if (spatial) {
                try {
                    await ensureFoa();
                } catch (err) {
                    console.warn('[useAmbisonicPlayer] FOA init failed, falling back to stereo', err);
                    setIsSpatial(false);
                }
                if (destroyedRef.current) return;
            } else if (channels !== 1 && channels !== 2) {
                console.warn(`[useAmbisonicPlayer] unexpected channel count ${channels}; playing as-is without spatialization`);
            }

            await captionsTask;
            if (destroyedRef.current) return;
            setIsReady(true);
        })();
        loadPromiseRef.current = loadTask;
        await loadTask;
    }, [ensureContext, ensureFoa, loadCaptions]);

    const play = useCallback(async () => {
        // Files can be large (100+ MB); if a user clicks the start button before
        // the fetch/decode has finished, wait for the in-flight load so we don't
        // silently no-op and leave the user staring at a stuck pause button.
        if (loadPromiseRef.current) {
            try { await loadPromiseRef.current; } catch { /* errors already logged in load */ }
        }
        if (destroyedRef.current) return;
        const ctx = ctxRef.current;
        const buf = bufferRef.current;
        if (!ctx || !buf) return;
        await unlockSharedAudioContext();
        if (destroyedRef.current) return;

        stopCurrentSource();

        const src = ctx.createBufferSource();
        src.buffer = buf;

        const spatial = isSpatial && foaRef.current && foaReadyRef.current;
        if (spatial) {
            // Keep the 4 channels discrete into the FOA renderer
            (src as any).channelCount = 4;
            (src as any).channelCountMode = 'explicit';
            (src as any).channelInterpretation = 'discrete';
            src.connect(foaRef.current!.input);
        } else {
            // Stereo/mono path also goes through the mute gain (vs. straight to destination).
            src.connect(gainRef.current ?? ctx.destination);
        }

        const offset = Math.min(Math.max(pauseOffsetRef.current, 0), buf.duration);
        src.onended = () => {
            if (sourceRef.current !== src) return;
            // Natural end (we clear onended manually on pause/seek)
            sourceRef.current = null;
            isPlayingRef.current = false;
            pauseOffsetRef.current = 0;
            setIsPlaying(false);
            setCurrentTime(buf.duration);
            stopRafLoop();
        };
        src.start(0, offset);
        // Tear down immediately if cleanup ran during the await above.
        if (destroyedRef.current) {
            try { src.onended = null; src.stop(); src.disconnect(); } catch { /* ignore */ }
            return;
        }
        sourceRef.current = src;
        startCtxTimeRef.current = ctx.currentTime;
        isPlayingRef.current = true;
        setIsPlaying(true);
        startRafLoop();
    }, [isSpatial, stopCurrentSource, startRafLoop, stopRafLoop]);

    const pause = useCallback(() => {
        const ctx = ctxRef.current;
        const buf = bufferRef.current;
        if (!ctx || !buf || !isPlayingRef.current) return;
        const elapsed = ctx.currentTime - startCtxTimeRef.current;
        pauseOffsetRef.current = Math.min(Math.max(pauseOffsetRef.current + elapsed, 0), buf.duration);
        stopCurrentSource();
        isPlayingRef.current = false;
        setIsPlaying(false);
        setCurrentTime(pauseOffsetRef.current);
        stopRafLoop();
        // Re-evaluate the cue at the paused position so the caption matches the
        // visible playhead even with the rAF loop stopped.
        if (cuesRef.current.length) {
            const active = findActiveCue(cuesRef.current, pauseOffsetRef.current);
            const next = active ? active.text : '';
            if (next !== lastCueTextRef.current) {
                lastCueTextRef.current = next;
                setActiveCueText(next);
            }
        }
    }, [stopCurrentSource, stopRafLoop]);

    const seek = useCallback((seconds: number) => {
        const buf = bufferRef.current;
        if (!buf) return;
        const target = Math.min(Math.max(seconds, 0), buf.duration);
        const wasPlaying = isPlayingRef.current;
        if (wasPlaying) stopCurrentSource();
        isPlayingRef.current = false;
        pauseOffsetRef.current = target;
        setCurrentTime(target);
        if (cuesRef.current.length) {
            const active = findActiveCue(cuesRef.current, target);
            const next = active ? active.text : '';
            if (next !== lastCueTextRef.current) {
                lastCueTextRef.current = next;
                setActiveCueText(next);
            }
        }
        if (wasPlaying) {
            void play();
        } else {
            setIsPlaying(false);
            stopRafLoop();
        }
    }, [play, stopCurrentSource, stopRafLoop]);

    /**
     * Flip the mute gain. Stored in `mutedRef` so a preference applied before
     * `ensureContext()` runs is honoured the moment the gain node is created.
     * Uses an immediate value write rather than a ramp — captions card already
     * gives the user instant visual feedback so we want the audio to match it.
     */
    const setMuted = useCallback((muted: boolean) => {
        mutedRef.current = muted;
        const gain = gainRef.current;
        if (gain) gain.gain.value = muted ? 0 : 1;
    }, []);

    const setRotation = useCallback((yawDeg: number, pitchDeg: number) => {
        rotYawRef.current = yawDeg;
        rotPitchRef.current = pitchDeg;
        const foa = foaRef.current;
        if (foa && foaReadyRef.current) {
            const yaw = yawDeg * DEG_TO_RAD;
            const pitch = pitchDeg * DEG_TO_RAD;
            foa.setRotationMatrix3(buildRotationMatrix3(yaw, pitch));
        }
    }, []);

    useEffect(() => {
        // Reset on (re-)mount for hot reload.
        destroyedRef.current = false;
        return () => {
            // Flip the kill switch first so in-flight awaits bail out.
            destroyedRef.current = true;
            stopCurrentSource();
            stopRafLoop();
            const foa = foaRef.current;
            if (foa) {
                try { foa.output.disconnect(); } catch { /* ignore */ }
            }
            const gain = gainRef.current;
            if (gain) {
                try { gain.disconnect(); } catch { /* ignore */ }
            }
            gainRef.current = null;
            foaRef.current = null;
            foaReadyRef.current = false;
            bufferRef.current = null;
            loadPromiseRef.current = null;
        };
    }, [stopCurrentSource, stopRafLoop]);

    return {
        load,
        play,
        pause,
        seek,
        setRotation,
        setMuted,
        isPlaying,
        currentTime,
        duration,
        isSpatial,
        isReady,
        hasCaptions,
        activeCueText,
    };
}
