import React, { useEffect, useRef, useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Viewer, Globe, Scene, Camera } from 'resium';
import {
    Ion,
    Cartesian3,
    Math as CesiumMath,
    Terrain,
    type Viewer as CesiumViewer,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';

import { beginViewTransition, notifyViewTransitionKitReady } from '../../viewTransition';
import { useGlobeCameraFlight } from './useGlobeCameraFlight';
import GlobeLocationPin, { type GlobeLocation } from './GlobeLocationPin';
import globeConfig from '../../../../config/globe-locations.json';
import './GlobeViewOverlay.css';

import type { CameraType } from '../../types';

const CESIUM_TOKEN = (import.meta.env.CESIUM_ION_TOKEN as string | undefined) ?? '';
Ion.defaultAccessToken = CESIUM_TOKEN;
if (!CESIUM_TOKEN) {
    console.warn(
        '[GlobeView] CESIUM_ION_TOKEN is not set in .env — globe imagery and terrain will fail to load (you may see a black globe). ' +
        'Set CESIUM_ION_TOKEN in the repo root .env file.',
    );
}

interface Props {
    onExitToView: (targetView: CameraType) => void;
}

const locations = globeConfig.locations as GlobeLocation[];
const initialView = globeConfig.globe.initialView;

const GlobeViewOverlay: React.FC<Props> = ({ onExitToView }) => {
    const { t } = useTranslation();
    const viewerRef = useRef<CesiumViewer | null>(null);
    const terrainLoadedRef = useRef(false);
    const [flyingIn, setFlyingIn] = useState(false);
    const pendingExitRef = useRef<GlobeLocation | null>(null);
    const cloudRef = useRef<HTMLDivElement>(null);

    const firstLocation = locations[0];
    const waypoints = useMemo(
        () => firstLocation?.cameraFlight.waypoints ?? [],
        [firstLocation],
    );

    const handleFlightProgress = useCallback((altitude: number) => {
        if (!cloudRef.current) return;
        const TOP = 15000, PEAK = 9000, BOTTOM = 4000, MAX_OP = 0.92;
        let opacity = 0;
        if (altitude >= BOTTOM && altitude <= TOP) {
            opacity = altitude >= PEAK
                ? (TOP - altitude) / (TOP - PEAK)
                : (altitude - BOTTOM) / (PEAK - BOTTOM);
            opacity = Math.max(0, Math.min(1, opacity)) * MAX_OP;
        }
        cloudRef.current.style.opacity = String(opacity);
    }, []);

    const { flightComplete, startFlight, reset } = useGlobeCameraFlight(waypoints);

    useEffect(() => {
        if (!flightComplete || !pendingExitRef.current) return;
        const location = pendingExitRef.current;
        pendingExitRef.current = null;

        const msg = t(location.transitionMessageKey, { defaultValue: `Entering ${location.fallbackLabel}\u2026` });
        beginViewTransition({
            message: msg,
            onFadeOutComplete: () => {
                setFlyingIn(false);
                onExitToView((location.targetView ?? 'bird_eye') as CameraType);
            },
        });
    }, [flightComplete, t, onExitToView]);

    const handleViewerReady = useCallback((viewer: CesiumViewer) => {
        viewerRef.current = viewer;

        if (viewer.scene.sun) viewer.scene.sun.show = true;
        if (viewer.scene.moon) viewer.scene.moon.show = true;
        viewer.scene.globe.enableLighting = true;
        viewer.scene.globe.showGroundAtmosphere = true;
        viewer.scene.fog.enabled = true;
        viewer.scene.fog.density = 2.0e-4;
        if (viewer.scene.skyAtmosphere) {
            viewer.scene.skyAtmosphere.show = true;
            viewer.scene.skyAtmosphere.perFragmentAtmosphere = true;
        }

        // Surface imagery / terrain failures so a "black globe" episode is
        // diagnosable instead of silent. Cesium's default world imagery and
        // terrain both go through Ion — if Ion is briefly unavailable or the
        // token is rejected, the layer errors and we get an unrendered globe.
        try {
            const imagery = viewer.scene.imageryLayers.get(0);
            if (imagery && imagery.imageryProvider && (imagery.imageryProvider as any).errorEvent) {
                (imagery.imageryProvider as any).errorEvent.addEventListener((err: any) => {
                    console.error('[GlobeView] Imagery layer error (likely Cesium Ion):', err);
                });
            }
            viewer.scene.terrainProvider.errorEvent?.addEventListener?.((err: any) => {
                console.error('[GlobeView] Terrain provider error (likely Cesium Ion):', err);
            });
        } catch (e) {
            console.warn('[GlobeView] Could not attach imagery/terrain error listeners:', e);
        }

        if (!terrainLoadedRef.current) {
            terrainLoadedRef.current = true;
            try {
                viewer.scene.setTerrain(Terrain.fromWorldTerrain());
            } catch {
                // falls back to ellipsoid
            }
        }

        viewer.camera.setView({
            destination: Cartesian3.fromDegrees(
                initialView.lon,
                initialView.lat,
                initialView.alt,
            ),
            orientation: {
                heading: CesiumMath.toRadians(initialView.heading),
                pitch: CesiumMath.toRadians(initialView.pitch),
                roll: 0,
            },
        });

        setTimeout(() => notifyViewTransitionKitReady(), 200);
    }, []);

    useEffect(() => {
        return () => {
            reset();
            terrainLoadedRef.current = false;
            pendingExitRef.current = null;
        };
    }, [reset]);

    const handleLocationClick = useCallback((location: GlobeLocation) => {
        if (flyingIn) return;
        const viewer = viewerRef.current;
        if (!viewer) return;

        setFlyingIn(true);
        pendingExitRef.current = location;
        startFlight(viewer, handleFlightProgress);
    }, [flyingIn, startFlight, handleFlightProgress]);

    const handleBackClick = useCallback(() => {
        beginViewTransition({
            message: t('streaming.switchingOverview'),
            onFadeOutComplete: () => {
                onExitToView('bird_eye');
            },
        });
    }, [t, onExitToView]);

    return (
        <div className="globe-view-overlay">
            <button type="button" className="globe-view-back-button" onClick={handleBackClick}>
                ‹ {t('common.back')}
            </button>

            {!flyingIn && (
                <div className="globe-view-hint">
                    {t('globe.clickPinHint', { defaultValue: 'Click a location pin to enter' })}
                </div>
            )}

            {flyingIn && (
                <div className="globe-view-hint globe-view-hint--flying">
                    {t('streaming.enteringGothenburg', { defaultValue: 'Entering Gothenburg\u2026' })}
                </div>
            )}

            <div ref={cloudRef} className="globe-cloud-layer" style={{ opacity: 0 }} />

            <Viewer
                full
                timeline={false}
                animation={false}
                baseLayerPicker={false}
                geocoder={false}
                homeButton={false}
                sceneModePicker={false}
                navigationHelpButton={false}
                fullscreenButton={false}
                selectionIndicator={false}
                infoBox={false}
                ref={(ref: any) => {
                    if (ref?.cesiumElement && ref.cesiumElement !== viewerRef.current) {
                        handleViewerReady(ref.cesiumElement);
                    }
                }}
            >
                <Scene />
                <Globe enableLighting />
                <Camera />

                {locations.map((loc) => (
                    <GlobeLocationPin
                        key={loc.id}
                        location={loc}
                        label={t(loc.labelKey, { defaultValue: loc.fallbackLabel })}
                        visible={!flyingIn}
                        onClick={handleLocationClick}
                    />
                ))}
            </Viewer>
        </div>
    );
};

export default GlobeViewOverlay;
