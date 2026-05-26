import React, { useState, useEffect, useRef } from 'react';
import { useEnvironment, useAppUI } from '../contexts';

const AREAS = [
    { area: 'cctv1_navmesh_area', label: 'CCTV1 Area Traffic' },
    { area: 'camera_vip_entrance_area', label: 'VIP Entrance' },
    { area: 'camera_main_entrance_exit_area', label: 'Main Exit' },
    { area: 'camera_main_entrance_entry_area', label: 'Main Entry' },
] as const;

const CameraPathfindingWidget: React.FC = () => {
    const env = useEnvironment();
    const appUI = useAppUI();
    const {
        cameraPathfindingWidgetOpen,
        setCameraPathfindingWidgetOpen,
        cctv1TrafficValue,
        handleCctv1TrafficChange: onCctv1TrafficChange,
        cameraCosts,
        handleCameraCostChange: onCameraCostChange,
        cameraDataCalcActive,
        cameraDataCalcBaking,
        handleCameraDataCalcToggle: onCameraDataCalcToggle,
    } = env;

    const [pos, setPos] = useState({ x: 320, y: 60 });
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
    if (!cameraPathfindingWidgetOpen) return null;

    const onClose = () => setCameraPathfindingWidgetOpen(false);

    const onHeaderPointerDown = (e: React.PointerEvent) => {
        if ((e.target as HTMLElement).closest('button') || (e.target as HTMLElement).closest('input')) return;
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        dragStartRef.current = { mouseX: e.clientX, mouseY: e.clientY, posX: pos.x, posY: pos.y };
        setDragging(true);
    };

    return (
        <div style={{ position: 'absolute', left: pos.x, top: pos.y, zIndex: 1100, minWidth: 260, maxWidth: 320, background: 'rgba(0,0,0,0.75)', borderRadius: 10, color: '#fff', fontSize: 13, backdropFilter: 'blur(12px)', border: '1px solid rgba(255,255,255,0.2)', boxShadow: '0 4px 20px rgba(0,0,0,0.4)' }}>
            <div role="button" tabIndex={0} onPointerDown={onHeaderPointerDown} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.1)', cursor: dragging ? 'grabbing' : 'grab', userSelect: 'none', touchAction: 'none' }} title="Drag to move">
                <strong>Pathfinding costs</strong>
                <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: 18, padding: '0 4px' }}>{'\u00D7'}</button>
            </div>
            <div style={{ padding: '12px' }}>
                {AREAS.map(({ area, label }) => {
                    const value = area === 'cctv1_navmesh_area' ? cctv1TrafficValue : (cameraCosts[area] ?? 1.0);
                    const onChange = area === 'cctv1_navmesh_area' ? onCctv1TrafficChange : (v: number) => onCameraCostChange(area, v);
                    return (
                        <div key={area} style={{ marginBottom: 10 }}>
                            <div style={{ fontSize: '0.75rem', marginBottom: 4, color: 'rgba(255,255,255,0.85)' }}>{label}</div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <input type="range" min={1} max={15} step={0.5} value={value} onChange={(e) => onChange(parseFloat(e.target.value))} style={{ flex: 1 }} />
                                <span style={{ minWidth: 28, fontSize: '0.8rem' }}>{value.toFixed(1)}</span>
                                <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.6)' }}>{value <= 2 ? 'Light' : value <= 7 ? 'Medium' : 'Heavy'}</span>
                            </div>
                        </div>
                    );
                })}
                {cameraDataCalcBaking && <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.7)', marginTop: 4 }}>Rebaking NavMesh\u2026</div>}
                <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                    <button type="button" disabled={cameraDataCalcBaking} onClick={onCameraDataCalcToggle} style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.3)', background: cameraDataCalcActive ? 'rgba(76,175,80,0.3)' : 'rgba(255,255,255,0.1)', color: '#fff', cursor: cameraDataCalcBaking ? 'not-allowed' : 'pointer', fontSize: 12 }}>
                        {cameraDataCalcActive ? 'Pathfinding ON' : 'Pathfinding OFF'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default CameraPathfindingWidget;
