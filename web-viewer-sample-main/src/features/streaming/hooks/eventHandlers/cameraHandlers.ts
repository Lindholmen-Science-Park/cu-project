import type { EventStateSetters } from './types';
import { notifyXformViewCameraReady } from '../../overlays/xformViewCameraChannel';

export function handleCameraEvents(event: any, s: EventStateSetters): void {
    if (event.event_type === 'cameraDataVisualizationHeatmapStatus') {
        s.setCameraDataHeatmapActive(event.payload.active === true);
        console.log(`Camera data heatmap ${event.payload.active ? 'activated' : 'deactivated'}`);
        return;
    }

    if (event.event_type === 'cameraDataVisualizationTrackerStatus') {
        s.setCameraDataTrackerActive(event.payload.active === true);
        console.log(`Camera data tracker ${event.payload.active ? 'activated' : 'deactivated'}`);
        if (!event.payload.active) s.setCameraDataStats(null);
        return;
    }

    if (event.event_type === 'cameraDataVisualizationStats') {
        s.setCameraDataStats({
            current: event.payload.current || 0,
            unique_last_1m: event.payload.unique_last_1m || 0,
            avg_concurrent_1m: event.payload.avg_concurrent_1m || 0,
            traffic_level: event.payload.traffic_level || 'low',
        });
        return;
    }

    if (event.event_type === 'fixedCameraStatus') {
        const p = event.payload || {};
        s.setActiveFixedCamera(p.active === true && p.cameraId ? p.cameraId : null);
        return;
    }

    if (event.event_type === 'xformViewCameraReady') {
        // See xformViewCameraChannel.ts.
        const p = event.payload || {};
        notifyXformViewCameraReady({
            primPath: String(p.primPath || ''),
            ok: p.ok !== false,
        });
        return;
    }

    if (event.event_type === 'placedCamerasSync') {
        const p = event.payload || {};
        const cameras: { id: string; label: string; primPath?: string }[] = Array.isArray(p.cameras)
            ? p.cameras.map((c: any) => ({ id: String(c.id || ''), label: String(c.label || c.id || ''), primPath: c.primPath ? String(c.primPath) : undefined }))
            : [];
        s.setPlacedCameras(cameras);
        return;
    }

    if (event.event_type === 'cameraDepthStatus') {
        const p = event.payload || {};
        const status = String(p.status || 'idle');
        if (status === 'capturing') s.setCameraDepthStatus('capturing');
        else if (status === 'done') { s.setCameraDepthStatus('done'); s.setCameraDepthPointCount(Number(p.pointCount) || 0); console.log(`[camera_depth] Point cloud created: ${p.pointCount} points`); }
        else if (status === 'detecting') s.setCameraDepthStatus('detecting');
        else if (status === 'obstacles_done') { s.setCameraDepthStatus('obstacles_done'); s.setCameraDepthObstacleCount(Number(p.obstacleCount) || 0); console.log(`[camera_depth] Obstacle areas created: ${p.obstacleCount}`); }
        else if (status === 'cleared') { s.setCameraDepthStatus('idle'); s.setCameraDepthPointCount(0); s.setCameraDepthObstacleCount(0); s.setCameraDepthPointsVisible(true); s.setCameraDepthAreasVisible(true); console.log('[camera_depth] Point cloud and obstacles cleared'); }
        else if (status === 'toggle_update') {
            if (p.pointsVisible != null) s.setCameraDepthPointsVisible(Boolean(p.pointsVisible));
            if (p.areasVisible != null) s.setCameraDepthAreasVisible(Boolean(p.areasVisible));
        }
        else if (status === 'error') { s.setCameraDepthStatus('error'); console.error(`[camera_depth] Error: ${p.error}`); }
        return;
    }

    if (event.event_type === 'cameraDataCalcStatus') {
        const p = event.payload || {};
        const status = String(p.status || '');
        const active = Boolean(p.active);
        if (status === 'baking') { s.setCameraDataCalcBaking(true); }
        else { s.setCameraDataCalcBaking(false); s.setCameraDataCalcActive(active); }
        return;
    }
}
