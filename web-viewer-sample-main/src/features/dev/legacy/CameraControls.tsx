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

import React from 'react';
import './CameraControls.css';

export type CameraType = 'first_person' | 'bird_eye';
export type PhysicsState = 'disabled' | 'enabled';

interface CameraControlsProps {
    currentCamera: CameraType;
    onCameraChange: (cameraType: CameraType) => void;
    currentPhysics: PhysicsState;
    onPhysicsChange: (physicsState: PhysicsState) => void;
    isVisible: boolean;
}

const CameraControls: React.FC<CameraControlsProps> = ({ 
    currentCamera, 
    onCameraChange,
    isVisible 
}) => {
    

    if (!isVisible) {
        return null;
    }

    return (
        <div className="camera-controls">
            <div className="camera-controls-header">
                <h3>Camera View</h3>
            </div>
            <div className="camera-buttons">
                <button
                    className={`camera-button ${currentCamera === 'first_person' ? 'active' : ''}`}
                    onClick={() => onCameraChange('first_person')}
                    title="First Person View"
                >
                    <div className="camera-icon">👤</div>
                    <span>First Person</span>
                </button>
                
                <button
                    className={`camera-button ${currentCamera === 'bird_eye' ? 'active' : ''}`}
                    onClick={() => onCameraChange('bird_eye')}
                    title="Bird's Eye View"
                >
                    <div className="camera-icon">🦅</div>
                    <span>Bird's Eye</span>
                </button>
            </div>
            
            {/* Physics controls removed: physics auto-starts with timeline */}
        </div>
    );
};

export default CameraControls;


