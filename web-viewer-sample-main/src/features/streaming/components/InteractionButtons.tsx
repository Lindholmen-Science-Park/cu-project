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

import React, { useState, useEffect } from 'react';
import { sendMessage } from '../messaging';
import './InteractionButtons.css';

interface InteractionButtonsProps {
    isActive: boolean;
    onCustomEvent?: (event: any) => void;
}

const InteractionButtons: React.FC<InteractionButtonsProps> = ({ isActive, onCustomEvent }) => {
    const [showTestButton, setShowTestButton] = useState(false);
    const [interactionMessage, setInteractionMessage] = useState('');
    const [showWeather, setShowWeather] = useState(false);
    const [cameraMode, setCameraMode] = useState('first-person');

    const toggleWeather = () => {
        const newWeatherState = !showWeather;
        setShowWeather(newWeatherState);
        
        sendMessage('weather_toggle', {
            enabled: newWeatherState
        });
    };

    const switchCamera = () => {
        const newCameraMode = cameraMode === 'first-person' ? 'third-person' : 'first-person';
        setCameraMode(newCameraMode);
        
        sendMessage('camera_switch', {
            mode: newCameraMode
        });
    };

    useEffect(() => {
        // Handle custom events from the USD scene
        const handleCustomEvent = (event: any) => {
            try {
                // Check if the event is wrapped in a payload (from Kit application)
                let actualEvent = event;
                if (event.event_type === 'playerInteractionEvent' && event.payload) {
                    actualEvent = event.payload;
                }
                
                if (actualEvent.event_type === 'player_interaction') {
                    if (actualEvent.action === 'entered_box') {
                        setShowTestButton(true);
                        setInteractionMessage(actualEvent.payload?.message || 'Player entered interaction area');
                    } else if (actualEvent.action === 'exited_box') {
                        setShowTestButton(false);
                        setInteractionMessage(actualEvent.payload?.message || 'Player exited interaction area');
                    }
                } else if (actualEvent.event_type === 'ui_interaction') {
                    if (actualEvent.action === 'test_button_clicked') {
                        setInteractionMessage(actualEvent.payload?.message || 'Test button was clicked!');
                    }
                }
            } catch (error) {
                console.error('Error handling custom event:', error);
            }
        };

        // Listen for custom events from AppStream
        const handleWindowEvent = (event: any) => {
            handleCustomEvent(event.detail);
        };

        // Set up both event handlers
        if (onCustomEvent) {
            onCustomEvent(handleCustomEvent);
        }
        
        // Events 2.0 messages come through onCustomEvent prop (no window events needed)
        return () => {
            // Cleanup - no window event listeners needed with Events 2.0
        };
    }, [onCustomEvent]);

    const handleTestButtonClick = () => {
        sendMessage('ui_interaction', {
            message: 'Test button clicked from web UI',
            timestamp: Date.now()
        });
    };

    if (!isActive || !showTestButton) {
        return null;
    }

    return (
        <div className="interaction-buttons-container">
            <div className="interaction-message">
                {interactionMessage}
            </div>
            <button 
                className="test-button"
                onClick={handleTestButtonClick}
            >
                Test Button
            </button>
            
            {/* Add weather and camera controls as additional buttons */}
            <div style={{ marginTop: '10px', display: 'flex', gap: '10px' }}>
                <button
                    onClick={toggleWeather}
                    style={{
                        padding: '8px 16px',
                        backgroundColor: showWeather ? '#4CAF50' : '#f44336',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '14px'
                    }}
                >
                    Weather: {showWeather ? 'ON' : 'OFF'}
                </button>
                
                <button
                    onClick={switchCamera}
                    style={{
                        padding: '8px 16px',
                        backgroundColor: '#2196F3',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '14px'
                    }}
                >
                    Camera: {cameraMode}
                </button>
            </div>
        </div>
    );
};

export default InteractionButtons;

