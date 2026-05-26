import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

export type SmoothedOverlayOptions = {
  /**
   * Higher = follows the projected target more tightly (less “floaty”).
   * Frame-rate independent via exponential decay (~12–18 is a good range).
   */
  smoothing?: number;
  /**
   * If the target jumps farther than this (px), snap immediately — avoids
   * sliding across the screen after a real teleport or visibility flip.
   */
  snapDistance?: number;
  /** Snap to the target when this close (px). */
  epsilon?: number;
  /** When false, pass through the raw target (no smoothing loop). */
  enabled?: boolean;
};

const DEFAULTS = {
  smoothing: 14,
  snapDistance: 120,
  epsilon: 0.45,
  enabled: true,
} as const;

const MAX_DT_SEC = 1 / 15;

/**
 * Smooths 2D overlay coordinates that are updated every frame from a remote
 * projector (Kit viewport → video content-rect). Reduces perceived jitter when
 * the stream cadence and the browser compositor are slightly out of phase.
 *
 * When the smoothed position has caught the target, the rAF loop stops until
 * the target moves again — same motion quality, less idle CPU.
 */
export function useSmoothedOverlayPosition(
  targetX: number,
  targetY: number,
  options: SmoothedOverlayOptions = {},
): { x: number; y: number } {
  const { smoothing, snapDistance, epsilon, enabled } = { ...DEFAULTS, ...options };

  const targetRef = useRef({ x: targetX, y: targetY });
  targetRef.current = { x: targetX, y: targetY };

  const optsRef = useRef({ smoothing, snapDistance, epsilon });
  optsRef.current = { smoothing, snapDistance, epsilon };

  const lastRef = useRef({ x: targetX, y: targetY });
  const rafRef = useRef(0);
  const lastFrameTimeRef = useRef(performance.now());

  const [pos, setPos] = useState(() => ({ x: targetX, y: targetY }));

  const stopRaf = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      stopRaf();
      lastRef.current = { x: targetX, y: targetY };
      setPos({ x: targetX, y: targetY });
    }
  }, [enabled, targetX, targetY, stopRaf]);

  const runFrame = useCallback(() => {
    const now = performance.now();
    const dt = Math.min(MAX_DT_SEC, (now - lastFrameTimeRef.current) / 1000);
    lastFrameTimeRef.current = now;

    const t = targetRef.current;
    const { smoothing: sm, snapDistance: snap, epsilon: eps } = optsRef.current;
    const p = lastRef.current;
    const dx = t.x - p.x;
    const dy = t.y - p.y;
    const dist = Math.hypot(dx, dy);

    if (!Number.isFinite(dist) || dist === 0) {
      stopRaf();
      return;
    }
    if (dist > snap) {
      lastRef.current = { x: t.x, y: t.y };
      setPos(lastRef.current);
      stopRaf();
      return;
    }
    if (dist <= eps) {
      lastRef.current = { x: t.x, y: t.y };
      setPos(lastRef.current);
      stopRaf();
      return;
    }
    const k = 1 - Math.exp(-sm * dt);
    const next = { x: p.x + dx * k, y: p.y + dy * k };
    lastRef.current = next;
    setPos(next);
    rafRef.current = requestAnimationFrame(runFrame);
  }, [stopRaf]);

  useLayoutEffect(() => {
    if (!enabled) return;
    if (rafRef.current !== 0) return;

    const t = targetRef.current;
    const p = lastRef.current;
    const { epsilon: eps } = optsRef.current;
    if (Math.hypot(t.x - p.x, t.y - p.y) <= eps) return;

    lastFrameTimeRef.current = performance.now();
    rafRef.current = requestAnimationFrame(runFrame);
  }, [enabled, targetX, targetY, runFrame]);

  useEffect(() => () => stopRaf(), [stopRaf]);

  if (!enabled) return { x: targetX, y: targetY };
  return pos;
}
