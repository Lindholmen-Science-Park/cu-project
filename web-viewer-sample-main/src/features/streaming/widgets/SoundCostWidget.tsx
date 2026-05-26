import React, { useState, useEffect, useRef } from 'react';
import { useEnvironment, useAppUI } from '../contexts';

const AREAS = [
    { area: 'sound_location_01_area', label: 'Sound Location 1' },
    { area: 'sound_location_02_area', label: 'Sound Location 2' },
    { area: 'sound_location_03_area', label: 'Sound Location 3' },
    { area: 'sound_location_04_area', label: 'Sound Location 4' },
] as const;

const SoundCostWidget: React.FC = () => {
    const env = useEnvironment();
    const appUI = useAppUI();
    const {
        soundCostWidgetOpen,
        soundAreasVisible,
        setSoundCostWidgetOpen,
        soundCosts,
        handleSoundCostChange: onSoundCostChange,
        soundDataCalcActive,
        soundDataCalcBaking,
        handleSoundDataCalcToggle: onSoundDataCalcToggle,
    } = env;

    const [pos, setPos] = useState({ x: 320, y: 320 });
    const [dragging, setDragging] = useState(false);
    const dragStartRef = useRef({ mouseX: 0, mouseY: 0, posX: 0, posY: 0 });

    useEffect(() => {
        if (!dragging) return;
        const onMove = (e: PointerEvent) => {
            const { mouseX, mouseY, posX, posY } = dragStartRef.current;
            setPos({ x: posX + (e.clientX - mouseX), y: posY + (e.clientY - mouseY) });
        };
        const onUp = () => setDragging(false);
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
        window.addEventListener('pointercancel', onUp);
        return () => { window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp); window.removeEventListener('pointercancel', onUp); };
    }, [dragging]);

    if (appUI.seatArrivalCelebrationVisible || appUI.poiArrivalVisible) return null;
    if (!soundCostWidgetOpen || (!soundAreasVisible && !soundDataCalcActive)) return null;

    const onClose = () => setSoundCostWidgetOpen(false);

    const onHeaderPointerDown = (e: React.PointerEvent) => {
        if ((e.target as HTMLElement).closest('button') || (e.target as HTMLElement).closest('input')) return;
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        dragStartRef.current = { mouseX: e.clientX, mouseY: e.clientY, posX: pos.x, posY: pos.y };
        setDragging(true);
    };

    return (
        <div style={{ position: 'absolute', left: pos.x, top: pos.y, zIndex: 1100, minWidth: 260, maxWidth: 320, background: 'rgba(0,0,0,0.75)', borderRadius: 10, color: '#fff', fontSize: 13, backdropFilter: 'blur(12px)', border: '1px solid rgba(255,255,255,0.2)', boxShadow: '0 4px 20px rgba(0,0,0,0.4)' }}>
            <div role="button" tabIndex={0} onPointerDown={onHeaderPointerDown} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.1)', cursor: dragging ? 'grabbing' : 'grab', userSelect: 'none', touchAction: 'none' }} title="Drag to move">
                <strong>Sound pathfinding costs</strong>
                <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: 18, padding: '0 4px' }}>{'\u00D7'}</button>
            </div>
            <div style={{ padding: '12px' }}>
                {AREAS.map(({ area, label }) => {
                    const value = soundCosts[area] ?? 1.0;
                    return (
                        <div key={area} style={{ marginBottom: 10 }}>
                            <div style={{ fontSize: '0.75rem', marginBottom: 4, color: 'rgba(255,255,255,0.85)' }}>{label}</div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <input type="range" min={1} max={15} step={0.5} value={value} onChange={(e) => onSoundCostChange(area, parseFloat(e.target.value))} style={{ flex: 1 }} />
                                <span style={{ minWidth: 28, fontSize: '0.8rem' }}>{value.toFixed(1)}</span>
                                <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.6)' }}>{value <= 2 ? 'Light' : value <= 7 ? 'Medium' : 'Heavy'}</span>
                            </div>
                        </div>
                    );
                })}
                {soundDataCalcBaking && <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.7)', marginTop: 4 }}>Rebaking NavMesh\u2026</div>}
                <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                    <button type="button" disabled={soundDataCalcBaking} onClick={onSoundDataCalcToggle} style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.3)', background: soundDataCalcActive ? 'rgba(76,175,80,0.3)' : 'rgba(255,255,255,0.1)', color: '#fff', cursor: soundDataCalcBaking ? 'not-allowed' : 'pointer', fontSize: 12 }}>
                        {soundDataCalcActive ? 'Pathfinding ON' : 'Pathfinding OFF'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default SoundCostWidget;
