/**
 * Ambient sound engine — PannerNode pool for world-placed emitters.
 *
 * Kit publishes the list of ``sound_emitter_*`` prims via the
 * ``soundEmittersStatus`` event (folded into ``worldStateSync``).  This
 * module-level singleton:
 *
 *   - diffs the emitter list and adds/removes ``PannerNode`` voices
 *   - decodes each file once and caches the ``AudioBuffer``
 *   - applies the listener's world position + orientation from
 *     ``playerPose`` events (~20 Hz) to the Web Audio ``AudioListener``
 *   - exposes a master gain so the spatial overlay can duck ambient sound
 *
 * Runs completely dormant when the emitter list is empty — no decoding,
 * no nodes, no per-frame work.
 */

import { getSharedAudioContext, hasSharedAudioContext } from './sharedAudioContext';

export type SoundEmitter = {
    id: string;
    file: string;
    pos: [number, number, number];
    radius?: number;
    refDistance?: number;
    volume?: number;
    loop?: boolean;
    startDelaySec?: number;
};

export type PlayerPose = {
    pos: [number, number, number];
    forward: [number, number, number];
    up: [number, number, number];
};

type Voice = {
    id: string;
    emitter: SoundEmitter;
    source: AudioBufferSourceNode | null;
    gain: GainNode;
    panner: PannerNode;
    loading: boolean;
    failed: boolean;
};

// Resolve Kit-relative filenames to Vite URLs from the nucleus sounds glob.
const nucleusSoundModules: Record<string, string> = {};
const rawNucleusSounds = import.meta.glob(
    '@nucleus-sounds/**/*.{wav,mp3,ogg,flac}',
    { eager: true, import: 'default' },
);
for (const [path, url] of Object.entries(rawNucleusSounds)) {
    const filename = path.split('/').pop();
    if (filename) nucleusSoundModules[filename] = url as string;
}

function resolveSoundUrl(file: string): string {
    if (!file) return '';
    if (file.startsWith('http://') || file.startsWith('https://')) return file;
    return nucleusSoundModules[file] ?? file;
}

class AmbientSoundEngine {
    private _voices = new Map<string, Voice>();
    private _bufferCache = new Map<string, Promise<AudioBuffer>>();
    private _masterGain: GainNode | null = null;
    private _started = false;
    private _unlocked = false;
    private _pendingEmitters: SoundEmitter[] | null = null;
    private _pendingPose: PlayerPose | null = null;

    /** Attach to the shared AudioContext. Called after first user gesture. */
    start(): void {
        if (this._started) return;
        const ctx = getSharedAudioContext();
        this._masterGain = ctx.createGain();
        this._masterGain.gain.value = 1.0;
        this._masterGain.connect(ctx.destination);
        this._started = true;
        this._unlocked = ctx.state === 'running';

        if (this._pendingEmitters) {
            this.setEmitters(this._pendingEmitters);
            this._pendingEmitters = null;
        }
        if (this._pendingPose) {
            this.updateListener(this._pendingPose);
            this._pendingPose = null;
        }
    }

    markUnlocked(): void {
        this._unlocked = true;
        for (const voice of this._voices.values()) {
            if (!voice.source && !voice.loading && !voice.failed) {
                this._startVoice(voice);
            }
        }
    }

    setMasterGain(value: number): void {
        if (!this._masterGain) return;
        const ctx = getSharedAudioContext();
        const clamped = Math.max(0, Math.min(1, value));
        this._masterGain.gain.setTargetAtTime(clamped, ctx.currentTime, 0.05);
    }

    setEmitters(emitters: SoundEmitter[]): void {
        if (!this._started) {
            this._pendingEmitters = emitters.slice();
            return;
        }

        const nextIds = new Set(emitters.map((e) => e.id));

        // Remove voices no longer in the list
        for (const [id, voice] of this._voices) {
            if (!nextIds.has(id)) {
                this._disposeVoice(voice);
                this._voices.delete(id);
            }
        }

        // Add / update voices
        for (const emitter of emitters) {
            const existing = this._voices.get(emitter.id);
            if (existing) {
                this._applyEmitterSettings(existing, emitter);
            } else {
                this._spawnVoice(emitter);
            }
        }
    }

    updateListener(pose: PlayerPose): void {
        if (!this._started || !hasSharedAudioContext()) {
            this._pendingPose = pose;
            return;
        }
        const ctx = getSharedAudioContext();
        const listener = ctx.listener;
        const [px, py, pz] = pose.pos;
        const [fx, fy, fz] = pose.forward;
        const [ux, uy, uz] = pose.up;

        const now = ctx.currentTime;
        if (listener.positionX) {
            listener.positionX.setTargetAtTime(px, now, 0.02);
            listener.positionY.setTargetAtTime(py, now, 0.02);
            listener.positionZ.setTargetAtTime(pz, now, 0.02);
            listener.forwardX.setTargetAtTime(fx, now, 0.02);
            listener.forwardY.setTargetAtTime(fy, now, 0.02);
            listener.forwardZ.setTargetAtTime(fz, now, 0.02);
            listener.upX.setTargetAtTime(ux, now, 0.02);
            listener.upY.setTargetAtTime(uy, now, 0.02);
            listener.upZ.setTargetAtTime(uz, now, 0.02);
        } else {
            // Older browsers
            (listener as any).setPosition?.(px, py, pz);
            (listener as any).setOrientation?.(fx, fy, fz, ux, uy, uz);
        }
    }

    stop(): void {
        for (const voice of this._voices.values()) {
            this._disposeVoice(voice);
        }
        this._voices.clear();
        try { this._masterGain?.disconnect(); } catch { /* noop */ }
        this._masterGain = null;
        this._bufferCache.clear();
        this._started = false;
        this._unlocked = false;
    }

    // ── internal ─────────────────────────────────────────────────────

    private _applyEmitterSettings(voice: Voice, emitter: SoundEmitter): void {
        voice.emitter = emitter;
        const ctx = getSharedAudioContext();
        const now = ctx.currentTime;
        const { panner, gain } = voice;
        const [x, y, z] = emitter.pos;
        if (panner.positionX) {
            panner.positionX.setTargetAtTime(x, now, 0.05);
            panner.positionY.setTargetAtTime(y, now, 0.05);
            panner.positionZ.setTargetAtTime(z, now, 0.05);
        } else {
            (panner as any).setPosition?.(x, y, z);
        }
        panner.refDistance = Math.max(1, emitter.refDistance ?? 200);
        panner.maxDistance = Math.max(panner.refDistance + 1, emitter.radius ?? 2000);
        panner.rolloffFactor = 1.0;
        panner.distanceModel = 'inverse';

        gain.gain.setTargetAtTime(Math.max(0, Math.min(1, emitter.volume ?? 1.0)), now, 0.05);
    }

    private _spawnVoice(emitter: SoundEmitter): void {
        if (!this._masterGain) return;
        const ctx = getSharedAudioContext();
        const panner = ctx.createPanner();
        panner.panningModel = 'HRTF';
        panner.distanceModel = 'inverse';
        panner.refDistance = Math.max(1, emitter.refDistance ?? 200);
        panner.maxDistance = Math.max(panner.refDistance + 1, emitter.radius ?? 2000);
        panner.rolloffFactor = 1.0;
        panner.coneInnerAngle = 360;
        panner.coneOuterAngle = 360;
        const [x, y, z] = emitter.pos;
        if (panner.positionX) {
            panner.positionX.value = x;
            panner.positionY.value = y;
            panner.positionZ.value = z;
        } else {
            (panner as any).setPosition?.(x, y, z);
        }

        const gain = ctx.createGain();
        gain.gain.value = Math.max(0, Math.min(1, emitter.volume ?? 1.0));

        panner.connect(gain);
        gain.connect(this._masterGain);

        const voice: Voice = {
            id: emitter.id,
            emitter,
            source: null,
            gain,
            panner,
            loading: false,
            failed: false,
        };
        this._voices.set(emitter.id, voice);

        if (this._unlocked) this._startVoice(voice);
    }

    private async _startVoice(voice: Voice): Promise<void> {
        if (voice.source || voice.loading || voice.failed) return;
        voice.loading = true;
        const url = resolveSoundUrl(voice.emitter.file);
        if (!url) {
            console.warn(`[ambientSoundEngine] emitter ${voice.id} has empty file; skipping`);
            voice.failed = true;
            voice.loading = false;
            return;
        }
        let buffer: AudioBuffer;
        try {
            buffer = await this._decode(url);
        } catch (err) {
            console.warn(`[ambientSoundEngine] failed to decode ${url} for emitter ${voice.id}:`, err);
            voice.failed = true;
            voice.loading = false;
            return;
        }
        voice.loading = false;

        const ctx = getSharedAudioContext();
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.loop = voice.emitter.loop !== false;
        source.connect(voice.panner);
        const delay = Math.max(0, voice.emitter.startDelaySec ?? 0);
        source.start(ctx.currentTime + delay);
        voice.source = source;
    }

    private _decode(url: string): Promise<AudioBuffer> {
        const cached = this._bufferCache.get(url);
        if (cached) return cached;
        const ctx = getSharedAudioContext();
        const promise = fetch(url)
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
                return r.arrayBuffer();
            })
            .then((buf) => ctx.decodeAudioData(buf));
        this._bufferCache.set(url, promise);
        promise.catch(() => { this._bufferCache.delete(url); });
        return promise;
    }

    private _disposeVoice(voice: Voice): void {
        try { voice.source?.stop(); } catch { /* already stopped */ }
        try { voice.source?.disconnect(); } catch { /* noop */ }
        try { voice.panner.disconnect(); } catch { /* noop */ }
        try { voice.gain.disconnect(); } catch { /* noop */ }
        voice.source = null;
    }
}

let singleton: AmbientSoundEngine | null = null;

export function getAmbientSoundEngine(): AmbientSoundEngine {
    if (!singleton) singleton = new AmbientSoundEngine();
    return singleton;
}
