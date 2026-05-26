import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { sendMessage, FIXED_CAMERAS } from '../../../streaming/messaging';
import { useEnvironment, useControl, useAppUI } from '../../../streaming/contexts';
import { LENS_PRESETS, ZOOM_STEP } from './types';

interface Props {
    fixedCameras?: { id: string; label: string }[];
}

const FixedCameraBar: React.FC<Props> = ({ fixedCameras: fixedCamerasProp }) => {
    const env = useEnvironment();
    const ctrl = useControl();
    const appUI = useAppUI();
    const viewportCaptureStatus = appUI.viewportCaptureStatus;
    const computedFixedCameras = useMemo(() => [...FIXED_CAMERAS, ...env.placedCameras], [env.placedCameras]);
    const fixedCameras = fixedCamerasProp ?? computedFixedCameras;

    const activeFixedCamera = env.activeFixedCamera;
    const placedCameras = env.placedCameras ?? [];
    const onRemovePlacedCamera = env.handleRemovePlacedCamera;
    const cameraAreaCubesVisible = env.cameraAreaCubesVisible;
    const onCameraAreaCubesToggle = env.handleCameraAreaCubesToggle;

    const onFixedCameraChange = useCallback(
        (cameraId: string | null) => env.handleFixedCameraChange(cameraId, ctrl.controlMode),
        [env.handleFixedCameraChange, ctrl.controlMode],
    );

    const isPlacedCamera = !!(activeFixedCamera && activeFixedCamera.startsWith('placed_cam_'));
    const [capturePopupOpen, setCapturePopupOpen] = useState(false);
    const [currentFocalLength, setCurrentFocalLength] = useState(12);
    const prevCameraRef = useRef(activeFixedCamera);

    useEffect(() => {
        if (activeFixedCamera !== prevCameraRef.current) {
            prevCameraRef.current = activeFixedCamera;
            if (activeFixedCamera && activeFixedCamera.startsWith('placed_cam_')) {
                setCurrentFocalLength(12);
            }
        }
    }, [activeFixedCamera]);

    const handleLensChange = useCallback((focalLength: number) => {
        const clamped = Math.max(4, Math.min(200, focalLength));
        setCurrentFocalLength(clamped);
        if (activeFixedCamera) {
            sendMessage('placedCameraLens', { cameraId: activeFixedCamera, focalLength: clamped });
        }
    }, [activeFixedCamera]);

    const doSnapshotCapture = useCallback((filePrefix = 'snapshot') => {
        const video = document.getElementById('remote-video') as HTMLVideoElement | null;
        if (!video || video.readyState < 2) return;
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        ctx.drawImage(video, 0, 0);
        const link = document.createElement('a');
        link.download = `${filePrefix}_${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
    }, []);

    const doRenderedCapture = useCallback(() => {
        sendMessage('viewportCaptureRequest', { format: 'jpeg' });
    }, []);

    useEffect(() => {
        if (!capturePopupOpen) return;
        const close = () => setCapturePopupOpen(false);
        const timer = setTimeout(() => document.addEventListener('pointerdown', close, { once: true }), 0);
        return () => { clearTimeout(timer); document.removeEventListener('pointerdown', close); };
    }, [capturePopupOpen]);

    if (!activeFixedCamera || activeFixedCamera === '') return null;

    return (
        <>
            {/* Prev / Next / Back bar */}
            {fixedCameras.length > 0 && (
                <div className="fixed-camera-bar">
                    <button
                        type="button"
                        className="fixed-camera-bar-btn"
                        onClick={() => {
                            const idx = fixedCameras.findIndex((c) => c.id === activeFixedCamera);
                            const prevIdx = idx <= 0 ? fixedCameras.length - 1 : idx - 1;
                            onFixedCameraChange(fixedCameras[prevIdx].id);
                        }}
                        title="Previous camera"
                    >
                        ‹ Prev
                    </button>
                    <span className="fixed-camera-bar-label">
                        {fixedCameras.find((c) => c.id === activeFixedCamera)?.label ?? activeFixedCamera}
                    </span>
                    <button
                        type="button"
                        className="fixed-camera-bar-btn"
                        onClick={() => {
                            const idx = fixedCameras.findIndex((c) => c.id === activeFixedCamera);
                            const nextIdx = idx < 0 || idx >= fixedCameras.length - 1 ? 0 : idx + 1;
                            onFixedCameraChange(fixedCameras[nextIdx].id);
                        }}
                        title="Next camera"
                    >
                        Next ›
                    </button>
                    {onCameraAreaCubesToggle && (
                        <button
                            type="button"
                            className={`fixed-camera-bar-btn ${cameraAreaCubesVisible ? 'active' : ''}`}
                            onClick={onCameraAreaCubesToggle}
                            title={cameraAreaCubesVisible ? 'Hide camera coverage areas' : 'Show camera coverage areas'}
                        >
                            {cameraAreaCubesVisible ? 'Hide areas' : 'Show areas'}
                        </button>
                    )}
                    <button
                        type="button"
                        className="fixed-camera-bar-btn fixed-camera-bar-back"
                        onClick={() => onFixedCameraChange(null)}
                        title="Back to first person"
                    >
                        Back to first person
                    </button>
                </div>
            )}

            {/* Lens controls — placed camera only */}
            {isPlacedCamera && (
                <div className="fixed-camera-bar" style={{ top: 'auto', bottom: 60, gap: 6 }}>
                    <button
                        type="button"
                        className="fixed-camera-bar-btn"
                        onClick={() => handleLensChange(currentFocalLength - ZOOM_STEP)}
                        title="Zoom out (wider)"
                        style={{ fontWeight: 700, fontSize: 16, padding: '4px 12px' }}
                    >
                        &minus;
                    </button>
                    {LENS_PRESETS.map((p) => (
                        <button
                            key={p.label}
                            type="button"
                            className={`fixed-camera-bar-btn ${currentFocalLength === p.focalLength ? 'active' : ''}`}
                            onClick={() => handleLensChange(p.focalLength)}
                            title={`${p.focalLength}mm`}
                        >
                            {p.label}
                        </button>
                    ))}
                    <button
                        type="button"
                        className="fixed-camera-bar-btn"
                        onClick={() => handleLensChange(currentFocalLength + ZOOM_STEP)}
                        title="Zoom in (tighter)"
                        style={{ fontWeight: 700, fontSize: 16, padding: '4px 12px' }}
                    >
                        +
                    </button>
                    <span style={{ fontSize: 12, color: '#b3b3b3', minWidth: 44, textAlign: 'center' }}>
                        {currentFocalLength}mm
                    </span>
                    <div style={{ width: 1, height: 20, background: 'rgba(255,255,255,0.2)', margin: '0 2px' }} />
                    <div style={{ position: 'relative' }}>
                        <button
                            type="button"
                            className={`fixed-camera-bar-btn ${capturePopupOpen ? 'active' : ''}`}
                            onClick={() => setCapturePopupOpen(prev => !prev)}
                            title="Capture viewport"
                            style={{ padding: '4px 12px' }}
                        >
                            {viewportCaptureStatus === 'capturing' ? '⏳' : '📸'} Capture
                        </button>
                        {capturePopupOpen && (
                            <div
                                onPointerDown={(e) => e.stopPropagation()}
                                style={{
                                    position: 'absolute', bottom: '100%', left: '50%', transform: 'translateX(-50%)',
                                    marginBottom: 8, display: 'flex', gap: 4, padding: 6,
                                    background: 'rgba(0,0,0,0.9)', borderRadius: 10, border: '1px solid rgba(255,255,255,0.2)',
                                    backdropFilter: 'blur(12px)', boxShadow: '0 8px 24px rgba(0,0,0,0.6)', whiteSpace: 'nowrap',
                                }}
                            >
                                <button
                                    type="button"
                                    className="fixed-camera-bar-btn"
                                    style={{ padding: '6px 14px', fontSize: 13 }}
                                    onClick={() => {
                                        const camLabel = placedCameras.find(c => c.id === activeFixedCamera)?.label ?? 'camera';
                                        doSnapshotCapture(`${camLabel}_${currentFocalLength}mm`);
                                        setCapturePopupOpen(false);
                                    }}
                                    title="Instant capture from stream"
                                >
                                    📷 Snapshot
                                </button>
                                <button
                                    type="button"
                                    className="fixed-camera-bar-btn"
                                    style={{ padding: '6px 14px', fontSize: 13 }}
                                    disabled={viewportCaptureStatus === 'capturing'}
                                    onClick={() => { doRenderedCapture(); setCapturePopupOpen(false); }}
                                    title="Full GPU quality from Kit"
                                >
                                    {viewportCaptureStatus === 'capturing' ? '⏳ Rendering...' : '🎨 Rendered'}
                                </button>
                            </div>
                        )}
                    </div>
                    {onRemovePlacedCamera && activeFixedCamera && (
                        <button
                            type="button"
                            className="fixed-camera-bar-btn"
                            onClick={() => { onRemovePlacedCamera(activeFixedCamera); onFixedCameraChange(null); }}
                            title="Remove this camera"
                            style={{ color: '#ff5555', fontWeight: 600, padding: '4px 12px' }}
                        >
                            Remove
                        </button>
                    )}
                </div>
            )}
        </>
    );
};

export default FixedCameraBar;
