/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 */
import { useEffect } from 'react';

export interface RemoteVideoPointerGesturesParams {
    streamReady: boolean;
    isViewer: boolean;
    sendCustomMessage: (eventType: string, payload: any) => void;
    nextClickPlacesMarker: boolean;
    nextClickPlacesIncident: boolean;
    nextClickPlacesCamera: boolean;
    incidentSizePreset: '1x1' | '2x2' | '2x1';
    incidentShape: 'cube' | 'cone' | 'torus';
    onMarkerClickConsumed?: () => void;
    onIncidentClickConsumed?: () => void;
    onCameraClickConsumed?: () => void;
    pointClickEnabled: boolean;
    osmNavigateActive: boolean;
    osmRouteOverlayActive: boolean;
    isBirdEye: boolean;
    birdEyeRouteActive: boolean;
    activeFixedCamera: string | null;
    invertTouchLook: boolean;
    usdEditIntent: string | null;
    vertexDragActive: boolean;
}

/**
 * Pointer gestures on `#remote-video`: tap → pick, drag → touch look / USD vertex drag /
 * bird-eye pinch-zoom + twist + wheel zoom.
 */
export function useRemoteVideoPointerGestures(p: RemoteVideoPointerGesturesParams): void {
    const {
        streamReady,
        isViewer,
        sendCustomMessage,
        nextClickPlacesMarker,
        nextClickPlacesIncident,
        nextClickPlacesCamera,
        incidentSizePreset,
        incidentShape,
        onMarkerClickConsumed,
        onIncidentClickConsumed,
        onCameraClickConsumed,
        pointClickEnabled,
        osmNavigateActive,
        osmRouteOverlayActive,
        isBirdEye,
        birdEyeRouteActive,
        activeFixedCamera,
        invertTouchLook,
        usdEditIntent,
        vertexDragActive,
    } = p;

    useEffect(() => {
        if (!streamReady || isViewer) return;

        const video = document.getElementById('remote-video') as HTMLVideoElement | null;
        if (!video) return;

        const DRAG_THRESHOLD_PX = 8;
        const ZOOM_MIN = 1.0;
        const ZOOM_MAX = 4.0;
        const ZOOM_WHEEL_STEP = 0.12;
        const ROTATE_DEG_PER_PX = 0.4;
        let activePointerId: number | null = null;
        let startX = 0;
        let startY = 0;
        let lastX = 0;
        let lastY = 0;
        let isDragging = false;
        let isRotateDrag = false;

        const pinchPointers = new Map<number, { x: number; y: number }>();
        let pinchActive = false;
        let pinchStartDist = 0;
        let pinchStartLevel = 1.0;
        let zoomLevel = 1.0;
        let twistLastAngleRad: number | null = null;
        let twistActiveInPinch = false;

        const sendZoomLevel = (level: number) => {
            const clamped = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, level));
            if (Math.abs(clamped - zoomLevel) < 0.01) return;
            zoomLevel = clamped;
            try {
                sendCustomMessage('birdEyeZoomLevel', { level: clamped });
            } catch {}
        };

        const sendYawDelta = (deltaDeg: number) => {
            if (!isBirdEye) return;
            if (!isFinite(deltaDeg) || Math.abs(deltaDeg) < 0.05) return;
            try {
                sendCustomMessage('birdEyeYawDelta', { deltaDeg });
                twistActiveInPinch = true;
            } catch {}
        };

        const angleBetweenRad = (
            a: { x: number; y: number },
            b: { x: number; y: number },
        ) => Math.atan2(-(b.y - a.y), b.x - a.x);

        const wrapAngle = (a: number) => {
            while (a > Math.PI) a -= 2 * Math.PI;
            while (a < -Math.PI) a += 2 * Math.PI;
            return a;
        };

        const handlePointerDown = (evt: PointerEvent) => {
            const isRotateButton =
                isBirdEye &&
                evt.pointerType === 'mouse' &&
                (evt.button === 1 || (evt.button === 0 && evt.shiftKey));
            if (isRotateButton) {
                if (activePointerId !== null) return;
                evt.preventDefault();
                activePointerId = evt.pointerId;
                startX = lastX = evt.clientX;
                startY = lastY = evt.clientY;
                isDragging = true;
                isRotateDrag = true;
                try { video.setPointerCapture(evt.pointerId); } catch {}
                return;
            }

            if (evt.button !== 0) return;
            if (isBirdEye && (evt.pointerType === 'touch' || evt.pointerType === 'pen')) {
                pinchPointers.set(evt.pointerId, { x: evt.clientX, y: evt.clientY });
                if (pinchPointers.size === 2) {
                    pinchActive = true;
                    isDragging = false;
                    activePointerId = null;
                    const pts = Array.from(pinchPointers.values());
                    const dx = pts[0].x - pts[1].x;
                    const dy = pts[0].y - pts[1].y;
                    pinchStartDist = Math.max(1, Math.hypot(dx, dy));
                    pinchStartLevel = zoomLevel;
                    twistLastAngleRad = angleBetweenRad(pts[0], pts[1]);
                    twistActiveInPinch = false;
                    evt.preventDefault();
                    return;
                }
            }
            if (activePointerId !== null) return;
            evt.preventDefault();
            activePointerId = evt.pointerId;
            startX = lastX = evt.clientX;
            startY = lastY = evt.clientY;
            isDragging = false;
            isRotateDrag = false;
            video.setPointerCapture(evt.pointerId);
        };

        const handlePointerMove = (evt: PointerEvent) => {
            if (pinchActive && pinchPointers.has(evt.pointerId)) {
                pinchPointers.set(evt.pointerId, { x: evt.clientX, y: evt.clientY });
                if (pinchPointers.size >= 2) {
                    const pts = Array.from(pinchPointers.values()).slice(0, 2);
                    const dx = pts[0].x - pts[1].x;
                    const dy = pts[0].y - pts[1].y;
                    const dist = Math.max(1, Math.hypot(dx, dy));
                    sendZoomLevel(pinchStartLevel * (dist / pinchStartDist));
                    const angle = angleBetweenRad(pts[0], pts[1]);
                    if (twistLastAngleRad !== null) {
                        const dRad = wrapAngle(angle - twistLastAngleRad);
                        sendYawDelta((dRad * 180) / Math.PI);
                    }
                    twistLastAngleRad = angle;
                    evt.preventDefault();
                }
                return;
            }
            if (evt.pointerId !== activePointerId) return;
            evt.preventDefault();

            const dx = evt.clientX - lastX;
            const dy = evt.clientY - lastY;
            lastX = evt.clientX;
            lastY = evt.clientY;

            if (isRotateDrag) {
                sendYawDelta(dx * ROTATE_DEG_PER_PX);
                return;
            }

            if (!isDragging) {
                const totalDx = evt.clientX - startX;
                const totalDy = evt.clientY - startY;
                if (Math.sqrt(totalDx * totalDx + totalDy * totalDy) > DRAG_THRESHOLD_PX) {
                    isDragging = true;
                } else {
                    return;
                }
            }

            if (vertexDragActive) {
                sendCustomMessage('usdEdit.dragVertex', { dx, dy });
                return;
            }

            const sx = invertTouchLook ? -dx : dx;
            const sy = invertTouchLook ? -dy : dy;

            if (activeFixedCamera && activeFixedCamera.startsWith('placed_cam_')) {
                sendCustomMessage('placedCameraRotate', { cameraId: activeFixedCamera, deltaYaw: -sx * 0.15, deltaPitch: -sy * 0.15 });
                return;
            }

            if (activeFixedCamera) return;

            sendCustomMessage('touchLookDelta', { dx: sx, dy: sy });
        };

        const handlePointerUp = (evt: PointerEvent) => {
            const wasTrackedForPinch = pinchPointers.delete(evt.pointerId);
            const endedPinch = wasTrackedForPinch && pinchActive;
            if (pinchPointers.size < 2) {
                pinchActive = false;
                twistLastAngleRad = null;
            }
            if (endedPinch) {
                if (isBirdEye && twistActiveInPinch) {
                    sendCustomMessage('birdEyeYawEnd', {});
                }
                twistActiveInPinch = false;
                return;
            }
            if (evt.pointerId !== activePointerId) return;
            const wasDragging = isDragging;
            const wasRotateDrag = isRotateDrag;
            activePointerId = null;
            isDragging = false;
            isRotateDrag = false;
            try { video.releasePointerCapture(evt.pointerId); } catch {}

            if (wasRotateDrag) {
                if (isBirdEye) {
                    sendCustomMessage('birdEyeYawEnd', {});
                }
                return;
            }
            if (wasDragging) {
                // Arm Kit-side release coast for stream drag-look (not placed-cam / map twist).
                if (
                    !activeFixedCamera?.startsWith('placed_cam_')
                    && !vertexDragActive
                ) {
                    sendCustomMessage('touchLookEnd', {});
                }
                return;
            }

            const rect = video.getBoundingClientRect();
            const videoW = video.videoWidth || 1920;
            const videoH = video.videoHeight || 1080;
            const elementAspect = rect.width / rect.height;
            const videoAspect = videoW / videoH;

            let videoDisplayW: number, videoDisplayH: number;
            if (elementAspect > videoAspect) {
                videoDisplayW = rect.width;
                videoDisplayH = rect.width / videoAspect;
            } else {
                videoDisplayH = rect.height;
                videoDisplayW = rect.height * videoAspect;
            }

            const videoLeft = rect.left - (videoDisplayW - rect.width) / 2;
            const videoTop = rect.top - (videoDisplayH - rect.height) / 2;

            const xInVideo = Math.min(Math.max(startX - videoLeft, 0), videoDisplayW);
            const yInVideo = Math.min(Math.max(startY - videoTop, 0), videoDisplayH);
            const ndcX = (xInVideo / videoDisplayW) * 2 - 1;
            const ndcY = 1 - (yInVideo / videoDisplayH) * 2;

            const isViewingPlacedCam = activeFixedCamera && activeFixedCamera.startsWith('placed_cam_');

            try {
                const base = `${Date.now()}_${Math.random().toString(16).slice(2)}`;
                if (usdEditIntent) {
                    sendCustomMessage("younite.pick.request", {
                        requestId: `usdEdit_${base}`, intent: usdEditIntent, ndcX, ndcY,
                    });
                } else if (nextClickPlacesCamera) {
                    sendCustomMessage("younite.pick.request", {
                        requestId: `cam_${base}`, intent: "cameraPlacement", ndcX, ndcY,
                        cameraYaw: 0, cameraPitch: -15,
                    });
                    onCameraClickConsumed?.();
                } else if (isViewingPlacedCam) {
                    /* no pick */
                } else if (nextClickPlacesMarker || nextClickPlacesIncident) {
                    if (nextClickPlacesMarker) {
                        sendCustomMessage("younite.pick.request", { requestId: `marker_${base}`, intent: "marker", ndcX, ndcY });
                        onMarkerClickConsumed?.();
                    }
                    if (nextClickPlacesIncident) {
                        const sizeLookup: Record<string, { width: number; depth: number }> = {
                            '1x1': { width: 100, depth: 100 },
                            '2x2': { width: 200, depth: 200 },
                            '2x1': { width: 200, depth: 100 },
                        };
                        const dims = sizeLookup[incidentSizePreset] || sizeLookup['1x1'];
                        sendCustomMessage("younite.pick.request", {
                            requestId: `incident_${base}`, intent: "incident", ndcX, ndcY,
                            incidentWidth: dims.width, incidentDepth: dims.depth,
                            incidentShape: incidentShape,
                        });
                        onIncidentClickConsumed?.();
                    }
                } else if (osmNavigateActive) {
                    sendCustomMessage("younite.pick.request", {
                        requestId: `osmnav_${base}`,
                        intent: "osmNavigate",
                        ndcX,
                        ndcY,
                    });
                } else if (osmRouteOverlayActive && pointClickEnabled && !isBirdEye) {
                    sendCustomMessage("younite.pick.request", {
                        requestId: `osmrouteoverlay_${base}`,
                        intent: "osmRouteOverlayMarker",
                        ndcX,
                        ndcY,
                        allowNavigation: true,
                    });
                } else if (isBirdEye) {
                    if (birdEyeRouteActive) {
                        return;
                    }
                    sendCustomMessage("younite.pick.request", {
                        requestId: `bep_${base}`,
                        intent: "birdEyePin",
                        ndcX,
                        ndcY,
                    });
                } else {
                    sendCustomMessage("younite.pick.request", {
                        requestId: `pc_${base}`,
                        intent: "pointClick",
                        ndcX,
                        ndcY,
                        allowNavigation: pointClickEnabled,
                    });
                }
            } catch (error) {
                console.warn('Failed to send pick request:', error);
            }
        };

        const handlePointerCancel = (evt: PointerEvent) => {
            pinchPointers.delete(evt.pointerId);
            if (pinchPointers.size < 2) {
                pinchActive = false;
                twistLastAngleRad = null;
            }
            if (evt.pointerId !== activePointerId) return;
            activePointerId = null;
            isDragging = false;
            isRotateDrag = false;
            try { video.releasePointerCapture(evt.pointerId); } catch {}
        };

        const handleWheel = (evt: WheelEvent) => {
            if (!isBirdEye) return;
            evt.preventDefault();
            const stepScale = evt.ctrlKey ? 0.4 : 1.0;
            const sign = evt.deltaY < 0 ? 1 : -1;
            sendZoomLevel(zoomLevel + sign * ZOOM_WHEEL_STEP * stepScale);
        };

        video.addEventListener('pointerdown', handlePointerDown);
        video.addEventListener('pointermove', handlePointerMove);
        video.addEventListener('pointerup', handlePointerUp);
        video.addEventListener('pointercancel', handlePointerCancel);
        video.addEventListener('wheel', handleWheel, { passive: false });

        return () => {
            video.removeEventListener('pointerdown', handlePointerDown);
            video.removeEventListener('pointermove', handlePointerMove);
            video.removeEventListener('pointerup', handlePointerUp);
            video.removeEventListener('pointercancel', handlePointerCancel);
            video.removeEventListener('wheel', handleWheel);
        };
    }, [
        streamReady,
        isViewer,
        sendCustomMessage,
        nextClickPlacesMarker,
        nextClickPlacesIncident,
        nextClickPlacesCamera,
        incidentSizePreset,
        incidentShape,
        onMarkerClickConsumed,
        onIncidentClickConsumed,
        onCameraClickConsumed,
        pointClickEnabled,
        osmNavigateActive,
        osmRouteOverlayActive,
        isBirdEye,
        birdEyeRouteActive,
        activeFixedCamera,
        invertTouchLook,
        usdEditIntent,
        vertexDragActive,
    ]);
}
