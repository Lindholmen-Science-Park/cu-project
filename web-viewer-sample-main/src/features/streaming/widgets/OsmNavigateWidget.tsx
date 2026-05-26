import React, { useState, useEffect, useRef } from 'react';
import { useNavigation, useAppUI } from '../contexts';

const POIS = [
    { id: 'skandinavium', label: 'Skandinavium' },
    { id: 'gothia_towers', label: 'Gothia Towers' },
    { id: 'museum_of_art', label: 'Museum of Art' },
    { id: 'poseidon_statue', label: 'Poseidon Statue' },
];

function formatDistance(m: number): string {
    return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
}

function formatTime(s: number): string {
    if (s < 60) return `${Math.round(s)} sec`;
    const mins = Math.floor(s / 60);
    const secs = Math.round(s % 60);
    return secs > 0 ? `${mins} min ${secs} sec` : `${mins} min`;
}

type OsmMode = 'walking' | 'wheelchair' | 'car';

// Display labels (Figma). Keep in lockstep with the internal values on
// the Kit side — "walking" / "wheelchair" / "car".
const MODE_OPTIONS: Array<{ value: OsmMode; label: string }> = [
    { value: 'walking', label: 'By foot' },
    { value: 'wheelchair', label: 'Wheelchair' },
    { value: 'car', label: 'Car' },
];

const OsmNavigateWidget: React.FC = () => {
    const nav = useNavigation();
    const appUI = useAppUI();
    const {
        osmSelectedPoiId: selectedPoiId,
        osmRouteInfo: routeInfo,
        osmMapVisible: mapVisible,
        osmSelectedMode: selectedMode,
        handleOsmPoiSelect: onPoiSelect,
        handleOsmModeSelect: onModeSelect,
        handleOsmClear: onClear,
        handleOsmNavigateClose: onClose,
        handleOsmToggleMap: onToggleMap,
    } = nav;

    const [pos, setPos] = useState({ x: -1, y: 80 });
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
    if (!nav.osmNavigateOpen) return null;

    const onHeaderPointerDown = (e: React.PointerEvent) => {
        if ((e.target as HTMLElement).closest('button') || (e.target as HTMLElement).closest('select')) return;
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        dragStartRef.current = { mouseX: e.clientX, mouseY: e.clientY, posX: pos.x, posY: pos.y };
        setDragging(true);
    };

    const posStyle = pos.x < 0
        ? { top: pos.y, right: 16 }
        : { top: pos.y, left: pos.x };

    return (
        <div style={{
            position: 'absolute',
            ...posStyle,
            width: 280,
            background: 'rgba(30, 30, 38, 0.92)',
            borderRadius: 10,
            padding: 16,
            color: '#e8e8e8',
            fontFamily: 'system-ui, sans-serif',
            fontSize: 14,
            boxShadow: '0 4px 24px rgba(0,0,0,0.4)',
            zIndex: 1100,
        }}>
            {/* Header */}
            <div role="button" tabIndex={0} onPointerDown={onHeaderPointerDown} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, cursor: dragging ? 'grabbing' : 'grab', userSelect: 'none', touchAction: 'none' }} title="Drag to move">
                <span style={{ fontWeight: 600, fontSize: 15 }}>City Navigate</span>
                <button
                    onClick={onClose}
                    style={{
                        background: 'none', border: 'none', color: '#aaa', cursor: 'pointer',
                        fontSize: 18, padding: '0 4px', lineHeight: 1,
                    }}
                >
                    X
                </button>
            </div>

            {/* Movement mode toggle (dev-only; production uses the CU accessibility mode) */}
            <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, color: '#999', display: 'block', marginBottom: 4 }}>Movement</label>
                <div
                    role="group"
                    aria-label="Movement mode"
                    style={{
                        display: 'flex',
                        borderRadius: 6,
                        overflow: 'hidden',
                        border: '1px solid #444',
                    }}
                >
                    {MODE_OPTIONS.map((opt) => {
                        const active = selectedMode === opt.value;
                        return (
                            <button
                                key={opt.value}
                                onClick={() => onModeSelect(opt.value)}
                                style={{
                                    flex: 1,
                                    padding: '6px 8px',
                                    background: active ? 'rgba(100, 200, 255, 0.22)' : '#2a2a36',
                                    color: active ? '#76c8ff' : '#ccc',
                                    border: 'none',
                                    borderRight: '1px solid #444',
                                    cursor: 'pointer',
                                    fontSize: 12,
                                    fontWeight: active ? 600 : 400,
                                }}
                            >
                                {opt.label}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* POI selector */}
            <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, color: '#999', display: 'block', marginBottom: 4 }}>Destination</label>
                <select
                    value={selectedPoiId || ''}
                    onChange={(e) => onPoiSelect(e.target.value)}
                    style={{
                        width: '100%', padding: '6px 8px', borderRadius: 6,
                        background: '#2a2a36', color: '#e8e8e8', border: '1px solid #444',
                        fontSize: 13, cursor: 'pointer',
                    }}
                >
                    <option value="" disabled>Select a destination...</option>
                    {POIS.map((poi) => (
                        <option key={poi.id} value={poi.id}>{poi.label}</option>
                    ))}
                </select>
            </div>

            {/* Instruction */}
            {selectedPoiId && !routeInfo && (
                <div style={{ padding: '8px 0', color: '#76c8ff', fontSize: 13 }}>
                    Click on the map to calculate route
                </div>
            )}

            {/* Route result */}
            {routeInfo && (
                <div style={{
                    background: 'rgba(0, 200, 200, 0.12)',
                    border: '1px solid rgba(0, 200, 200, 0.3)',
                    borderRadius: 8,
                    padding: 12,
                    marginBottom: 12,
                }}>
                    <div style={{ fontSize: 13, color: '#aaa', marginBottom: 4 }}>Route to {POIS.find(p => p.id === routeInfo.poiId)?.label}</div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: '#00e8e8' }}>
                        {formatDistance(routeInfo.distanceMeters)}
                    </div>
                    <div style={{ fontSize: 13, color: '#ccc', marginTop: 2 }}>
                        ~{formatTime(routeInfo.estimatedTimeSeconds)} walk
                    </div>
                </div>
            )}

            {/* Clear button */}
            {(routeInfo || selectedPoiId) && (
                <button
                    onClick={onClear}
                    style={{
                        width: '100%', padding: '8px 0', borderRadius: 6,
                        background: 'rgba(255, 100, 100, 0.15)', color: '#ff8888',
                        border: '1px solid rgba(255, 100, 100, 0.3)',
                        cursor: 'pointer', fontSize: 13,
                        marginBottom: 8,
                    }}
                >
                    Clear Route
                </button>
            )}

            {/* Show/hide road network toggle */}
            <button
                onClick={onToggleMap}
                style={{
                    width: '100%', padding: '8px 0', borderRadius: 6,
                    background: mapVisible ? 'rgba(100, 200, 255, 0.18)' : 'rgba(255, 255, 255, 0.06)',
                    color: mapVisible ? '#76c8ff' : '#888',
                    border: `1px solid ${mapVisible ? 'rgba(100, 200, 255, 0.35)' : 'rgba(255, 255, 255, 0.12)'}`,
                    cursor: 'pointer', fontSize: 13,
                }}
            >
                {mapVisible ? 'Hide road map' : 'Show road map'}
            </button>
        </div>
    );
};

export default OsmNavigateWidget;
