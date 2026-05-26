import { useCallback, useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { findActiveCue, parseVtt, type VttCue } from '../spatialSound/parseVtt';

/**
 * useVideoSphere
 *
 * Browser-side 360° equirectangular video player. Mounts a Three.js scene
 * (sphere with inverted normals, video texture) into a host `<div>` and
 * exposes a small player API: `mount`, `play`, `pause`, `seek`, plus live
 * `currentTime` / `duration` / `isPlaying` state. Rotation is applied via
 * `setRotation(yawDeg, pitchDeg)` — the overlay drives this from drag and
 * device-orientation events. The Kit camera is **never** touched.
 *
 * Why a sphere with `scale.x = -1`? The standard trick to render an
 * equirectangular projection from the inside without flipping UVs.
 *
 * Captions: when a `vttSource` is provided we parse it once and expose
 * `activeCueText` updated each animation frame from the video's
 * `currentTime`. This mirrors `useAmbisonicPlayer`'s caption flow so the
 * overlay shares the same UI affordance.
 *
 * ## Mount ordering — important
 *
 * The caller MUST gate the host `<div>` on `isReady` (i.e. only render
 * the div after `load()` resolves). `THREE.VideoTexture` registers a
 * `requestVideoFrameCallback` on its source video at construction time;
 * if that video has no `src` yet, the callback chain never starts and the
 * texture stays at its initial (black) state forever — even after the
 * source is set later and frames begin flowing. Constructing the texture
 * against a video that already has metadata avoids the race entirely;
 * everything else (including the renderer, scene, mesh) can come and go
 * per mount.
 */
export function useVideoSphere() {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const cuesRef = useRef<VttCue[]>([]);

    const containerRef = useRef<HTMLDivElement | null>(null);
    const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
    const sceneRef = useRef<THREE.Scene | null>(null);
    const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
    const meshRef = useRef<THREE.Mesh | null>(null);
    const textureRef = useRef<THREE.VideoTexture | null>(null);
    const rafRef = useRef<number | null>(null);
    const resizeObserverRef = useRef<ResizeObserver | null>(null);

    const yawRef = useRef(0);
    const pitchRef = useRef(0);

    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [hasCaptions, setHasCaptions] = useState(false);
    const [activeCueText, setActiveCueText] = useState<string>('');
    /**
     * `true` once `load()` has resolved (metadata available) for the
     * current source. The overlay reads this to decide when to render the
     * sphere host div — see the comment block at the top of this file.
     */
    const [isReady, setIsReady] = useState(false);

    // Lazily create the hidden <video> on first access. Kept across re-renders
    // so `play()/pause()` retain state during phase transitions.
    const ensureVideo = useCallback((): HTMLVideoElement => {
        if (videoRef.current) return videoRef.current;
        const v = document.createElement('video');
        v.crossOrigin = 'anonymous';
        v.playsInline = true;
        v.preload = 'auto';
        v.muted = false;
        v.loop = false;
        videoRef.current = v;
        return v;
    }, []);

    const load = useCallback(async (src: string, captionsUrl?: string) => {
        setIsReady(false);
        const v = ensureVideo();
        if (v.src !== src) {
            v.src = src;
            v.load();
        }
        await new Promise<void>((resolve) => {
            if (v.readyState >= 1) { resolve(); return; }
            const onMeta = () => { v.removeEventListener('loadedmetadata', onMeta); resolve(); };
            v.addEventListener('loadedmetadata', onMeta);
        });
        setDuration(Number.isFinite(v.duration) ? v.duration : 0);

        cuesRef.current = [];
        setHasCaptions(false);
        setActiveCueText('');
        if (captionsUrl) {
            try {
                const res = await fetch(captionsUrl);
                if (res.ok) {
                    const txt = await res.text();
                    const cues = parseVtt(txt);
                    cuesRef.current = cues;
                    setHasCaptions(cues.length > 0);
                }
            } catch {
                // Swallow caption fetch errors — the player keeps working.
            }
        }
        setIsReady(true);
    }, [ensureVideo]);

    const play = useCallback(async () => {
        const v = ensureVideo();
        try {
            await v.play();
            setIsPlaying(!v.paused);
        } catch (err) {
            console.warn('[useVideoSphere] play() rejected:', err);
        }
    }, [ensureVideo]);

    const pause = useCallback(() => {
        const v = videoRef.current;
        if (!v) return;
        v.pause();
        setIsPlaying(false);
    }, []);

    const seek = useCallback((t: number) => {
        const v = videoRef.current;
        if (!v || !Number.isFinite(t)) return;
        v.currentTime = Math.max(0, Math.min(t, v.duration || t));
    }, []);

    /**
     * Mirror the volume preference (`VideoBookSettingsContext.muted`) onto the hidden
     * `<video>` element. Safe to call before `mount()` / `load()` — the next
     * `ensureVideo()` call uses whatever was last written.
     */
    const setMuted = useCallback((next: boolean) => {
        const v = ensureVideo();
        v.muted = next;
    }, [ensureVideo]);

    /**
     * Apply a `playbackRate` to the hidden `<video>` element. Also updates
     * `defaultPlaybackRate` so the user's preference survives any browser-side reset
     * (e.g. media-session interruptions on mobile).
     */
    const setPlaybackRate = useCallback((rate: number) => {
        if (!Number.isFinite(rate) || rate <= 0) return;
        const v = ensureVideo();
        v.playbackRate = rate;
        v.defaultPlaybackRate = rate;
    }, [ensureVideo]);

    const setRotation = useCallback((yawDeg: number, pitchDeg: number) => {
        yawRef.current = yawDeg;
        pitchRef.current = Math.max(-89, Math.min(89, pitchDeg));
    }, []);

    const addRotation = useCallback((dYawDeg: number, dPitchDeg: number) => {
        yawRef.current += dYawDeg;
        pitchRef.current = Math.max(-89, Math.min(89, pitchRef.current + dPitchDeg));
    }, []);

    // Mount the Three.js scene into the host div. Caller MUST only render
    // the host once `isReady` is true so the VideoTexture binds against a
    // video that already has metadata + frames (see file header comment).
    const mount = useCallback((container: HTMLDivElement) => {
        if (containerRef.current === container && rendererRef.current) return;
        containerRef.current = container;

        const v = ensureVideo();

        const width = container.clientWidth || 1;
        const height = container.clientHeight || 1;

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1100);
        camera.position.set(0, 0, 0);

        const geometry = new THREE.SphereGeometry(500, 60, 40);
        // Inverted sphere: render the inside surface so the equirect
        // texture wraps around the camera correctly.
        geometry.scale(-1, 1, 1);

        const texture = new THREE.VideoTexture(v);
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.minFilter = THREE.LinearFilter;
        texture.magFilter = THREE.LinearFilter;
        const material = new THREE.MeshBasicMaterial({ map: texture });
        const mesh = new THREE.Mesh(geometry, material);
        scene.add(mesh);

        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
        renderer.setPixelRatio(window.devicePixelRatio || 1);
        renderer.setSize(width, height, false);
        renderer.domElement.style.width = '100%';
        renderer.domElement.style.height = '100%';
        renderer.domElement.style.display = 'block';
        renderer.domElement.style.touchAction = 'none';
        container.appendChild(renderer.domElement);

        rendererRef.current = renderer;
        sceneRef.current = scene;
        cameraRef.current = camera;
        meshRef.current = mesh;
        textureRef.current = texture;

        const handleResize = () => {
            const w = container.clientWidth || 1;
            const h = container.clientHeight || 1;
            renderer.setSize(w, h, false);
            camera.aspect = w / h;
            camera.updateProjectionMatrix();
        };
        const ro = new ResizeObserver(handleResize);
        ro.observe(container);
        resizeObserverRef.current = ro;

        // Render + state pump loop
        const tick = () => {
            const yawRad = THREE.MathUtils.degToRad(yawRef.current);
            const pitchRad = THREE.MathUtils.degToRad(pitchRef.current);
            // Spherical → cartesian look target. Yaw rotates around Y, pitch around X.
            const cosP = Math.cos(pitchRad);
            const target = new THREE.Vector3(
                Math.sin(yawRad) * cosP,
                Math.sin(pitchRad),
                -Math.cos(yawRad) * cosP,
            );
            camera.lookAt(target);

            renderer.render(scene, camera);

            if (videoRef.current) {
                const t = videoRef.current.currentTime;
                setCurrentTime(t);
                if (cuesRef.current.length > 0) {
                    const cue = findActiveCue(cuesRef.current, t);
                    setActiveCueText(cue ? cue.text : '');
                }
            }

            rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
    }, [ensureVideo]);

    // Final teardown — fired on overlay unmount. Everything (including the
    // <video> element) is destroyed; reopen reloads from scratch but the
    // browser HTTP cache covers the cost on warm reloads.
    useEffect(() => () => {
        if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
        resizeObserverRef.current?.disconnect();
        resizeObserverRef.current = null;
        const renderer = rendererRef.current;
        if (renderer) {
            renderer.dispose();
            renderer.domElement.parentElement?.removeChild(renderer.domElement);
        }
        meshRef.current?.geometry.dispose();
        const mat = meshRef.current?.material as THREE.Material | undefined;
        mat?.dispose();
        textureRef.current?.dispose();
        const v = videoRef.current;
        if (v) {
            v.pause();
            v.removeAttribute('src');
            v.load();
        }
        rendererRef.current = null;
        sceneRef.current = null;
        cameraRef.current = null;
        meshRef.current = null;
        textureRef.current = null;
        videoRef.current = null;
        containerRef.current = null;
    }, []);

    return {
        mount,
        load,
        play,
        pause,
        seek,
        setMuted,
        setPlaybackRate,
        setRotation,
        addRotation,
        isPlaying,
        isReady,
        currentTime,
        duration,
        hasCaptions,
        activeCueText,
    };
}
