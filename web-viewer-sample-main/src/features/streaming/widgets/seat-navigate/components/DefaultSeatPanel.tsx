import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import './DefaultSeatPanel.css';

interface DefaultSeatPanelProps {
    children: React.ReactNode;
    onClose: () => void;
}

const DefaultSeatPanel: React.FC<DefaultSeatPanelProps> = ({ children, onClose }) => {
    const { t } = useTranslation();
    const [pos, setPos] = useState({ x: 80, y: 180 });
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
        return () => {
            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerup', onUp);
            window.removeEventListener('pointercancel', onUp);
        };
    }, [dragging]);

    const onHeaderPointerDown = (e: React.PointerEvent) => {
        if ((e.target as HTMLElement).closest('button') || (e.target as HTMLElement).closest('input')) return;
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        dragStartRef.current = { mouseX: e.clientX, mouseY: e.clientY, posX: pos.x, posY: pos.y };
        setDragging(true);
    };

    return (
        <div
            className="seat-panel-default"
            style={{ left: pos.x, top: pos.y }}
        >
            <div className="seat-panel-default__card">
                <div
                    role="button"
                    tabIndex={0}
                    onPointerDown={onHeaderPointerDown}
                    className="seat-panel-default__header"
                    style={{ cursor: dragging ? 'grabbing' : 'grab' }}
                    title={t('seat.dragToMove')}
                >
                    <strong>{t('seat.findMySeat')}</strong>
                    <button
                        type="button"
                        onClick={onClose}
                        className="seat-panel-default__close"
                    >
                        {'\u00D7'}
                    </button>
                </div>
                {children}
            </div>
        </div>
    );
};

export default DefaultSeatPanel;
