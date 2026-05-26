import React from 'react';
import { useControl, useAppUI } from '../contexts';

const INCIDENT_SIZES = [['1x1', '1\u00D71m'], ['2x2', '2\u00D72m'], ['2x1', '2\u00D71m']] as const;
const INCIDENT_SHAPES = [['cube', '\u25A0 Cube'], ['cone', '\u25B2 Cone'], ['torus', '\u25CB Torus']] as const;

const PlacementButtons: React.FC = () => {
    const appUI = useAppUI();
    const ctrl = useControl();

    if (appUI.isViewer || appUI.seatArrivalCelebrationVisible || appUI.poiArrivalVisible) return null;

    const {
        markerPlacementEnabled,
        nextClickPlacesMarker,
        handleAddMarkerClick,
        incidentPlacementEnabled,
        nextClickPlacesIncident,
        handleAddIncidentClick,
        incidentSizePreset,
        setIncidentSizePreset,
        incidentShape,
        setIncidentShape,
        cameraPlacementEnabled = false,
        nextClickPlacesCamera = false,
        handleAddCameraClick,
    } = ctrl;

    if (!markerPlacementEnabled && !incidentPlacementEnabled && !cameraPlacementEnabled) return null;

    return (
        <div style={{
            position: 'fixed',
            top: 20,
            right: 20,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            zIndex: 1500,
            pointerEvents: 'auto',
        }}>
            {markerPlacementEnabled && (
                <button
                    type="button"
                    onClick={handleAddMarkerClick}
                    style={{
                        padding: '10px 18px',
                        fontSize: 14,
                        fontWeight: 600,
                        color: '#fff',
                        backgroundColor: nextClickPlacesMarker ? 'rgba(118, 185, 0, 0.85)' : 'rgba(0, 0, 0, 0.85)',
                        border: nextClickPlacesMarker ? '2px solid #76b900' : '1px solid rgba(255,255,255,0.25)',
                        borderRadius: 10,
                        cursor: 'pointer',
                        backdropFilter: 'blur(12px)',
                        boxShadow: nextClickPlacesMarker ? '0 0 16px rgba(118,185,0,0.5)' : '0 4px 16px rgba(0,0,0,0.4)',
                        transition: 'all 0.2s ease',
                    }}
                >
                    {nextClickPlacesMarker ? '\uD83D\uDCCD Click ground to place marker' : '\uD83D\uDCCD Add marker'}
                </button>
            )}
            {incidentPlacementEnabled && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <button
                        type="button"
                        onClick={handleAddIncidentClick}
                        style={{
                            padding: '10px 18px',
                            fontSize: 14,
                            fontWeight: 600,
                            color: '#fff',
                            backgroundColor: nextClickPlacesIncident ? 'rgba(230, 140, 0, 0.85)' : 'rgba(0, 0, 0, 0.85)',
                            border: nextClickPlacesIncident ? '2px solid #e68c00' : '1px solid rgba(255,200,100,0.5)',
                            borderRadius: 10,
                            cursor: 'pointer',
                            backdropFilter: 'blur(12px)',
                            boxShadow: nextClickPlacesIncident ? '0 0 16px rgba(230,140,0,0.5)' : '0 4px 16px rgba(0,0,0,0.4)',
                            transition: 'all 0.2s ease',
                        }}
                    >
                        {nextClickPlacesIncident ? '\uD83D\uDEA7 Click ground to place incident' : '\uD83D\uDEA7 Add incident'}
                    </button>
                    <div style={{ display: 'flex', gap: 4 }}>
                        {INCIDENT_SHAPES.map(([key, label]) => (
                            <button
                                key={key}
                                type="button"
                                onClick={() => setIncidentShape(key as 'cube' | 'cone' | 'torus')}
                                style={{
                                    flex: 1,
                                    padding: '5px 0',
                                    fontSize: 12,
                                    fontWeight: incidentShape === key ? 700 : 500,
                                    color: '#fff',
                                    backgroundColor: incidentShape === key ? 'rgba(230, 140, 0, 0.7)' : 'rgba(0, 0, 0, 0.7)',
                                    border: incidentShape === key ? '1px solid #e68c00' : '1px solid rgba(255,255,255,0.15)',
                                    borderRadius: 6,
                                    cursor: 'pointer',
                                    transition: 'all 0.15s ease',
                                }}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                    <div style={{ display: 'flex', gap: 4 }}>
                        {INCIDENT_SIZES.map(([key, label]) => (
                            <button
                                key={key}
                                type="button"
                                onClick={() => setIncidentSizePreset(key as '1x1' | '2x2' | '2x1')}
                                style={{
                                    flex: 1,
                                    padding: '5px 0',
                                    fontSize: 12,
                                    fontWeight: incidentSizePreset === key ? 700 : 500,
                                    color: '#fff',
                                    backgroundColor: incidentSizePreset === key ? 'rgba(230, 140, 0, 0.7)' : 'rgba(0, 0, 0, 0.7)',
                                    border: incidentSizePreset === key ? '1px solid #e68c00' : '1px solid rgba(255,255,255,0.15)',
                                    borderRadius: 6,
                                    cursor: 'pointer',
                                    transition: 'all 0.15s ease',
                                }}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                </div>
            )}
            {cameraPlacementEnabled && handleAddCameraClick && (
                <button
                    type="button"
                    onClick={handleAddCameraClick}
                    style={{
                        padding: '10px 18px',
                        fontSize: 14,
                        fontWeight: 600,
                        color: '#fff',
                        backgroundColor: nextClickPlacesCamera ? 'rgba(0, 120, 215, 0.85)' : 'rgba(0, 0, 0, 0.85)',
                        border: nextClickPlacesCamera ? '2px solid #0078d7' : '1px solid rgba(100,180,255,0.5)',
                        borderRadius: 10,
                        cursor: 'pointer',
                        backdropFilter: 'blur(12px)',
                        boxShadow: nextClickPlacesCamera ? '0 0 16px rgba(0,120,215,0.5)' : '0 4px 16px rgba(0,0,0,0.4)',
                        transition: 'all 0.2s ease',
                    }}
                >
                    {nextClickPlacesCamera ? 'Click to place camera' : 'Add camera'}
                </button>
            )}
        </div>
    );
};

export default PlacementButtons;
