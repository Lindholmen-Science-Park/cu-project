import { useState, useCallback, useRef, useEffect } from 'react';
import { sendMessage } from '../messaging';
import { ControlMode, type TransitLiveOverlayStatusState } from '../types';

// Seated-crowd density variants the master "Display crowd" toggle drives.
// Mirrors the Kit-side `SEATED_CROWD_DEFAULT_VARIANT` constant in
// `younite.people_toggle_extension/extension.py`. The authored default
// in `Instances/seated_people.usda` is `none` (invisible on stage open),
// so the toggle starts OFF and the user opts in.
const SEATED_CROWD_ON_VARIANT = 'dense';
const SEATED_CROWD_OFF_VARIANT = 'none';
import { UiInteractionBoxesUpdate } from '../overlays/interactionBoxes/InteractionBoxesOverlay';
import { AvatarChatConfig } from '../overlays/avatarChat/AvatarChatOverlay';
import { VideoConfig } from '../overlays/videoPlayer/VideoPlayerOverlay';
import type { VideoBookEntry } from '../../cu/videobook/VideoBookOverlay';

export interface CoinPoiPayload {
    poiType: string;
    xformId: string;
    coinType: string;
    primPath?: string;
    displayName?: string;
    labelIcon?: string;
    metadata?: Record<string, unknown>;
}
import type { KitRegistryItem } from '../../dev/mediaAdmin/mediaRegistryUtils';
import type { IotAirQualityStation } from '../../../types/iotAirQuality';
import type { IotBikeShareStation } from '../../../types/iotBikeShare';
import type { IotOsmPoiCategory, IotOsmPoiStation } from '../../../types/iotOsmPois';

export interface BirdEyeRoutePoint {
    sx: number;
    sy: number;
    wx: number;
    wy: number;
    wz: number;
}

export interface BirdEyeRouteData {
    points: BirdEyeRoutePoint[];
    /** Optional secondary polyline — the OSM bridge leg for outside-navmesh pins. */
    osmPoints?: BirdEyeRoutePoint[];
    /**
     * Optional single-point pin marker — set while the bird-eye pin sheet
     * is open BEFORE the user commits to directions. Rendered by
     * `BirdEyeRouteOverlay` as a solo flag bubble without any polyline.
     */
    pinMarker?: { sx: number; sy: number } | null;
    /**
     * Composed polyline's true first / last vertex, projected to screen
     * space. Overrides the fall-back heuristic (``points[0]`` /
     * ``osmPoints.last``) for directions-preview bubble placement on
     * routes with multiple leg kinds (OSM→NavMesh, cross-island, etc.),
     * where the first NavMesh vertex is the handover bridge rather
     * than the user's start position.
     */
    startMarker?: { sx: number; sy: number } | null;
    endMarker?: { sx: number; sy: number } | null;
    viewport: { width: number; height: number } | null;
}

export interface NearestNpcInfo {
    id: string;
    npcConfig: AvatarChatConfig & { [key: string]: any };
    distanceMeters: number;
}

export interface NearestIconInfo {
    id: string;
    iconConfig: {
        iconId: string;
        iconName: string;
        iconImage: string;
        greeting: string;
        [key: string]: any;
    };
    distanceMeters: number;
}

export function useControlHandlers() {
    const [controlMode, setControlMode] = useState<ControlMode>('pointClick');
    const [markerPlacementEnabled, setMarkerPlacementEnabled] = useState(false);
    const [nextClickPlacesMarker, setNextClickPlacesMarker] = useState(false);
    const [incidentPlacementEnabled, setIncidentPlacementEnabled] = useState(false);
    const [nextClickPlacesIncident, setNextClickPlacesIncident] = useState(false);
    const [incidentSizePreset, setIncidentSizePreset] = useState<'1x1' | '2x2' | '2x1'>('1x1');
    const [incidentShape, setIncidentShape] = useState<'cube' | 'cone' | 'torus'>('cube');
    const [poiMarkersVisible, setPoiMarkersVisible] = useState(false);
    const [iotAirStations, setIotAirStations] = useState<IotAirQualityStation[] | null>(null);
    const [iotAirStationsPanelOpen, setIotAirStationsPanelOpen] = useState(false);
    const [iotAirSelectedStationId, setIotAirSelectedStationId] = useState<string | null>(null);
    const [iotBikeShareStations, setIotBikeShareStations] = useState<IotBikeShareStation[] | null>(null);
    const [iotBikeSharePanelOpen, setIotBikeSharePanelOpen] = useState(false);
    const [iotBikeShareSelectedStationId, setIotBikeShareSelectedStationId] = useState<string | null>(null);
    const [iotOsmPoisAll, setIotOsmPoisAll] = useState<IotOsmPoiStation[] | null>(null);
    const [iotOsmPoisPanelOpen, setIotOsmPoisPanelOpen] = useState(false);
    const [iotOsmPoisCategory, setIotOsmPoisCategory] = useState<IotOsmPoiCategory>('restaurants');
    const [iotOsmPoisSelectedStationId, setIotOsmPoisSelectedStationId] = useState<string | null>(null);
    // Live transit list panel — shares the AIQ/Bike "select row → camera focus + detail" pattern.
    // Vehicle data lives in `transitLiveOverlayStatus.vehicles` (pushed by Kit), keyed by `token`.
    const [iotTransitLivePanelOpen, setIotTransitLivePanelOpen] = useState(false);
    const [iotTransitLiveSelectedVehicleToken, setIotTransitLiveSelectedVehicleToken] = useState<string | null>(null);
    const [peopleVisible, setPeopleVisible] = useState(false);
    const [npcTestActive, setNpcTestActive] = useState(false);
    const [maintenanceBotsActive, setMaintenanceBotsActive] = useState(false);
    const [lightCullingEnabled, setLightCullingEnabled] = useState(false);
    const [tileCullingEnabled, setTileCullingEnabled] = useState(false);
    const [stadiumLodLight, setStadiumLodLight] = useState(false);
    const [uiInteractionBoxes, setUiInteractionBoxes] = useState<UiInteractionBoxesUpdate | null>(null);
    const [triggerZoneNotification, setTriggerZoneNotification] = useState<{ message: string; zoneType: string } | null>(null);
    const triggerZoneTimerRef = useRef<number | null>(null);
    const [avatarChatOpen, setAvatarChatOpen] = useState(false);
    const [avatarChatConfig, setAvatarChatConfig] = useState<AvatarChatConfig | null>(null);
    const [videoPlayerOpen, setVideoPlayerOpen] = useState(false);
    const [videoPlayerConfig, setVideoPlayerConfig] = useState<VideoConfig | null>(null);
    const [videoList, setVideoList] = useState<VideoConfig[]>([]);
    const [cameraPlacementEnabled, setCameraPlacementEnabled] = useState(false);
    const [nextClickPlacesCamera, setNextClickPlacesCamera] = useState(false);
    const [nearestNpc, setNearestNpc] = useState<NearestNpcInfo | null>(null);
    const [nearestIcon, setNearestIcon] = useState<NearestIconInfo | null>(null);
    const [videobookOpen, setVideobookOpen] = useState(false);
    const [videobookEntry, setVideobookEntry] = useState<VideoBookEntry | null>(null);
    const [coinPoiOpen, setCoinPoiOpen] = useState(false);
    const [coinPoiPayload, setCoinPoiPayload] = useState<CoinPoiPayload | null>(null);
    /** True when opened from icon bubble → show hero splash before frosted chapter menu. */
    const [videobookShowEntrySplash, setVideobookShowEntrySplash] = useState(false);
    const [birdEyeRoutePoints, setBirdEyeRoutePoints] = useState<BirdEyeRouteData | null>(null);

    const [usdEditMode, setUsdEditMode] = useState(false);
    const [usdEditSubMode, setUsdEditSubMode] = useState<'transform' | 'vertices' | 'markers'>('transform');
    const [usdEditPhase, setUsdEditPhase] = useState<'idle' | 'selectMesh' | 'selectVertex' | 'selectPrim' | 'primSelected' | 'markerCreated' | 'markerSelected'>('idle');
    const [selectedVertexInfo, setSelectedVertexInfo] = useState<{ index: number; x: number; y: number; z: number } | null>(null);
    const [editingMeshPath, setEditingMeshPath] = useState<string | null>(null);
    const [editingVertexCount, setEditingVertexCount] = useState(0);
    const [usdEditSaveStatus, setUsdEditSaveStatus] = useState<{ status: string; message?: string } | null>(null);

    const [mediaAdminOpen, setMediaAdminOpen] = useState(false);
    const [transitLiveOverlayStatus, setTransitLiveOverlayStatus] = useState<TransitLiveOverlayStatusState | null>(null);
    const [mediaContentTheme, setMediaContentTheme] = useState('horseshow');
    const [mediaAdminKitRegistry, setMediaAdminKitRegistry] = useState<KitRegistryItem[] | null>(null);
    const [mediaAdminKitRefreshToken, setMediaAdminKitRefreshToken] = useState(0);
    const [devLocaleWriteStatus, setDevLocaleWriteStatus] = useState<{
        ok: boolean;
        message?: string;
        error?: string;
    } | null>(null);
    const bumpMediaAdminKitRefresh = useCallback(() => {
        setMediaAdminKitRefreshToken((n) => n + 1);
    }, []);
    const [transformInfo, setTransformInfo] = useState<{ primPath: string; primName: string; x: number; y: number; z: number; rotX: number; rotY: number; rotZ: number } | null>(null);
    const [nextClickSelectsVertex, setNextClickSelectsVertex] = useState(false);
    const [nextClickSelectsPrim, setNextClickSelectsPrim] = useState(false);
    const [vertexDragEnabled, setVertexDragEnabled] = useState(false);

    const [measureMode, setMeasureMode] = useState<'off' | 'pickFirst' | 'pickSecond'>('off');
    const [measurePoint1, setMeasurePoint1] = useState<{ index: number; x: number; y: number; z: number } | null>(null);
    const [measurePoint2, setMeasurePoint2] = useState<{ index: number; x: number; y: number; z: number } | null>(null);
    const [measureResult, setMeasureResult] = useState<number | null>(null);
    const measureModeRef = useRef<'off' | 'pickFirst' | 'pickSecond'>('off');
    const measurePoint1Ref = useRef<{ index: number; x: number; y: number; z: number } | null>(null);

    useEffect(() => { measureModeRef.current = measureMode; }, [measureMode]);
    useEffect(() => { measurePoint1Ref.current = measurePoint1; }, [measurePoint1]);

    const [sublayerList, setSublayerList] = useState<{ identifier: string; displayName: string }[]>([]);
    const [selectedSublayer, setSelectedSublayer] = useState<string>('');
    const [markerName, setMarkerName] = useState('');
    const [showMarkers, setShowMarkers] = useState(false);
    const [markerPlacementArmed, setMarkerPlacementArmed] = useState(false);
    const [selectedMarkerInfo, setSelectedMarkerInfo] = useState<{ primPath: string; primName: string; x: number; y: number; z: number; rotX: number; rotY: number; rotZ: number; layerDisplayName?: string } | null>(null);
    const [editOriginalLayer, setEditOriginalLayer] = useState(false);
    const [markerCopyIncludeFullDiagnostic, setMarkerCopyIncludeFullDiagnostic] = useState(false);

    const handleControlModeChange = useCallback((mode: ControlMode) => {
        if (mode === controlMode) return;
        const prevMode = controlMode;
        setControlMode(mode);

        if (prevMode === 'joystick') {
            try { sendMessage('joystickInput', { forward: 0, right: 0 }); } catch {}
            try { sendMessage('lookInput', { yaw: 0, pitch: 0 }); } catch {}
        }
        if (prevMode === 'pointClick' && mode !== 'pointClick') {
            try { sendMessage('navmeshRouteStop', { routeId: 'player' }); } catch {}
        }

        if (mode === 'pointClick') {
            try { sendMessage('navigationStateSet', { movementMode: 'pointClick', navigationEnabled: true, drawPath: false, autoMove: true, routeId: 'player' }); } catch {}
        } else if (mode === 'wasd') {
            try { sendMessage('navigationStateSet', { movementMode: 'wasd', navigationEnabled: true, drawPath: false, autoMove: false, routeId: 'player' }); } catch {}
        } else if (mode === 'joystick') {
            try { sendMessage('navigationStateSet', { movementMode: 'mobileJoystick', navigationEnabled: true, drawPath: false, autoMove: false, routeId: 'player' }); } catch {}
        }
        console.log(`Control mode: ${prevMode} -> ${mode}`);
    }, [controlMode]);

    const handleMarkerPlacementToggle = useCallback(() => {
        const newState = !markerPlacementEnabled;
        setMarkerPlacementEnabled(newState);
        if (!newState) setNextClickPlacesMarker(false);
        sendMessage('markerPlacementToggle', { enabled: newState });
    }, [markerPlacementEnabled]);

    const handleIncidentPlacementToggle = useCallback(() => {
        const newState = !incidentPlacementEnabled;
        setIncidentPlacementEnabled(newState);
        if (!newState) setNextClickPlacesIncident(false);
        sendMessage('incidentPlacementToggle', { enabled: newState });
    }, [incidentPlacementEnabled]);

    const handleAddMarkerClick = useCallback(() => { setNextClickPlacesMarker(true); }, []);
    const handleMarkerClickConsumed = useCallback(() => { setNextClickPlacesMarker(false); }, []);
    const handleAddIncidentClick = useCallback(() => { setNextClickPlacesIncident(true); }, []);
    const handleIncidentClickConsumed = useCallback(() => { setNextClickPlacesIncident(false); }, []);

    const dismissIotAirStationsPanel = useCallback(() => {
        try {
            sendMessage('iotAirQualityStations', { stations: [] });
            sendMessage('iotAirQualityHighlightStation', { id: null });
        } catch {
            /* ignore */
        }
        setIotAirStationsPanelOpen(false);
    }, []);

    const dismissIotBikeSharePanel = useCallback(() => {
        try {
            sendMessage('iotBikeShareStations', { stations: [] });
            sendMessage('iotBikeShareHighlightStation', { id: null });
        } catch {
            /* ignore */
        }
        setIotBikeSharePanelOpen(false);
    }, []);

    const dismissIotOsmPoisPanel = useCallback(() => {
        try {
            sendMessage('iotOsmPoisStations', { stations: [] });
            sendMessage('iotOsmPoisHighlightStation', { id: null });
        } catch {
            /* ignore */
        }
        setIotOsmPoisPanelOpen(false);
    }, []);

    /**
     * Transit dismiss differs from AIQ/Bike: vehicle markers belong to the Kit-side
     * overlay toggle, not to this panel. Closing the panel only hides the list/widget;
     * use the Live transit toggle in the IoT submenu to stop the Kit overlay itself.
     */
    const dismissIotTransitLivePanel = useCallback(() => {
        setIotTransitLivePanelOpen(false);
        setIotTransitLiveSelectedVehicleToken(null);
    }, []);

    const handlePoiMarkersToggle = useCallback(() => {
        const newState = !poiMarkersVisible;
        setPoiMarkersVisible(newState);
        console.log(`POI markers ${newState ? 'visible' : 'hidden'}`);
        sendMessage('poiMarkersToggle', { enabled: newState });
    }, [poiMarkersVisible]);

    const handleTransitLiveOverlayToggle = useCallback(() => {
        const cur = transitLiveOverlayStatus?.enabled === true;
        sendMessage('transitLiveOverlayRequest', { enabled: !cur });
    }, [transitLiveOverlayStatus]);

    const handlePeopleToggle = useCallback(() => {
        const newState = !peopleVisible;
        setPeopleVisible(newState);
        console.log(`Crowd ${newState ? 'visible' : 'hidden'}`);
        // `peopleToggle` drives the traffic crowd (/World/cctv1_crowd) on/off
        // (slider density is sent separately via peopleDensityUpdate). The
        // legacy /World/test_people layer it used to also toggle was removed.
        sendMessage('peopleToggle', { enabled: newState });
        // Drive the seated PointInstancer crowd density variant so the single
        // "Display crowd" toggle controls both crowds. The seated crowd's
        // authoritative state is owned by `useSeatNavigation.seatedCrowdLayout`
        // and updated via the `seatedCrowdLayoutChanged` response handler in
        // `seatHandlers.ts`, which keeps the dev-panel density picker in sync.
        try {
            sendMessage('seatedCrowdLayoutChange', {
                variant: newState ? SEATED_CROWD_ON_VARIANT : SEATED_CROWD_OFF_VARIANT,
            });
        } catch {}
    }, [peopleVisible]);

    const handleNpcTestToggle = useCallback(() => {
        if (npcTestActive) {
            setNpcTestActive(false);
            sendMessage('npcStopAll', {});
        } else {
            setNpcTestActive(true);
            sendMessage('npcStartAll', {});
        }
    }, [npcTestActive]);

    const handleLightCullingToggle = useCallback(() => {
        const newState = !lightCullingEnabled;
        setLightCullingEnabled(newState);
        sendMessage('lightCullingToggle', { enabled: newState });
    }, [lightCullingEnabled]);

    const handleTileCullingToggle = useCallback(() => {
        const newState = !tileCullingEnabled;
        setTileCullingEnabled(newState);
        sendMessage('tileCullingToggle', { enabled: newState });
    }, [tileCullingEnabled]);

    const handleStadiumLodToggle = useCallback(() => {
        const newLod = stadiumLodLight ? 'full' : 'light';
        setStadiumLodLight(!stadiumLodLight);
        sendMessage('stadiumLodToggle', { lod: newLod });
    }, [stadiumLodLight]);

    const handleMaintenanceBotsToggle = useCallback(() => {
        if (maintenanceBotsActive) {
            setMaintenanceBotsActive(false);
            sendMessage('maintenanceBotDespawn', {});
        } else {
            setMaintenanceBotsActive(true);
            sendMessage('maintenanceBotSpawn', {});
        }
    }, [maintenanceBotsActive]);

    const handleCameraPlacementToggle = useCallback(() => {
        const newState = !cameraPlacementEnabled;
        setCameraPlacementEnabled(newState);
        if (!newState) setNextClickPlacesCamera(false);
        sendMessage('cameraPlacementToggle', { enabled: newState });
    }, [cameraPlacementEnabled]);

    const handleAddCameraClick = useCallback(() => { setNextClickPlacesCamera(true); }, []);
    const handleCameraClickConsumed = useCallback(() => { setNextClickPlacesCamera(false); }, []);

    const clearMeasureState = useCallback(() => {
        setMeasureMode('off');
        measureModeRef.current = 'off';
        setMeasurePoint1(null);
        measurePoint1Ref.current = null;
        setMeasurePoint2(null);
        setMeasureResult(null);
        try { sendMessage('usdEdit.clearMeasureLine', {}); } catch {}
    }, []);

    const handleUsdEditToggle = useCallback(() => {
        const newState = !usdEditMode;
        setUsdEditMode(newState);
        if (newState) {
            if (usdEditSubMode === 'vertices') setUsdEditPhase('selectMesh');
            else if (usdEditSubMode === 'markers') {
                setUsdEditPhase('idle');
                sendMessage('usdEdit.requestSublayers', {});
            } else setUsdEditPhase('selectPrim');
        } else {
            setUsdEditPhase('idle');
            setSelectedVertexInfo(null);
            setEditingMeshPath(null);
            setEditingVertexCount(0);
            setTransformInfo(null);
            setSelectedMarkerInfo(null);
            setMarkerPlacementArmed(false);
            setNextClickSelectsVertex(false);
            setNextClickSelectsPrim(false);
            setVertexDragEnabled(false);
            clearMeasureState();
            setMarkerCopyIncludeFullDiagnostic(false);
            sendMessage('usdEdit.exitEditMode', {});
        }
    }, [usdEditMode, usdEditSubMode, clearMeasureState]);

    const handleUsdEditSubModeChange = useCallback((mode: 'transform' | 'vertices' | 'markers') => {
        if (mode === usdEditSubMode) return;
        if (usdEditSubMode === 'vertices') {
            sendMessage('usdEdit.exitVertexDots', {});
        }
        if (usdEditSubMode === 'markers') {
            sendMessage('usdEdit.exitMarkerMode', {});
            setMarkerPlacementArmed(false);
            setSelectedMarkerInfo(null);
        }
        setUsdEditSubMode(mode);
        setSelectedVertexInfo(null);
        setEditingMeshPath(null);
        setEditingVertexCount(0);
        setTransformInfo(null);
        setNextClickSelectsVertex(false);
        setNextClickSelectsPrim(false);
        setVertexDragEnabled(false);
        clearMeasureState();
        if (mode === 'vertices') setUsdEditPhase('selectMesh');
        else if (mode === 'markers') {
            setUsdEditPhase('idle');
            sendMessage('usdEdit.requestSublayers', {});
        } else setUsdEditPhase('selectPrim');
    }, [usdEditSubMode, clearMeasureState]);

    const handleSelectVertexClick = useCallback(() => {
        clearMeasureState();
        setNextClickSelectsVertex(true);
    }, [clearMeasureState]);
    const handleVertexSelectConsumed = useCallback(() => { setNextClickSelectsVertex(false); }, []);

    const handleMeasureDistanceClick = useCallback(() => {
        if (measureMode !== 'off' || measureResult != null) {
            clearMeasureState();
            return;
        }
        setNextClickSelectsVertex(false);
        setMeasureMode('pickFirst');
        measureModeRef.current = 'pickFirst';
        setMeasurePoint1(null);
        measurePoint1Ref.current = null;
        setMeasurePoint2(null);
        setMeasureResult(null);
        setNextClickSelectsVertex(true);
    }, [measureMode, measureResult, clearMeasureState]);
    const handleSelectPrimClick = useCallback(() => { setNextClickSelectsPrim(true); }, []);
    const handlePrimSelectConsumed = useCallback(() => { setNextClickSelectsPrim(false); }, []);

    const handleVertexEditNudge = useCallback((dx: number, dy: number, dz: number) => {
        if (selectedVertexInfo === null) return;
        sendMessage('usdEdit.moveVertex', {
            vertexIndex: selectedVertexInfo.index, dx, dy, dz,
        });
    }, [selectedVertexInfo]);

    const handleTransformNudgeTranslate = useCallback((dx: number, dy: number, dz: number) => {
        sendMessage('usdEdit.nudgeTranslate', { dx, dy, dz });
    }, []);

    const handleTransformNudgeRotate = useCallback((dx: number, dy: number, dz: number) => {
        sendMessage('usdEdit.nudgeRotate', { dx, dy, dz });
    }, []);

    const handleArmMarkerPlacement = useCallback(() => {
        if (!selectedSublayer || !markerName.trim()) return;
        sendMessage('usdEdit.armMarkerPlacement', {
            sublayerIdentifier: selectedSublayer,
            markerName: markerName.trim(),
        });
        setMarkerPlacementArmed(true);
    }, [selectedSublayer, markerName]);

    const handleShowMarkersToggle = useCallback(() => {
        const newState = !showMarkers;
        setShowMarkers(newState);
        if (!newState) setSelectedMarkerInfo(null);
        sendMessage('usdEdit.showMarkers', { visible: newState });
    }, [showMarkers]);

    const handleMarkerNudgeTranslate = useCallback((dx: number, dy: number, dz: number) => {
        sendMessage('usdEdit.nudgeMarkerTranslate', { dx, dy, dz, editOriginal: editOriginalLayer });
    }, [editOriginalLayer]);

    const handleMarkerNudgeRotate = useCallback((dx: number, dy: number, dz: number) => {
        sendMessage('usdEdit.nudgeMarkerRotate', { dx, dy, dz, editOriginal: editOriginalLayer });
    }, [editOriginalLayer]);

    const handleRemoveMarker = useCallback(() => {
        sendMessage('usdEdit.removeMarker', {});
    }, []);

    const handleCopyMarkerWorldTransform = useCallback(() => {
        sendMessage('usdEdit.copyMarkerWorldTransform', {
            includeFullDiagnostic: markerCopyIncludeFullDiagnostic,
        });
    }, [markerCopyIncludeFullDiagnostic]);

    const handleUsdEditSave = useCallback(() => {
        sendMessage('usdEdit.save', {});
    }, []);

    const handleUsdEditResetSession = useCallback(() => {
        sendMessage('usdEdit.resetSession', {});
        setSelectedVertexInfo(null);
        setTransformInfo(null);
        setSelectedMarkerInfo(null);
        setVertexDragEnabled(false);
        clearMeasureState();
    }, [clearMeasureState]);

    const handleUsdEditHardReset = useCallback(() => {
        sendMessage('usdEdit.hardReset', {});
        setSelectedVertexInfo(null);
        setTransformInfo(null);
        setSelectedMarkerInfo(null);
        setVertexDragEnabled(false);
        clearMeasureState();
    }, [clearMeasureState]);

    const handlePlayVideo = useCallback((video?: VideoConfig) => {
        const target = video || videoList[0];
        if (!target) {
            sendMessage('videoListRequest', {});
            return;
        }
        setVideoPlayerConfig(target);
        setVideoPlayerOpen(true);
    }, [videoList]);

    const handleVideoClose = useCallback(() => {
        setVideoPlayerOpen(false);
        setVideoPlayerConfig(null);
    }, []);

    const handleVideoComplete = useCallback((_config: VideoConfig) => {
        setVideoPlayerOpen(false);
        setVideoPlayerConfig(null);
    }, []);

    const cleanupTimers = useCallback(() => {
        if (triggerZoneTimerRef.current) {
            window.clearTimeout(triggerZoneTimerRef.current);
            triggerZoneTimerRef.current = null;
        }
    }, []);

    return {
        // State
        controlMode,
        markerPlacementEnabled, nextClickPlacesMarker,
        incidentPlacementEnabled, nextClickPlacesIncident,
        incidentSizePreset, setIncidentSizePreset,
        incidentShape, setIncidentShape,
        poiMarkersVisible, peopleVisible, setPeopleVisible,
        iotAirStations, setIotAirStations,
        iotAirStationsPanelOpen, setIotAirStationsPanelOpen,
        iotAirSelectedStationId, setIotAirSelectedStationId,
        dismissIotAirStationsPanel,
        iotBikeShareStations, setIotBikeShareStations,
        iotBikeSharePanelOpen, setIotBikeSharePanelOpen,
        iotBikeShareSelectedStationId, setIotBikeShareSelectedStationId,
        dismissIotBikeSharePanel,
        iotOsmPoisAll,
        setIotOsmPoisAll,
        iotOsmPoisPanelOpen,
        setIotOsmPoisPanelOpen,
        iotOsmPoisCategory,
        setIotOsmPoisCategory,
        iotOsmPoisSelectedStationId,
        setIotOsmPoisSelectedStationId,
        dismissIotOsmPoisPanel,
        iotTransitLivePanelOpen, setIotTransitLivePanelOpen,
        iotTransitLiveSelectedVehicleToken, setIotTransitLiveSelectedVehicleToken,
        dismissIotTransitLivePanel,
        npcTestActive, setNpcTestActive,
        lightCullingEnabled, setLightCullingEnabled,
        tileCullingEnabled, setTileCullingEnabled,
        stadiumLodLight, setStadiumLodLight,
        maintenanceBotsActive, setMaintenanceBotsActive,
        uiInteractionBoxes, setUiInteractionBoxes,
        triggerZoneNotification, setTriggerZoneNotification,
        triggerZoneTimerRef,
        avatarChatOpen, setAvatarChatOpen,
        avatarChatConfig, setAvatarChatConfig,
        videoPlayerOpen, setVideoPlayerOpen,
        videoPlayerConfig, setVideoPlayerConfig,
        videoList, setVideoList,
        cameraPlacementEnabled, nextClickPlacesCamera,
        nearestNpc, setNearestNpc,
        nearestIcon, setNearestIcon,
        videobookOpen, setVideobookOpen,
        videobookEntry, setVideobookEntry,
        videobookShowEntrySplash, setVideobookShowEntrySplash,
        coinPoiOpen, setCoinPoiOpen,
        coinPoiPayload, setCoinPoiPayload,
        birdEyeRoutePoints, setBirdEyeRoutePoints,
        usdEditMode, usdEditSubMode, usdEditPhase, setUsdEditPhase,
        selectedVertexInfo, setSelectedVertexInfo,
        editingMeshPath, setEditingMeshPath,
        editingVertexCount, setEditingVertexCount,
        transformInfo, setTransformInfo,
        sublayerList, setSublayerList,
        selectedSublayer, setSelectedSublayer,
        markerName, setMarkerName,
        showMarkers, setShowMarkers,
        markerPlacementArmed, setMarkerPlacementArmed,
        selectedMarkerInfo, setSelectedMarkerInfo,
        editOriginalLayer, setEditOriginalLayer,
        markerCopyIncludeFullDiagnostic, setMarkerCopyIncludeFullDiagnostic,
        nextClickSelectsVertex, setNextClickSelectsVertex,
        nextClickSelectsPrim, setNextClickSelectsPrim,
        vertexDragEnabled, setVertexDragEnabled,
        measureMode, setMeasureMode,
        measurePoint1, setMeasurePoint1,
        measurePoint2, setMeasurePoint2,
        measureResult, setMeasureResult,
        measureModeRef, measurePoint1Ref,
        // Handlers
        handleControlModeChange,
        handleMarkerPlacementToggle, handleIncidentPlacementToggle,
        handleCameraPlacementToggle,
        handleAddMarkerClick, handleMarkerClickConsumed,
        handleAddIncidentClick, handleIncidentClickConsumed,
        handleAddCameraClick, handleCameraClickConsumed,
        handlePoiMarkersToggle, handlePeopleToggle,
        handleLightCullingToggle,
        handleTileCullingToggle,
        handleStadiumLodToggle,
        handleNpcTestToggle, handleMaintenanceBotsToggle,
        handlePlayVideo, handleVideoClose, handleVideoComplete,
        handleUsdEditToggle, handleUsdEditSubModeChange,
        handleSelectVertexClick, handleVertexSelectConsumed, handleMeasureDistanceClick,
        handleSelectPrimClick, handlePrimSelectConsumed,
        handleVertexEditNudge, handleTransformNudgeTranslate, handleTransformNudgeRotate,
        handleArmMarkerPlacement, handleShowMarkersToggle, handleMarkerNudgeTranslate, handleMarkerNudgeRotate, handleRemoveMarker,
        handleCopyMarkerWorldTransform,
        handleUsdEditSave, handleUsdEditResetSession, handleUsdEditHardReset,
        usdEditSaveStatus, setUsdEditSaveStatus,
        mediaAdminOpen, setMediaAdminOpen,
        transitLiveOverlayStatus,
        setTransitLiveOverlayStatus,
        handleTransitLiveOverlayToggle,
        mediaContentTheme, setMediaContentTheme,
        mediaAdminKitRegistry, setMediaAdminKitRegistry,
        mediaAdminKitRefreshToken,
        bumpMediaAdminKitRefresh,
        devLocaleWriteStatus, setDevLocaleWriteStatus,
        cleanupTimers,
    };
}
