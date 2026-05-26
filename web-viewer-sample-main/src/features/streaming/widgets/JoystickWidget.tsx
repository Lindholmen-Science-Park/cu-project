/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import './JoystickWidget.css';

/** Normalized movement: forward (-1..1, positive=forward), right (-1..1, positive=right) */
export interface JoystickMovement {
    forward: number;
    right: number;
}

export type JoystickPosition = 'left' | 'right';

interface JoystickWidgetProps {
    isVisible: boolean;
    position?: JoystickPosition;
    onJoystickChange?: (forward: number, right: number) => void;
}

/** Stick displacement in pixels from center */
interface StickPosition {
    x: number;
    y: number;
}

const JOYSTICK_DEADZONE = 0.08; // Ignore small movements near center

/**
 * Virtual joystick widget for mobile/touch-based control.
 * position: 'left' = movement (bottom-left), 'right' = look/camera (bottom-right)
 * Calls onJoystickChange(forward, right) with normalized -1..1 values.
 */
const JoystickWidget: React.FC<JoystickWidgetProps> = ({ isVisible, position = 'left', onJoystickChange }) => {
    const [stickPos, setStickPos] = useState<StickPosition>({ x: 0, y: 0 });
    const [isDragging, setIsDragging] = useState(false);
    const baseRef = useRef<HTMLDivElement>(null);

    const getMaxDisplacement = useCallback(() => {
        const base = baseRef.current;
        if (!base) return 36;
        const rect = base.getBoundingClientRect();
        const baseRadius = rect.width / 2;
        const stickRadius = rect.width * 0.2; // stick is ~40% of base
        return Math.max(10, baseRadius - stickRadius);
    }, []);

    const clampToCircle = useCallback(
        (dx: number, dy: number): StickPosition => {
            const max = getMaxDisplacement();
            const len = Math.sqrt(dx * dx + dy * dy);
            if (len <= max) return { x: dx, y: dy };
            const scale = max / len;
            return { x: dx * scale, y: dy * scale };
        },
        [getMaxDisplacement]
    );

    /** Convert stick position to normalized forward/right (-1..1) */
    const stickPosToMovement = useCallback(
        (pos: StickPosition): { forward: number; right: number } => {
            const max = getMaxDisplacement();
            if (max <= 0) return { forward: 0, right: 0 };
            let forward = -pos.y / max; // stick up (negative y) = forward
            let right = pos.x / max;
            const len = Math.sqrt(forward * forward + right * right);
            if (len <= JOYSTICK_DEADZONE) return { forward: 0, right: 0 };
            // Rescale to remove deadzone
            const scaled = (len - JOYSTICK_DEADZONE) / (1 - JOYSTICK_DEADZONE);
            const factor = scaled / len;
            forward = Math.max(-1, Math.min(1, forward * factor));
            right = Math.max(-1, Math.min(1, right * factor));
            return { forward, right };
        },
        [getMaxDisplacement]
    );

    const notifyMovement = useCallback(
        (pos: StickPosition) => {
            if (!onJoystickChange) return;
            const { forward, right } = stickPosToMovement(pos);
            onJoystickChange(forward, right);
        },
        [onJoystickChange, stickPosToMovement]
    );

    const handlePointerDown = useCallback(
        (e: React.PointerEvent) => {
            e.preventDefault();
            setIsDragging(true);
            const base = baseRef.current;
            if (!base) return;
            const rect = base.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;
            const pos = clampToCircle(e.clientX - centerX, e.clientY - centerY);
            setStickPos(pos);
            notifyMovement(pos);
        },
        [clampToCircle, notifyMovement]
    );

    const handlePointerMove = useCallback(
        (e: PointerEvent) => {
            if (!isDragging) return;
            const base = baseRef.current;
            if (!base) return;
            const rect = base.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;
            const pos = clampToCircle(e.clientX - centerX, e.clientY - centerY);
            setStickPos(pos);
            notifyMovement(pos);
        },
        [isDragging, clampToCircle, notifyMovement]
    );

    const handlePointerUp = useCallback(() => {
        setIsDragging(false);
        setStickPos({ x: 0, y: 0 });
        onJoystickChange?.(0, 0);
    }, [onJoystickChange]);

    useEffect(() => {
        if (!isDragging) return;
        document.addEventListener('pointermove', handlePointerMove);
        document.addEventListener('pointerup', handlePointerUp);
        document.addEventListener('pointercancel', handlePointerUp);
        return () => {
            document.removeEventListener('pointermove', handlePointerMove);
            document.removeEventListener('pointerup', handlePointerUp);
            document.removeEventListener('pointercancel', handlePointerUp);
        };
    }, [isDragging, handlePointerMove, handlePointerUp]);

    if (!isVisible) {
        return null;
    }

    return (
        <div
            className={`joystick-widget joystick-widget--${position}`}
            aria-label={position === 'left' ? 'Virtual joystick for movement' : 'Virtual joystick for look'}
        >
            <div
                ref={baseRef}
                className="joystick-base"
                onPointerDown={handlePointerDown}
                style={{ touchAction: 'none' }}
            >
                <div
                    className={`joystick-stick ${isDragging ? 'dragging' : ''}`}
                    style={{
                        transform: `translate(${stickPos.x}px, ${stickPos.y}px)`,
                    }}
                />
            </div>
        </div>
    );
};

export default JoystickWidget;
