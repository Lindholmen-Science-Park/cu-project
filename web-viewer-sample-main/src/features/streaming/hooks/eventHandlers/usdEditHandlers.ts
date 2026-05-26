import { sendMessage } from '../../messaging';
import type { EventStateSetters } from './types';

export function handleUsdEditEvents(event: any, s: EventStateSetters): void {
    if (event.event_type === 'usdEditStateUpdate') {
        const p = event.payload || {};
        const phase = String(p.phase || 'idle');
        if (phase === 'meshSelected') {
            s.setUsdEditPhase?.('selectVertex');
            s.setEditingMeshPath?.(String(p.meshPath || ''));
            s.setEditingVertexCount?.(Number(p.vertexCount) || 0);
            s.setSelectedVertexInfo?.(null);
        } else if (phase === 'primSelected') {
            s.setUsdEditPhase?.('primSelected');
        } else if (phase === 'markerCreated') {
            s.setUsdEditPhase?.('markerCreated');
            s.setMarkerPlacementArmed?.(false);
        } else if (phase === 'markerSelected') {
            s.setUsdEditPhase?.('markerSelected');
        } else if (phase === 'idle' || phase === 'error') {
            s.setUsdEditPhase?.('idle');
            s.setEditingMeshPath?.(null);
            s.setEditingVertexCount?.(0);
            s.setSelectedVertexInfo?.(null);
            s.setTransformInfo?.(null);
            s.setSelectedMarkerInfo?.(null);
        }
        return;
    }

    if (event.event_type === 'usdEditVertexSelected') {
        const p = event.payload || {};
        s.setNextClickSelectsVertex?.(false);
        if (p.vertexIndex != null) {
            const info = {
                index: Number(p.vertexIndex),
                x: Number(p.x) || 0,
                y: Number(p.y) || 0,
                z: Number(p.z) || 0,
            };
            s.setSelectedVertexInfo?.(info);

            const mode = s.measureModeRef?.current;
            if (mode === 'pickFirst') {
                s.setMeasurePoint1?.(info);
                if (s.measurePoint1Ref) s.measurePoint1Ref.current = info;
                s.setMeasurePoint2?.(null);
                s.setMeasureResult?.(null);
                s.setMeasureMode?.('pickSecond');
                if (s.measureModeRef) s.measureModeRef.current = 'pickSecond';
                s.setNextClickSelectsVertex?.(true);
            } else if (mode === 'pickSecond') {
                const p1 = s.measurePoint1Ref?.current;
                s.setMeasurePoint2?.(info);
                if (p1) {
                    const dx = info.x - p1.x;
                    const dy = info.y - p1.y;
                    const dz = info.z - p1.z;
                    s.setMeasureResult?.(Math.sqrt(dx * dx + dy * dy + dz * dz));
                    try {
                        sendMessage('usdEdit.highlightVertices', { indices: [p1.index, info.index] });
                        sendMessage('usdEdit.drawMeasureLine', {
                            x1: p1.x, y1: p1.y, z1: p1.z,
                            x2: info.x, y2: info.y, z2: info.z,
                        });
                    } catch {}
                }
                s.setMeasureMode?.('off');
                if (s.measureModeRef) s.measureModeRef.current = 'off';
            }
        }
        return;
    }

    if (event.event_type === 'usdEditTransformUpdate') {
        const p = event.payload || {};
        s.setNextClickSelectsPrim?.(false);
        s.setTransformInfo?.({
            primPath: String(p.primPath || ''),
            primName: String(p.primName || ''),
            x: Number(p.x) || 0,
            y: Number(p.y) || 0,
            z: Number(p.z) || 0,
            rotX: Number(p.rotX) || 0,
            rotY: Number(p.rotY) || 0,
            rotZ: Number(p.rotZ) || 0,
        });
        return;
    }

    if (event.event_type === 'usdEditSaveStatus') {
        const p = event.payload || {};
        s.setUsdEditSaveStatus?.({
            status: String(p.status || ''),
            message: p.message ? String(p.message) : undefined,
        });
        return;
    }

    if (event.event_type === 'usdEditSublayerList') {
        const p = event.payload || {};
        const sublayers = Array.isArray(p.sublayers) ? p.sublayers.map((sub: any) => ({
            identifier: String(sub.identifier || ''),
            displayName: String(sub.displayName || ''),
        })) : [];
        s.setSublayerList?.(sublayers);
        return;
    }

    if (event.event_type === 'usdEditMarkerCreated') {
        s.setMarkerPlacementArmed?.(false);
        s.setUsdEditPhase?.('markerCreated');
        return;
    }

    if (event.event_type === 'usdEditMarkerSelected') {
        const p = event.payload || {};
        s.setSelectedMarkerInfo?.({
            primPath: String(p.primPath || ''),
            primName: String(p.primName || ''),
            x: Number(p.x) || 0,
            y: Number(p.y) || 0,
            z: Number(p.z) || 0,
            rotX: Number(p.rotX) || 0,
            rotY: Number(p.rotY) || 0,
            rotZ: Number(p.rotZ) || 0,
            layerDisplayName: p.layerDisplayName ? String(p.layerDisplayName) : undefined,
        });
        s.setUsdEditPhase?.('markerSelected');
        return;
    }

    if (event.event_type === 'usdEditMarkerRemoved') {
        const p = event.payload || {};
        s.setSelectedMarkerInfo?.(null);
        s.setUsdEditPhase?.('idle');
        const name = String(p.primName || 'Marker');
        const layer = p.layerDisplayName ? String(p.layerDisplayName) : '';
        const msg = layer ? `Removed "${name}" from ${layer}` : `Removed "${name}"`;
        s.setUsdEditSaveStatus?.({ status: 'removed', message: msg });
        return;
    }

    if (event.event_type === 'usdEditMarkerWorldTransform') {
        const p = event.payload || {};
        const err = p.error != null ? String(p.error) : '';
        if (err) {
            s.setUsdEditSaveStatus?.({ status: 'nothing', message: err });
            return;
        }
        const json = typeof p.clipboardJson === 'string' ? p.clipboardJson : '';
        if (!json) {
            s.setUsdEditSaveStatus?.({ status: 'nothing', message: 'No world transform data from Kit' });
            return;
        }
        void (async () => {
            try {
                await navigator.clipboard.writeText(json);
                const kind = String(p.clipKind || '');
                const msg = kind === 'full'
                    ? 'Copied marker JSON (full diagnostic)'
                    : 'Copied marker JSON (essential only)';
                s.setUsdEditSaveStatus?.({
                    status: 'nothing',
                    message: msg,
                });
            } catch {
                s.setUsdEditSaveStatus?.({
                    status: 'nothing',
                    message: 'Clipboard failed — check browser permissions or HTTPS',
                });
            }
        })();
        return;
    }
}
