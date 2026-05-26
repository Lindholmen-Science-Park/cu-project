import React, { useState, useEffect, useRef } from 'react';
import type { PoiResult } from '../types';

export interface PoiRoutesWidgetProps {
    title: string;
    results: PoiResult[];
    activeRouteId: string | null;
    movingToId: string | null;
    onClose: () => void;
    onRefresh: () => void;
    onItemClick: (primPath: string, itemKey: string) => void;
    onMoveStart: () => void;
    onMoveStop: () => void;
    onTeleport?: (primPath: string, itemKey: string) => void;
    headerExtra?: React.ReactNode;
    itemIcon?: (result: PoiResult, index: number) => string;
    itemLabel?: (result: PoiResult, index: number) => string;
    emptyText?: string;
    hideUnreachable?: boolean;
}

const defaultItemIcon = (_r: PoiResult, i: number) => (i === 0 ? '\uD83D\uDFE2' : '\uD83D\uDCCD');
const defaultItemLabel = (r: PoiResult, i: number) => {
    const path = typeof r.poiRef === 'string' ? r.poiRef : '';
    return path ? path.replace(/^.*\//, '') : (r.poiId || `Item ${i + 1}`);
};

const PoiRoutesWidget: React.FC<PoiRoutesWidgetProps> = ({
    title, results, activeRouteId, movingToId,
    onClose, onRefresh, onItemClick, onMoveStart, onMoveStop, onTeleport,
    headerExtra, itemIcon = defaultItemIcon, itemLabel = defaultItemLabel,
    emptyText = 'No results yet. Calculating\u2026',
    hideUnreachable = false,
}) => {
    const filteredResults = hideUnreachable ? results.filter((r) => r.success) : results;
    const [pos, setPos] = useState({ x: 80, y: 60 });
    const [dragging, setDragging] = useState(false);
    const [hoveredId, setHoveredId] = useState<string | null>(null);
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
        return () => {
            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerup', onUp);
            window.removeEventListener('pointercancel', onUp);
        };
    }, [dragging]);

    const onHeaderPointerDown = (e: React.PointerEvent) => {
        if ((e.target as HTMLElement).closest('button')) return;
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        dragStartRef.current = { mouseX: e.clientX, mouseY: e.clientY, posX: pos.x, posY: pos.y };
        setDragging(true);
    };

    const fmt = (n: number) => (n < 10 ? n.toFixed(1) : Math.round(n).toString());
    const isMoving = !!movingToId;

    return (
        <div
            style={{
                position: 'absolute',
                left: pos.x,
                top: pos.y,
                zIndex: 1100,
                minWidth: 240,
                maxWidth: 340,
                maxHeight: '70vh',
                overflow: 'auto',
                background: 'rgba(0,0,0,0.75)',
                borderRadius: 10,
                color: '#fff',
                fontSize: 13,
                backdropFilter: 'blur(12px)',
                border: '1px solid rgba(255,255,255,0.2)',
                boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
            }}
        >
            <div
                role="button"
                tabIndex={0}
                onPointerDown={onHeaderPointerDown}
                style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '10px 12px',
                    borderBottom: '1px solid rgba(255,255,255,0.1)',
                    cursor: dragging ? 'grabbing' : 'grab',
                    userSelect: 'none',
                    touchAction: 'none',
                }}
                title="Drag to move"
            >
                <strong>{title}</strong>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); onRefresh(); }}
                        title="Recalculate routes"
                        style={{
                            background: 'none', border: 'none',
                            color: '#cccccc', cursor: 'pointer',
                            fontSize: 16, padding: '2px 4px', lineHeight: 1,
                        }}
                    >
                        {'\u21BB'}
                    </button>
                    <button
                        type="button"
                        onClick={onClose}
                        style={{ background: 'none', border: 'none', color: '#b3b3b3', cursor: 'pointer', fontSize: 18, padding: '0 4px' }}
                    >
                        {'\u00D7'}
                    </button>
                </span>
            </div>

            {headerExtra && (
                <div style={{ padding: '8px 12px 0' }}>
                    {headerExtra}
                </div>
            )}

            <div style={{ padding: '8px 12px 12px' }}>
                {filteredResults.length === 0 ? (
                    <div style={{ color: '#999999' }}>{results.length > 0 && hideUnreachable ? 'No reachable locations found.' : emptyText}</div>
                ) : (
                    <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                        {filteredResults.map((r, i) => {
                            const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
                            const label = itemLabel(r, i);
                            const key = r.poiId || primPath || `poi_${i}`;
                            const isActive = activeRouteId === key;
                            const isHovered = hoveredId === key;
                            return (
                                <li
                                    key={key}
                                    onMouseEnter={() => setHoveredId(key)}
                                    onMouseLeave={() => setHoveredId(null)}
                                    onClick={() => { if (r.success && primPath) onItemClick(primPath, key); }}
                                    style={{
                                        padding: '8px 10px',
                                        margin: '2px 0',
                                        borderRadius: 6,
                                        cursor: r.success ? 'pointer' : 'default',
                                        background: isActive
                                            ? 'rgba(76, 175, 80, 0.25)'
                                            : isHovered ? 'rgba(255,255,255,0.1)' : 'transparent',
                                        border: isActive
                                            ? '1px solid rgba(76, 175, 80, 0.5)'
                                            : '1px solid transparent',
                                        transition: 'background 0.15s, border-color 0.15s',
                                    }}
                                >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <span style={{ fontSize: 15 }}>{itemIcon(r, i)}</span>
                                        <span style={{ fontWeight: isActive ? 600 : 500 }}>{label}</span>
                                        {isActive && <span style={{ fontSize: 10, color: '#43a047', marginLeft: 'auto' }}>ROUTE ACTIVE</span>}
                                    </div>
                                    {r.success ? (
                                        <div style={{ color: '#d9d9d9', marginTop: 3, marginLeft: 21 }}>
                                            {fmt(r.distanceMetersActual ?? r.distanceMetersBase)} m {'\u00B7'} ~{fmt(r.estimatedTimeSecondsActual ?? r.estimatedTimeSecondsBase)} s
                                        </div>
                                    ) : (
                                        <div style={{ color: '#ff8a80', marginTop: 3, marginLeft: 21 }}>{r.error || 'Path failed'}</div>
                                    )}
                                </li>
                            );
                        })}
                    </ul>
                )}

                {activeRouteId && (
                    <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                if (isMoving) onMoveStop();
                                else onMoveStart();
                            }}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: 6,
                                flex: 1,
                                padding: '8px 12px',
                                borderRadius: 8,
                                border: 'none',
                                cursor: 'pointer',
                                fontSize: 13,
                                fontWeight: 600,
                                color: '#fff',
                                background: isMoving
                                    ? 'rgba(244, 67, 54, 0.7)'
                                    : 'rgba(76, 175, 80, 0.7)',
                                transition: 'background 0.2s',
                            }}
                        >
                            <span>{isMoving ? '\u23F9' : '\uD83D\uDEB6'}</span>
                            <span>{isMoving ? 'Stop moving' : `Move to ${activeRouteId.replace(/^.*\//, '')}`}</span>
                        </button>
                        {onTeleport && (() => {
                            const activeResult = filteredResults.find((r) => (r.poiId || r.poiRef) === activeRouteId);
                            const primPath = activeResult ? (typeof activeResult.poiRef === 'string' ? activeResult.poiRef : '') : '';
                            if (!primPath) return null;
                            return (
                                <button
                                    onClick={(e) => { e.stopPropagation(); onTeleport(primPath, activeRouteId); }}
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        gap: 6,
                                        flex: 1,
                                        padding: '8px 12px',
                                        borderRadius: 8,
                                        border: 'none',
                                        cursor: 'pointer',
                                        fontSize: 13,
                                        fontWeight: 600,
                                        color: '#fff',
                                        background: 'rgba(156, 39, 176, 0.7)',
                                        transition: 'background 0.2s',
                                    }}
                                    title="Teleport directly to this location"
                                >
                                    <span>{'\u26A1'}</span>
                                    <span>Take Me There</span>
                                </button>
                            );
                        })()}
                    </div>
                )}
            </div>
        </div>
    );
};

export default PoiRoutesWidget;
