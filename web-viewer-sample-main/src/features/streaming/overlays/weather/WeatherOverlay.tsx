import React, { useRef, useEffect, useCallback } from 'react';
import { useEnvironment } from '../../contexts';
import './WeatherOverlay.css';

/* ── rain constants ─────────────────────────────────────────────── */
const RAIN_COUNT = 320;
const RAIN_MIN_SPEED = 900;
const RAIN_MAX_SPEED = 1600;
const RAIN_MIN_LEN = 18;
const RAIN_MAX_LEN = 36;
const RAIN_WIND_ANGLE = 0.08;   // radians — slight tilt
const RAIN_COLOR = 'rgba(180, 210, 240, 0.45)';
const RAIN_LINE_WIDTH = 1.5;

/* ── snow constants ─────────────────────────────────────────────── */
const SNOW_COUNT = 160;
const SNOW_MIN_SPEED = 40;
const SNOW_MAX_SPEED = 100;
const SNOW_MIN_R = 2;
const SNOW_MAX_R = 5;
const SNOW_DRIFT_STRENGTH = 30;
const SNOW_DRIFT_FREQ = 0.6;

interface Particle {
    x: number;
    y: number;
    speed: number;
    size: number;    // length for rain, radius for snow
    opacity: number;
    phase: number;   // snow drift phase offset
}

function rand(lo: number, hi: number) {
    return lo + Math.random() * (hi - lo);
}

function spawnRain(w: number, h: number): Particle {
    return {
        x: Math.random() * w * 1.2 - w * 0.1,
        y: -rand(0, h),
        speed: rand(RAIN_MIN_SPEED, RAIN_MAX_SPEED),
        size: rand(RAIN_MIN_LEN, RAIN_MAX_LEN),
        opacity: rand(0.25, 0.55),
        phase: 0,
    };
}

function spawnSnow(w: number, h: number): Particle {
    return {
        x: Math.random() * w,
        y: -rand(0, h),
        speed: rand(SNOW_MIN_SPEED, SNOW_MAX_SPEED),
        size: rand(SNOW_MIN_R, SNOW_MAX_R),
        opacity: rand(0.4, 0.9),
        phase: Math.random() * Math.PI * 2,
    };
}

const WeatherOverlay: React.FC = () => {
    const { weather, currentCamera } = useEnvironment();
    const active = currentCamera === 'bird_eye' && (weather === 'rain' || weather === 'snow');
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const particlesRef = useRef<Particle[]>([]);
    const rafRef = useRef<number>(0);
    const prevTimeRef = useRef<number>(0);

    const initParticles = useCallback((w: number, h: number, mode: 'rain' | 'snow') => {
        const count = mode === 'rain' ? RAIN_COUNT : SNOW_COUNT;
        const spawner = mode === 'rain' ? spawnRain : spawnSnow;
        particlesRef.current = Array.from({ length: count }, () => spawner(w, h));
    }, []);

    useEffect(() => {
        if (!active) {
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
            rafRef.current = 0;
            particlesRef.current = [];
            return;
        }

        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const resize = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            initParticles(canvas.width, canvas.height, weather as 'rain' | 'snow');
        };
        resize();
        window.addEventListener('resize', resize);

        const mode = weather as 'rain' | 'snow';
        prevTimeRef.current = performance.now();

        const frame = (now: number) => {
            const dt = Math.min((now - prevTimeRef.current) / 1000, 0.1);
            prevTimeRef.current = now;

            const w = canvas.width;
            const h = canvas.height;
            ctx.clearRect(0, 0, w, h);

            const particles = particlesRef.current;

            if (mode === 'rain') {
                ctx.strokeStyle = RAIN_COLOR;
                ctx.lineWidth = RAIN_LINE_WIDTH;
                ctx.lineCap = 'round';

                for (const p of particles) {
                    p.y += p.speed * dt;
                    p.x += Math.sin(RAIN_WIND_ANGLE) * p.speed * dt;

                    if (p.y > h + p.size) {
                        Object.assign(p, spawnRain(w, h));
                        p.y = -p.size;
                    }

                    ctx.globalAlpha = p.opacity;
                    ctx.beginPath();
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(
                        p.x + Math.sin(RAIN_WIND_ANGLE) * p.size,
                        p.y + Math.cos(RAIN_WIND_ANGLE) * p.size,
                    );
                    ctx.stroke();
                }
            } else {
                ctx.fillStyle = '#fff';

                for (const p of particles) {
                    p.y += p.speed * dt;
                    p.x += Math.sin(p.phase + now * 0.001 * SNOW_DRIFT_FREQ) * SNOW_DRIFT_STRENGTH * dt;

                    if (p.y > h + p.size) {
                        Object.assign(p, spawnSnow(w, h));
                        p.y = -p.size;
                    }
                    if (p.x < -p.size) p.x = w + p.size;
                    if (p.x > w + p.size) p.x = -p.size;

                    ctx.globalAlpha = p.opacity;
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                    ctx.fill();
                }
            }

            ctx.globalAlpha = 1;
            rafRef.current = requestAnimationFrame(frame);
        };

        rafRef.current = requestAnimationFrame(frame);

        return () => {
            window.removeEventListener('resize', resize);
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
            rafRef.current = 0;
        };
    }, [active, weather, initParticles]);

    if (!active) return null;

    return <canvas ref={canvasRef} className="weather-overlay" />;
};

export default WeatherOverlay;
