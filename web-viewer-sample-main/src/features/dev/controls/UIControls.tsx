/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 */

import React, { useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppMode } from '../../../context/AppModeContext';
import { useEnvironment, useNavigation, useStream, useControl, useAppUI } from '../../streaming/contexts';
import { beginViewTransition } from '../../streaming/viewTransition';
import { FIXED_CAMERAS, sendMessage } from '../../streaming/messaging';
import {
    CamerasSubmenu, SoundSubmenu, NavigationSubmenu, SceneSubmenu,
    MediaSubmenu, SimulationSubmenu, ToolsSubmenu, IotSubmenu,
    FixedCameraBar, QuickStatus, FloatingActions,
} from './submenus';
import type { CameraType } from './submenus/types';
import './UIControls.css';

export type { CameraType, PhysicsState, ControlMode } from './submenus';

const MENU_CATEGORIES = [
    { id: 'cameras', label: 'Cameras', icon: '📷' },
    { id: 'sound', label: 'Sound', icon: '🔊' },
    { id: 'navigation', label: 'Navigation', icon: '🗺️' },
    { id: 'scene', label: 'Scene', icon: '🏙️' },
    { id: 'media', label: 'Media', icon: '🎬' },
    { id: 'simulation', label: 'Simulation', icon: '👥' },
    { id: 'tools', label: 'Tools', icon: '🛠️' },
    { id: 'iot', label: 'IoT', icon: '📡' },
] as const;

const UIControls: React.FC = () => {
    const { t } = useTranslation();
    const { setMode } = useAppMode();
    const env = useEnvironment();
    const nav = useNavigation();
    const stream = useStream();
    const ctrl = useControl();
    const appUI = useAppUI();

    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [activeSubmenu, setActiveSubmenu] = useState<string | null>(null);

    const closeMenu = useCallback(() => {
        setIsMenuOpen(false);
        setActiveSubmenu(null);
    }, []);

    const handleCameraChangeForUi = useCallback(
        (cameraType: CameraType) => {
            if (cameraType === 'space') {
                // Snapshot the player's first-person pose on Kit before we
                // hide them under the globe overlay. When the user later
                // clicks a globe pin to exit back into bird's-eye, the normal
                // FP→birdEye `cameraViewSwitchRequest` handler will only see a
                // valid stored FP state if it was captured BEFORE the player
                // got teleported to the bird-eye spawn — otherwise wayfinding
                // and the user-location arrow snap to the bird-eye spawn
                // instead of where the user actually was on the ground.
                // Direct Space entry (FP → space → globe pin → bird_eye)
                // skips the usual FP→birdEye step entirely, so we capture
                // here as the explicit pre-space store.
                if (env.currentCamera === 'first_person') {
                    sendMessage('playerStateCaptureRequest', {});
                }
                beginViewTransition({
                    message: t('streaming.enteringSpace'),
                    onFadeOutComplete: () => {
                        env.handleCameraChange(cameraType);
                    },
                });
                return;
            }
            beginViewTransition({
                target: cameraType === 'first_person' ? 'firstPerson' : 'birdEye',
                message: cameraType === 'first_person' ? t('streaming.switchingFirstPerson') : t('streaming.switchingOverview'),
                onFadeOutComplete: () => env.handleCameraChange(cameraType),
            });
        },
        [env, t],
    );

    const handleSceneSwitch = useCallback((sceneId: string) => {
        ctrl.setUiInteractionBoxes(null);
        stream.handleSceneSwitch(sceneId);
    }, [ctrl, stream]);

    const allFixedCameras = useMemo(
        () => [...FIXED_CAMERAS, ...env.placedCameras],
        [env.placedCameras],
    );

    if (!stream.streamReady || appUI.isViewer) return null;

    const hasActiveIndicator = nav.navmeshActive || env.cameraDataHeatmapActive || env.cameraDataTrackerActive
        || (env.activeFixedCamera != null && env.activeFixedCamera !== '')
        || ((ctrl.iotAirStations?.length ?? 0) > 0);

    return (
        <div className="ui-controls">
            <button
                className={`hamburger-menu ${isMenuOpen ? 'open' : ''} ${hasActiveIndicator ? 'active' : ''}`}
                onClick={() => { const next = !isMenuOpen; setIsMenuOpen(next); if (!next) setActiveSubmenu(null); }}
                title="Open Controls"
            >
                <span></span><span></span><span></span>
            </button>

            {isMenuOpen && (
                <div className="controls-menu-overlay" onClick={closeMenu}>
                    <div className="controls-menu" onClick={(e) => e.stopPropagation()}>

                        {!activeSubmenu && (
                            <div className="controls-menu-categories">
                                {MENU_CATEGORIES.map((cat) => (
                                    <button key={cat.id} className="controls-menu-category-btn" onClick={() => setActiveSubmenu(cat.id)}>
                                        <span className="controls-category-icon">{cat.icon}</span>
                                        <span className="controls-category-label">{cat.label}</span>
                                        <span className="controls-category-arrow">›</span>
                                    </button>
                                ))}
                                <div className="controls-menu-divider" />
                                <button className="controls-menu-category-btn controls-mode-switch" onClick={() => { closeMenu(); setMode('cu'); }}>
                                    <span className="controls-category-icon">🎨</span>
                                    <span className="controls-category-label">CU Mode</span>
                                </button>
                            </div>
                        )}

                        {activeSubmenu === 'cameras' && (
                            <CamerasSubmenu
                                onCameraChange={(ct) => { handleCameraChangeForUi(ct as CameraType); closeMenu(); }}
                                closeMenu={closeMenu}
                            />
                        )}
                        {activeSubmenu === 'sound' && <SoundSubmenu closeMenu={closeMenu} />}
                        {activeSubmenu === 'navigation' && <NavigationSubmenu closeMenu={closeMenu} />}
                        {activeSubmenu === 'scene' && <SceneSubmenu onSceneSwitch={handleSceneSwitch} closeMenu={closeMenu} />}
                        {activeSubmenu === 'media' && <MediaSubmenu closeMenu={closeMenu} />}
                        {activeSubmenu === 'simulation' && <SimulationSubmenu closeMenu={closeMenu} />}
                        {activeSubmenu === 'tools' && <ToolsSubmenu closeMenu={closeMenu} />}
                        {activeSubmenu === 'iot' && <IotSubmenu closeMenu={closeMenu} />}

                    </div>
                </div>
            )}

            <FixedCameraBar fixedCameras={allFixedCameras} />

            <QuickStatus />

            <FloatingActions />
        </div>
    );
};

export default UIControls;
