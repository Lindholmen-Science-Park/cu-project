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
import React, { useMemo } from 'react';
import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import StreamConfig from '../../config/stream.config.json';
import type { AppProps } from './connection/Window';
import { useStream, useEnvironment, useNavigation, useControl, useAppUI } from './contexts';
import { resolvePoiLocalizedTitle } from './utils/poiLocalizedTitle';
import AppStreamCore from './AppStreamCore';

/**
 * Stream canvas wired from domain contexts + `appProps` session fields.
 * Mount only under `StreamOnlyWindow`'s provider stack.
 */
export const AppStreamConnected: React.FC<{
    appProps: AppProps;
    handleCustomEvent: (event: any) => void;
    style?: CSSProperties;
}> = ({ appProps, handleCustomEvent, style }) => {
    const { t } = useTranslation();
    const stream = useStream();
    const env = useEnvironment();
    const nav = useNavigation();
    const ctrl = useControl();
    const appUI = useAppUI();

    const seatNavigationOverlay = useMemo(() => {
        if (appUI.seatStreamOverlayActive) {
            const isSeatSwap = nav.seatRouteDisplayLabel != null;
            return {
                isMoving: !!nav.movingToSeatId,
                seatLabel: nav.activeSeatRouteId!,
                displayLabel: nav.seatRouteDisplayLabel ?? undefined,
                onPlay: nav.handleSeatMoveStart,
                onStop: nav.handleSeatMoveStop,
                onDismiss: nav.handleSeatRouteDismiss,
                routeMeasure: nav.routeMeasureByRouteId['seat_nav'],
                routeMeasureEnabled: nav.routeMeasureEnabled,
                approachUsesGenericLabel: isSeatSwap,
            };
        }
        if (appUI.restroomStreamOverlayActive) {
            let displayLabel = t('search.findToilet');
            const aid = nav.activePoiRouteId;
            if (aid && nav.poiRouteDisplayLabel) {
                displayLabel = nav.poiRouteDisplayLabel;
            } else if (aid) {
                for (let i = 0; i < nav.restroomResults.length; i++) {
                    const r = nav.restroomResults[i];
                    const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
                    const key = (r.poiId || primPath || `poi_${i}`) as string;
                    if (key === aid) {
                        displayLabel =
                            resolvePoiLocalizedTitle('restroom', (r.metadata || {}) as Record<string, unknown>, t)
                            || t('search.toiletSection', { n: i + 1 });
                        break;
                    }
                }
            }
            return {
                isMoving: !!nav.movingToPoiId,
                seatLabel: aid || 'poi',
                displayLabel,
                onPlay: nav.handlePoiMoveStart,
                onStop: nav.handlePoiMoveStop,
                onDismiss: nav.handleRestroomWidgetClose,
                routeMeasure: nav.routeMeasureByRouteId['poi_nav'],
                routeMeasureEnabled: nav.routeMeasureEnabled,
            };
        }
        if (appUI.quietStreamOverlayActive) {
            let displayLabel = t('search.findQuietArea');
            const qid = nav.activeQuietZoneRouteId;
            if (qid) {
                for (let i = 0; i < nav.quietZoneResults.length; i++) {
                    const r = nav.quietZoneResults[i];
                    const primPath = typeof r.poiRef === 'string' ? r.poiRef : '';
                    const key = (r.poiId || primPath || `poi_${i}`) as string;
                    if (key === qid) {
                        displayLabel =
                            resolvePoiLocalizedTitle('quiet_zone', (r.metadata || {}) as Record<string, unknown>, t)
                            || t('search.quietAreaPlaceholder', { n: i + 1 });
                        break;
                    }
                }
            }
            return {
                isMoving: !!nav.movingToQuietZoneId,
                seatLabel: qid || 'quiet_zone',
                displayLabel,
                onPlay: nav.handleQuietZoneMoveStart,
                onStop: nav.handleQuietZoneMoveStop,
                onDismiss: nav.handleQuietZoneWidgetClose,
                routeMeasure: nav.routeMeasureByRouteId['quiet_zone_nav'],
                routeMeasureEnabled: nav.routeMeasureEnabled,
            };
        }
        return null;
    }, [
        appUI.seatStreamOverlayActive,
        appUI.restroomStreamOverlayActive,
        appUI.quietStreamOverlayActive,
        t,
        nav.movingToSeatId,
        nav.activeSeatRouteId,
        nav.seatRouteDisplayLabel,
        nav.handleSeatMoveStart,
        nav.handleSeatMoveStop,
        nav.handleSeatRouteDismiss,
        nav.routeMeasureByRouteId,
        nav.routeMeasureEnabled,
        nav.movingToPoiId,
        nav.activePoiRouteId,
        nav.poiRouteDisplayLabel,
        nav.restroomResults,
        nav.handlePoiMoveStart,
        nav.handlePoiMoveStop,
        nav.handleRestroomWidgetClose,
        nav.movingToQuietZoneId,
        nav.activeQuietZoneRouteId,
        nav.quietZoneResults,
        nav.handleQuietZoneMoveStart,
        nav.handleQuietZoneMoveStop,
        nav.handleQuietZoneWidgetClose,
    ]);

    const usdEditIntent =
        ctrl.usdEditMode
            ? ctrl.usdEditSubMode === 'vertices'
                ? (ctrl.usdEditPhase === 'selectMesh' || ctrl.nextClickSelectsVertex) ? 'vertexEdit' : null
                : ctrl.usdEditSubMode === 'markers'
                    ? 'usdEditMarker'
                    : (ctrl.usdEditPhase === 'selectPrim' || ctrl.nextClickSelectsPrim) ? 'usdEditTransform' : null
            : null;

    return (
        <AppStreamCore
            style={style}
            isViewer={appUI.isViewer}
            sessionId={StreamConfig.source === 'local' ? '' : appProps.sessionId}
            backendUrl={StreamConfig.source === 'local' ? '' : appProps.backendUrl}
            signalingserver={StreamConfig.source === 'local' ? StreamConfig.local.server : appProps.signalingserver}
            signalingport={StreamConfig.source === 'local' ? StreamConfig.local.signalingPort : appProps.signalingport}
            mediaserver={StreamConfig.source === 'local' ? StreamConfig.local.server : appProps.mediaserver}
            mediaport={StreamConfig.source === 'local' ? (StreamConfig.local.mediaPort || 0) : appProps.mediaport}
            accessToken={appProps.accessToken}
            onStarted={stream.handleStreamStarted}
            onStreamFailed={stream.handleStreamFailed}
            onLoggedIn={(userId) => console.log(`User logged in: ${userId}`)}
            handleCustomEvent={handleCustomEvent}
            nextClickPlacesMarker={ctrl.nextClickPlacesMarker}
            nextClickPlacesIncident={ctrl.nextClickPlacesIncident}
            nextClickPlacesCamera={ctrl.nextClickPlacesCamera}
            osmNavigateActive={nav.osmNavigateOpen && !!nav.osmSelectedPoiId}
            osmRouteOverlayActive={
                !!nav.osmRouteOverlayVisible &&
                ctrl.controlMode === 'pointClick' &&
                env.currentCamera !== 'bird_eye' &&
                env.currentCamera !== 'space'
            }
            isBirdEye={env.currentCamera === 'bird_eye'}
            birdEyeRouteActive={
                !!ctrl.birdEyeRoutePoints &&
                (((ctrl.birdEyeRoutePoints.points?.length ?? 0) > 0) ||
                    ((ctrl.birdEyeRoutePoints.osmPoints?.length ?? 0) > 0))
            }
            incidentSizePreset={ctrl.incidentSizePreset}
            incidentShape={ctrl.incidentShape}
            onMarkerClickConsumed={ctrl.handleMarkerClickConsumed}
            onIncidentClickConsumed={ctrl.handleIncidentClickConsumed}
            onCameraClickConsumed={ctrl.handleCameraClickConsumed}
            pointClickEnabled={ctrl.controlMode === 'pointClick'}
            activeFixedCamera={env.activeFixedCamera}
            onLoadingStatus={stream.setLoadingText}
            seatNavigationOverlay={seatNavigationOverlay}
            seatArrivalCelebrationVisible={appUI.seatArrivalCelebrationVisible}
            seatArrivalLabel={appUI.seatArrivalLabel}
            onArrivalDismiss={appUI.dismissArrivalCelebration}
            poiArrivalVisible={appUI.poiArrivalVisible}
            poiArrivalLabel={appUI.poiArrivalLabel}
            onPoiArrivalDismiss={appUI.dismissPoiArrival}
            invertTouchLook={appUI.invertTouchLook}
            usdEditIntent={usdEditIntent}
            vertexDragActive={ctrl.vertexDragEnabled && ctrl.selectedVertexInfo !== null}
        />
    );
};
