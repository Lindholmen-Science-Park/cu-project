import React, { useEffect, useState } from 'react';
import { useControl } from '../../streaming/contexts';

const POS_STEP = 1.0;
const POS_LARGE = 10.0;
// Single-tap rotation nudge is 1°. The « / » buttons remain coarse for snapping
// to common angles. For fine values, click the number itself to type directly.
const ROT_STEP = 1.0;
const ROT_LARGE = 45.0;

// ── Styles ───────────────────────────────────────────────────────

const panelStyle: React.CSSProperties = {
    position: 'fixed', bottom: 20, right: 20, minWidth: 280, maxWidth: 340,
    padding: 16, backgroundColor: 'rgba(0,0,0,0.88)',
    border: '1px solid rgba(100,180,255,0.4)', borderRadius: 12,
    backdropFilter: 'blur(14px)', boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
    color: '#fff', fontSize: 13, zIndex: 1500, pointerEvents: 'auto',
    fontFamily: 'Lexend, system-ui, sans-serif',
};

const headerStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 };

const btnBase: React.CSSProperties = {
    padding: '4px 10px', fontSize: 12, fontWeight: 600, color: '#fff',
    backgroundColor: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.2)',
    borderRadius: 6, cursor: 'pointer', transition: 'background-color 0.15s ease',
};

const nudgeBtnStyle: React.CSSProperties = { ...btnBase, padding: '6px 12px', fontSize: 13, fontWeight: 700, minWidth: 36, textAlign: 'center' };

const tabContainerStyle: React.CSSProperties = { display: 'flex', gap: 4, marginBottom: 10 };

const tabStyle = (active: boolean): React.CSSProperties => ({
    ...btnBase, flex: 1, textAlign: 'center', padding: '6px 0',
    backgroundColor: active ? 'rgba(100,180,255,0.35)' : 'rgba(255,255,255,0.08)',
    border: active ? '1px solid rgba(100,180,255,0.6)' : '1px solid rgba(255,255,255,0.15)',
});

const axisRowStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 };
const axisLabelStyle: React.CSSProperties = { width: 18, fontWeight: 700, fontSize: 14, textAlign: 'center' };
const actionBtnStyle: React.CSSProperties = { ...btnBase, flex: 1, padding: '7px 0', fontSize: 12, textAlign: 'center' };
const dividerStyle: React.CSSProperties = { height: 1, backgroundColor: 'rgba(255,255,255,0.1)', margin: '10px 0' };

const meshName = (path: string | null | undefined): string => {
    if (!path) return '?';
    const parts = path.split('/');
    return parts[parts.length - 1] || path;
};

// ── Axis nudge row ──────────────────────────────────────────────

const valueInputStyle: React.CSSProperties = {
    flex: 1,
    minWidth: 0,
    width: '100%',
    textAlign: 'center',
    fontFamily: 'Lexend, system-ui, sans-serif',
    fontSize: 12,
    color: '#e6e6e6',
    backgroundColor: 'rgba(255,255,255,0.06)',
    border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: 4,
    padding: '3px 4px',
    outline: 'none',
    MozAppearance: 'textfield' as React.CSSProperties['MozAppearance'],
};

const AxisRow: React.FC<{
    axis: 'x' | 'y' | 'z'; value: number; smallStep: number; largeStep: number;
    onNudge: (dx: number, dy: number, dz: number) => void; label?: string;
}> = ({ axis, value, smallStep, largeStep, onNudge, label }) => {
    const color = axis === 'x' ? '#ff4444' : axis === 'y' ? '#44cc44' : '#4488ff';
    const d = (v: number) => ({ x: axis === 'x' ? v : 0, y: axis === 'y' ? v : 0, z: axis === 'z' ? v : 0 });

    // Local draft so the user can type freely without React clobbering the
    // input each time Kit pushes back the new value. Synced when `value`
    // changes from the outside (selection / nudge) and the field isn't
    // currently focused.
    const [draft, setDraft] = useState(value.toFixed(1));
    const focusedRef = React.useRef(false);
    useEffect(() => {
        if (!focusedRef.current) setDraft(value.toFixed(1));
    }, [value]);

    const commit = () => {
        const parsed = parseFloat(draft);
        if (!Number.isFinite(parsed)) {
            setDraft(value.toFixed(1));
            return;
        }
        const delta = parsed - value;
        if (Math.abs(delta) < 1e-4) {
            setDraft(value.toFixed(1));
            return;
        }
        const a = d(delta);
        onNudge(a.x, a.y, a.z);
    };

    return (
        <div style={axisRowStyle}>
            <span style={{ ...axisLabelStyle, color }}>{label ?? axis.toUpperCase()}</span>
            <button style={nudgeBtnStyle} onClick={() => { const a = d(-largeStep); onNudge(a.x, a.y, a.z); }}>&laquo;</button>
            <button style={nudgeBtnStyle} onClick={() => { const a = d(-smallStep); onNudge(a.x, a.y, a.z); }}>&lsaquo;</button>
            <input
                type="number"
                step="any"
                className="usd-edit-axis-input"
                style={valueInputStyle}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onFocus={(e) => { focusedRef.current = true; e.target.select(); }}
                onBlur={() => { focusedRef.current = false; commit(); }}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') { (e.target as HTMLInputElement).blur(); }
                    else if (e.key === 'Escape') {
                        setDraft(value.toFixed(1));
                        (e.target as HTMLInputElement).blur();
                    }
                }}
            />
            <button style={nudgeBtnStyle} onClick={() => { const a = d(smallStep); onNudge(a.x, a.y, a.z); }}>&rsaquo;</button>
            <button style={nudgeBtnStyle} onClick={() => { const a = d(largeStep); onNudge(a.x, a.y, a.z); }}>&raquo;</button>
        </div>
    );
};

// ── Main panel ──────────────────────────────────────────────────

const selectStyle: React.CSSProperties = {
    width: '100%', padding: '6px 8px', fontSize: 12, fontFamily: 'Lexend, system-ui, sans-serif',
    backgroundColor: '#1e1e1e', color: '#fff',
    border: '1px solid rgba(255,255,255,0.2)', borderRadius: 6,
    outline: 'none', marginBottom: 8,
};

const optionStyle: React.CSSProperties = {
    backgroundColor: '#1e1e1e', color: '#fff',
};

const inputStyle: React.CSSProperties = {
    ...selectStyle, marginBottom: 8,
};

const checkboxRowStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, cursor: 'pointer',
};

const pickBtnStyle = (armed: boolean): React.CSSProperties => ({
    ...btnBase, padding: '6px 0', fontSize: 12, textAlign: 'center', width: '100%', marginBottom: 6,
    backgroundColor: armed ? 'rgba(100,180,255,0.4)' : 'rgba(255,255,255,0.12)',
    border: armed ? '1px solid rgba(100,180,255,0.7)' : '1px solid rgba(255,255,255,0.2)',
});

const UsdEditPanel: React.FC = () => {
    const ctrl = useControl();

    const subMode = ctrl.usdEditSubMode;
    const phase = ctrl.usdEditPhase;
    const onSubModeChange = ctrl.handleUsdEditSubModeChange;
    const meshPath = ctrl.editingMeshPath;
    const vertexCount = ctrl.editingVertexCount ?? 0;
    const selectedVertex = ctrl.selectedVertexInfo;
    const transformInfo = ctrl.transformInfo;
    const saveStatus = ctrl.usdEditSaveStatus;
    const onVertexNudge = ctrl.handleVertexEditNudge;
    const onTranslateNudge = ctrl.handleTransformNudgeTranslate;
    const onRotateNudge = ctrl.handleTransformNudgeRotate;
    const onSelectVertexClick = ctrl.handleSelectVertexClick;
    const nextClickSelectsVertex = ctrl.nextClickSelectsVertex;
    const vertexDragEnabled = ctrl.vertexDragEnabled;
    const onVertexDragToggle = () => ctrl.setVertexDragEnabled(v => !v);
    const measureMode = ctrl.measureMode ?? 'off';
    const measurePoint1 = ctrl.measurePoint1;
    const measurePoint2 = ctrl.measurePoint2;
    const measureResult = ctrl.measureResult;
    const onMeasureDistanceClick = ctrl.handleMeasureDistanceClick;
    const onSelectPrimClick = ctrl.handleSelectPrimClick;
    const nextClickSelectsPrim = ctrl.nextClickSelectsPrim;
    const onSave = ctrl.handleUsdEditSave;
    const onResetSession = ctrl.handleUsdEditResetSession;
    const onHardReset = ctrl.handleUsdEditHardReset;
    const onExit = ctrl.handleUsdEditToggle;
    const sublayerList = ctrl.sublayerList ?? [];
    const selectedSublayer = ctrl.selectedSublayer ?? '';
    const onSelectedSublayerChange = ctrl.setSelectedSublayer;
    const markerName = ctrl.markerName ?? '';
    const onMarkerNameChange = ctrl.setMarkerName;
    const showMarkers = ctrl.showMarkers ?? false;
    const onShowMarkersToggle = ctrl.handleShowMarkersToggle;
    const markerPlacementArmed = ctrl.markerPlacementArmed ?? false;
    const onArmMarkerPlacement = ctrl.handleArmMarkerPlacement;
    const selectedMarkerInfo = ctrl.selectedMarkerInfo;
    const onMarkerNudgeTranslate = ctrl.handleMarkerNudgeTranslate;
    const onMarkerNudgeRotate = ctrl.handleMarkerNudgeRotate;
    const editOriginalLayer = ctrl.editOriginalLayer ?? false;
    const onEditOriginalLayerChange = ctrl.setEditOriginalLayer;
    const onRemoveMarker = ctrl.handleRemoveMarker;
    const onCopyMarkerWorldTransform = ctrl.handleCopyMarkerWorldTransform;
    const markerCopyIncludeFullDiagnostic = ctrl.markerCopyIncludeFullDiagnostic ?? false;
    const setMarkerCopyIncludeFullDiagnostic = ctrl.setMarkerCopyIncludeFullDiagnostic;

    const [statusMessage, setStatusMessage] = useState<string | null>(null);
    const [confirmingRemove, setConfirmingRemove] = useState(false);

    useEffect(() => {
        if (saveStatus?.message) {
            setStatusMessage(saveStatus.message);
            const timer = window.setTimeout(() => setStatusMessage(null), 4000);
            return () => window.clearTimeout(timer);
        }
    }, [saveStatus]);

    useEffect(() => { setConfirmingRemove(false); }, [selectedMarkerInfo?.primPath]);

    useEffect(() => {
        if (!confirmingRemove) return;
        const timer = window.setTimeout(() => setConfirmingRemove(false), 4000);
        return () => window.clearTimeout(timer);
    }, [confirmingRemove]);

    return (
        <div style={panelStyle}>
            {/* Hide the native number-input spinner buttons inside this panel
                only — they're tiny, easy to mis-click, and confuse the user
                with our custom « / < / > / » nudge buttons. */}
            <style>{`
                .usd-edit-axis-input::-webkit-outer-spin-button,
                .usd-edit-axis-input::-webkit-inner-spin-button {
                    -webkit-appearance: none;
                    margin: 0;
                }
            `}</style>

            {/* Header */}
            <div style={headerStyle}>
                <span style={{ fontWeight: 700, fontSize: 14 }}>USD Editing</span>
                <button style={{ ...btnBase, backgroundColor: 'rgba(200,60,60,0.7)', border: '1px solid rgba(255,80,80,0.5)' }} onClick={onExit}>Exit</button>
            </div>

            {/* Mode tabs */}
            <div style={tabContainerStyle}>
                <button style={tabStyle(subMode === 'transform')} onClick={() => onSubModeChange('transform')}>Transform</button>
                <button style={tabStyle(subMode === 'vertices')} onClick={() => onSubModeChange('vertices')}>Vertices</button>
                <button style={tabStyle(subMode === 'markers')} onClick={() => onSubModeChange('markers')}>Markers</button>
            </div>

            {/* ── Transform mode ── */}
            {subMode === 'transform' && (
                <>
                    {(phase === 'selectPrim') && (
                        <div style={{ color: '#b3b3b3' }}>Click a prim in the scene to select it.</div>
                    )}

                    {transformInfo && (
                        <div>
                            <div style={{ marginBottom: 8, color: '#b3b3b3' }}>
                                <strong style={{ color: '#6bb8ff' }}>{transformInfo.primName}</strong>
                            </div>

                            <button style={pickBtnStyle(nextClickSelectsPrim)} onClick={onSelectPrimClick}>
                                {nextClickSelectsPrim ? 'Click a prim\u2026' : 'Pick Prim'}
                            </button>

                            <div style={{ marginBottom: 6, fontSize: 11, color: '#808080', textTransform: 'uppercase', letterSpacing: 1 }}>Position</div>
                            <AxisRow axis="x" value={transformInfo.x} smallStep={POS_STEP} largeStep={POS_LARGE} onNudge={onTranslateNudge} />
                            <AxisRow axis="y" value={transformInfo.y} smallStep={POS_STEP} largeStep={POS_LARGE} onNudge={onTranslateNudge} />
                            <AxisRow axis="z" value={transformInfo.z} smallStep={POS_STEP} largeStep={POS_LARGE} onNudge={onTranslateNudge} />

                            <div style={{ marginTop: 8, marginBottom: 6, fontSize: 11, color: '#808080', textTransform: 'uppercase', letterSpacing: 1 }}>Rotation</div>
                            <AxisRow axis="x" value={transformInfo.rotX} smallStep={ROT_STEP} largeStep={ROT_LARGE} onNudge={onRotateNudge} />
                            <AxisRow axis="y" value={transformInfo.rotY} smallStep={ROT_STEP} largeStep={ROT_LARGE} onNudge={onRotateNudge} />
                            <AxisRow axis="z" value={transformInfo.rotZ} smallStep={ROT_STEP} largeStep={ROT_LARGE} onNudge={onRotateNudge} />
                        </div>
                    )}
                </>
            )}

            {/* ── Vertices mode ── */}
            {subMode === 'vertices' && (
                <>
                    {phase === 'selectMesh' && (
                        <div style={{ color: '#b3b3b3' }}>Click a mesh in the scene to view its vertices.</div>
                    )}

                    {(phase === 'selectVertex') && (
                        <>
                            <div style={{ marginBottom: 8, color: '#b3b3b3' }}>
                                <strong style={{ color: '#6bb8ff' }}>{meshName(meshPath)}</strong>
                                {' '}&mdash; {vertexCount} vertices
                            </div>

                            <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
                                <button
                                    style={{
                                        ...btnBase, flex: 1, padding: '6px 0', fontSize: 12, textAlign: 'center',
                                        backgroundColor: (nextClickSelectsVertex && measureMode === 'off') ? 'rgba(100,180,255,0.4)' : 'rgba(255,255,255,0.12)',
                                        border: (nextClickSelectsVertex && measureMode === 'off') ? '1px solid rgba(100,180,255,0.7)' : '1px solid rgba(255,255,255,0.2)',
                                    }}
                                    onClick={onSelectVertexClick}
                                >
                                    {(nextClickSelectsVertex && measureMode === 'off') ? 'Click a vertex\u2026' : 'Pick Vertex'}
                                </button>
                                <button
                                    style={{
                                        ...btnBase, flex: 1, padding: '6px 0', fontSize: 12, textAlign: 'center',
                                        backgroundColor: measureMode !== 'off' ? 'rgba(255,180,30,0.4)' : 'rgba(255,255,255,0.12)',
                                        border: measureMode !== 'off' ? '1px solid rgba(255,200,50,0.7)' : '1px solid rgba(255,255,255,0.2)',
                                    }}
                                    onClick={onMeasureDistanceClick}
                                >
                                    {measureMode === 'pickFirst' ? 'Click 1st point\u2026'
                                        : measureMode === 'pickSecond' ? 'Click 2nd point\u2026'
                                        : 'Measure'}
                                </button>
                            </div>

                            {measureResult != null && measurePoint1 && measurePoint2 && (
                                <div style={{
                                    marginBottom: 8, padding: '8px 10px',
                                    backgroundColor: 'rgba(255,180,30,0.12)',
                                    border: '1px solid rgba(255,200,50,0.3)',
                                    borderRadius: 6, fontSize: 12, color: '#e6e6e6',
                                }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                        <span style={{ color: '#b3b3b3', fontSize: 11 }}>
                                            #{measurePoint1.index} &rarr; #{measurePoint2.index}
                                        </span>
                                        <button
                                            style={{
                                                ...btnBase, padding: '2px 8px', fontSize: 10,
                                                backgroundColor: 'rgba(255,255,255,0.08)',
                                                border: '1px solid rgba(255,255,255,0.15)',
                                            }}
                                            onClick={onMeasureDistanceClick}
                                        >Clear</button>
                                    </div>
                                    <div style={{ fontSize: 16, fontWeight: 700, color: '#ffcc44' }}>
                                        {measureResult.toFixed(2)} cm
                                    </div>
                                </div>
                            )}

                            {selectedVertex && (
                                <div>
                                    <div style={{ marginBottom: 8, color: '#cccccc' }}>
                                        Vertex <strong style={{ color: '#ff6b6b' }}>#{selectedVertex.index}</strong>
                                    </div>
                                    <AxisRow axis="x" value={selectedVertex.x} smallStep={POS_STEP} largeStep={POS_LARGE} onNudge={onVertexNudge} />
                                    <AxisRow axis="y" value={selectedVertex.y} smallStep={POS_STEP} largeStep={POS_LARGE} onNudge={onVertexNudge} />
                                    <AxisRow axis="z" value={selectedVertex.z} smallStep={POS_STEP} largeStep={POS_LARGE} onNudge={onVertexNudge} />

                                    <button style={pickBtnStyle(vertexDragEnabled)} onClick={onVertexDragToggle}>
                                        {vertexDragEnabled ? 'Drag to Move: ON' : 'Drag to Move: OFF'}
                                    </button>
                                </div>
                            )}
                        </>
                    )}
                </>
            )}

            {/* ── Markers mode ── */}
            {subMode === 'markers' && (
                <>
                    <div style={{ marginBottom: 6, fontSize: 11, color: '#808080', textTransform: 'uppercase', letterSpacing: 1 }}>Create Marker</div>

                    <select
                        style={selectStyle}
                        value={selectedSublayer}
                        onChange={(e) => onSelectedSublayerChange?.(e.target.value)}
                    >
                        <option value="" style={optionStyle}>Select sublayer...</option>
                        {sublayerList.map((s) => (
                            <option key={s.identifier} value={s.identifier} style={optionStyle}>{s.displayName}</option>
                        ))}
                    </select>

                    <input
                        type="text"
                        style={inputStyle}
                        placeholder="Marker name"
                        value={markerName}
                        onChange={(e) => onMarkerNameChange?.(e.target.value)}
                    />

                    <button
                        style={{
                            ...btnBase, width: '100%', padding: '8px 0', textAlign: 'center', marginBottom: 10,
                            backgroundColor: markerPlacementArmed
                                ? 'rgba(255,180,30,0.6)'
                                : 'rgba(50,160,80,0.6)',
                            border: markerPlacementArmed
                                ? '1px solid rgba(255,200,50,0.7)'
                                : '1px solid rgba(80,200,110,0.5)',
                        }}
                        onClick={onArmMarkerPlacement}
                        disabled={!selectedSublayer || !markerName.trim()}
                    >
                        {markerPlacementArmed ? 'Click scene to place...' : 'Place Marker'}
                    </button>

                    {phase === 'markerCreated' && (
                        <div style={{ marginBottom: 8, padding: '6px 10px', backgroundColor: 'rgba(50,200,80,0.15)', borderRadius: 6, fontSize: 12, color: '#d9d9d9', textAlign: 'center' }}>
                            Marker created
                        </div>
                    )}

                    <div style={dividerStyle} />

                    <label style={checkboxRowStyle} onClick={onShowMarkersToggle}>
                        <input
                            type="checkbox"
                            checked={showMarkers}
                            onChange={() => {}}
                            style={{ accentColor: '#6bb8ff', width: 16, height: 16 }}
                        />
                        <span style={{ fontSize: 13, color: '#d9d9d9' }}>Show Markers</span>
                    </label>

                    {selectedMarkerInfo && (
                        <div>
                            <div style={{ marginBottom: 4, color: '#b3b3b3' }}>
                                <strong style={{ color: '#6bb8ff' }}>{selectedMarkerInfo.primName}</strong>
                            </div>
                            {selectedMarkerInfo.layerDisplayName && (
                                <div style={{ marginBottom: 8, fontSize: 11, color: '#737373' }}>
                                    Layer: <span style={{ color: '#b3b3b3' }}>{selectedMarkerInfo.layerDisplayName}</span>
                                </div>
                            )}

                            <label style={{ ...checkboxRowStyle, marginBottom: 10 }} onClick={() => onEditOriginalLayerChange?.(!editOriginalLayer)}>
                                <input
                                    type="checkbox"
                                    checked={editOriginalLayer}
                                    onChange={() => {}}
                                    style={{ accentColor: '#ff9944', width: 16, height: 16 }}
                                />
                                <span style={{ fontSize: 12, color: '#d9d9d9' }}>
                                    Edit original layer
                                </span>
                            </label>
                            <div style={{ marginBottom: 4, fontSize: 10, color: editOriginalLayer ? '#ffa032' : '#8c8c8c', fontStyle: 'italic' }}>
                                {editOriginalLayer
                                    ? `Saving to ${selectedMarkerInfo.layerDisplayName || 'original layer'}`
                                    : 'Saving to usd_edits (session)'}
                            </div>

                            <div style={{ marginTop: 6, marginBottom: 6, fontSize: 11, color: '#808080', textTransform: 'uppercase', letterSpacing: 1 }}>Position</div>
                            <AxisRow axis="x" value={selectedMarkerInfo.x} smallStep={POS_STEP} largeStep={POS_LARGE} onNudge={onMarkerNudgeTranslate ?? (() => {})} />
                            <AxisRow axis="y" value={selectedMarkerInfo.y} smallStep={POS_STEP} largeStep={POS_LARGE} onNudge={onMarkerNudgeTranslate ?? (() => {})} />
                            <AxisRow axis="z" value={selectedMarkerInfo.z} smallStep={POS_STEP} largeStep={POS_LARGE} onNudge={onMarkerNudgeTranslate ?? (() => {})} />

                            <div style={{ marginTop: 8, marginBottom: 6, fontSize: 11, color: '#808080', textTransform: 'uppercase', letterSpacing: 1 }}>Rotation</div>
                            <AxisRow axis="x" value={selectedMarkerInfo.rotX} smallStep={ROT_STEP} largeStep={ROT_LARGE} onNudge={onMarkerNudgeRotate ?? (() => {})} />
                            <AxisRow axis="y" value={selectedMarkerInfo.rotY} smallStep={ROT_STEP} largeStep={ROT_LARGE} onNudge={onMarkerNudgeRotate ?? (() => {})} />

                            <div style={{ marginTop: 10 }}>
                                <button
                                    type="button"
                                    style={{ ...actionBtnStyle, marginBottom: 6 }}
                                    onClick={() => onCopyMarkerWorldTransform?.()}
                                    title={
                                        markerCopyIncludeFullDiagnostic
                                            ? 'Copy nested JSON (essential + full: matrix, quaternion, notes)'
                                            : 'Copy flat JSON: prim, location, rotationDegWorld (composed scene only)'
                                    }
                                    aria-label={
                                        markerCopyIncludeFullDiagnostic
                                            ? 'Copy marker transform JSON including full diagnostic'
                                            : 'Copy marker pose JSON: world location and world rotation only'
                                    }
                                >
                                    Copy transform JSON
                                </button>
                                <label
                                    htmlFor="usd-edit-marker-copy-full"
                                    style={{
                                        ...checkboxRowStyle,
                                        marginBottom: 8,
                                        minHeight: 44,
                                        paddingTop: 4,
                                        paddingBottom: 4,
                                        boxSizing: 'border-box',
                                    }}
                                >
                                    <input
                                        id="usd-edit-marker-copy-full"
                                        type="checkbox"
                                        checked={markerCopyIncludeFullDiagnostic}
                                        onChange={(e) => setMarkerCopyIncludeFullDiagnostic?.(e.target.checked)}
                                        style={{ accentColor: '#6bb8ff', width: 18, height: 18, flexShrink: 0 }}
                                    />
                                    <span style={{ fontSize: 12, color: '#d9d9d9', lineHeight: 1.35 }}>
                                        Include full diagnostic (matrix, quaternion, notes)
                                    </span>
                                </label>
                                <button
                                    type="button"
                                    style={{
                                        ...btnBase, width: '100%', padding: '7px 0', fontSize: 12, textAlign: 'center',
                                        backgroundColor: confirmingRemove ? 'rgba(220,50,50,0.7)' : 'rgba(180,50,50,0.4)',
                                        border: confirmingRemove ? '1px solid rgba(255,80,80,0.8)' : '1px solid rgba(220,70,70,0.4)',
                                    }}
                                    onClick={() => {
                                        if (confirmingRemove) {
                                            onRemoveMarker?.();
                                            setConfirmingRemove(false);
                                        } else {
                                            setConfirmingRemove(true);
                                        }
                                    }}
                                >
                                    {confirmingRemove ? 'Click again to confirm removal' : 'Remove Marker'}
                                </button>
                                {confirmingRemove && (
                                    <div style={{ marginTop: 4, fontSize: 10, color: '#ff6666', textAlign: 'center' }}>
                                        This will delete from {selectedMarkerInfo.layerDisplayName || 'its layer'}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </>
            )}

            {/* Save / Reset controls */}
            <div style={dividerStyle} />
            <div style={{ display: 'flex', gap: 6 }}>
                <button style={{ ...actionBtnStyle, backgroundColor: 'rgba(50,160,80,0.6)', border: '1px solid rgba(80,200,110,0.5)' }} onClick={onSave} title="Save edits to persistent sublayer">Save</button>
                <button style={{ ...actionBtnStyle, backgroundColor: 'rgba(180,140,30,0.5)', border: '1px solid rgba(220,180,50,0.5)' }} onClick={onResetSession} title="Revert this session's edits">Reset Session</button>
                <button style={{ ...actionBtnStyle, backgroundColor: 'rgba(180,50,50,0.5)', border: '1px solid rgba(220,70,70,0.5)' }} onClick={onHardReset} title="Clear ALL saved edits">Hard Reset</button>
            </div>

            {statusMessage && (
                <div style={{ marginTop: 8, padding: '6px 10px', backgroundColor: 'rgba(100,180,255,0.15)', borderRadius: 6, fontSize: 12, color: '#d9d9d9', textAlign: 'center' }}>
                    {statusMessage}
                </div>
            )}
        </div>
    );
};

export default UsdEditPanel;
