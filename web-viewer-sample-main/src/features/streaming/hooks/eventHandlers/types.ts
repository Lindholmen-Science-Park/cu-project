import type { RouteMeasure, ExitResult, PoiResult, CameraDataStats, CameraDepthStatus, OsmRouteInfo, TransitLiveOverlayStatusState } from '../../types';
import type { InteractionPointDef, NavigationSpot, CameraType } from '../../types';
import type { UiInteractionBoxesUpdate } from '../../overlays/interactionBoxes/InteractionBoxesOverlay';
import type { VideoConfig } from '../../overlays/videoPlayer/VideoPlayerOverlay';
import type { NearestNpcInfo, NearestIconInfo, BirdEyeRouteData } from '../useControlHandlers';
import type { WeatherOption, SeasonOption } from '../../../cu/types';
import type { AppMode } from '../../../../context/AppModeContext';
import type { MapMarkerSheetData } from '../navigationHandlers/useMapMarkerPoiNavigation';
import type { RouteErrorAnnouncement } from '../../utils/navRouteErrorMessages';

export interface EventStateSetters {
    appModeRef: React.MutableRefObject<AppMode>;
    setNavmeshActive: React.Dispatch<React.SetStateAction<boolean>>;
    setShortcutsActive?: React.Dispatch<React.SetStateAction<boolean>>;
    setActiveSpotRouteId: React.Dispatch<React.SetStateAction<string | null>>;
    setMovingToSpotId: React.Dispatch<React.SetStateAction<string | null>>;
    /** Player auto-move active flag — drives the OSM route overlay Play/Pause FAB icon. */
    setPlayerAutoMoveActive: React.Dispatch<React.SetStateAction<boolean>>;
    /** Whether the player is currently bound to the OSM route overlay — gates FAB visibility. */
    setOsmRouteOverlayAttached: React.Dispatch<React.SetStateAction<boolean>>;
    setRouteMeasureByRouteId: React.Dispatch<React.SetStateAction<Record<string, RouteMeasure>>>;
    setRouteReadyByRouteId: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
    markRouteCalculating: (routeId: string) => void;
    markRouteReady: (routeId: string, ready: boolean) => void;
    setRouteError: (routeId: string, error: RouteErrorAnnouncement) => void;
    clearRouteError: (routeId: string) => void;
    setExitsResults: React.Dispatch<React.SetStateAction<ExitResult[]>>;
    setActiveSeatRouteId: React.Dispatch<React.SetStateAction<string | null>>;
    setMovingToSeatId: React.Dispatch<React.SetStateAction<string | null>>;
    lastSeatPositionRef: React.MutableRefObject<number[] | null>;
    seatRouteFromSeatRef: React.MutableRefObject<boolean>;
    /** Paired clear for `seatRouteFromSeatRef` + `seatRouteDisplayLabel` — see `useSeatNavigation.clearSeatRouteSwapState`. */
    clearSeatRouteSwapState: () => void;
    setSeatingLayout: React.Dispatch<React.SetStateAction<string | null>>;
    setAvailableSeatingLayouts: React.Dispatch<React.SetStateAction<string[]>>;
    setSeatedCrowdLayout: React.Dispatch<React.SetStateAction<string | null>>;
    setAvailableSeatedCrowdLayouts: React.Dispatch<React.SetStateAction<string[]>>;
    setCameraDataHeatmapActive: React.Dispatch<React.SetStateAction<boolean>>;
    setCameraDataTrackerActive: React.Dispatch<React.SetStateAction<boolean>>;
    setCameraDataStats: React.Dispatch<React.SetStateAction<CameraDataStats | null>>;
    setPeopleVisible: React.Dispatch<React.SetStateAction<boolean>>;
    setLightCullingEnabled: React.Dispatch<React.SetStateAction<boolean>>;
    setTileCullingEnabled: React.Dispatch<React.SetStateAction<boolean>>;
    setActiveFixedCamera: React.Dispatch<React.SetStateAction<string | null>>;
    setPlacedCameras: React.Dispatch<React.SetStateAction<{ id: string; label: string; primPath?: string }[]>>;
    setUiInteractionBoxes: React.Dispatch<React.SetStateAction<UiInteractionBoxesUpdate | null>>;
    setInteractionPointDefs: React.Dispatch<React.SetStateAction<InteractionPointDef[]>>;
    setNpcTestActive: React.Dispatch<React.SetStateAction<boolean>>;
    setMaintenanceBotsActive: React.Dispatch<React.SetStateAction<boolean>>;
    setCameraDepthStatus: React.Dispatch<React.SetStateAction<CameraDepthStatus>>;
    setCameraDepthPointCount: React.Dispatch<React.SetStateAction<number>>;
    setCameraDepthObstacleCount: React.Dispatch<React.SetStateAction<number>>;
    setCameraDepthPointsVisible: React.Dispatch<React.SetStateAction<boolean>>;
    setCameraDepthAreasVisible: React.Dispatch<React.SetStateAction<boolean>>;
    setNavmeshBaking: React.Dispatch<React.SetStateAction<boolean>>;
    setNavmeshMode: React.Dispatch<React.SetStateAction<'wheelchair' | 'walking'>>;
    setCameraDataCalcActive: React.Dispatch<React.SetStateAction<boolean>>;
    setCameraDataCalcBaking: React.Dispatch<React.SetStateAction<boolean>>;
    setSoundDataCalcActive: React.Dispatch<React.SetStateAction<boolean>>;
    setSoundDataCalcBaking: React.Dispatch<React.SetStateAction<boolean>>;
    setActiveExitRouteId: React.Dispatch<React.SetStateAction<string | null>>;
    setMovingToExitId: React.Dispatch<React.SetStateAction<string | null>>;
    lastExitPrimPathRef: React.MutableRefObject<string | null>;
    setRestroomResults: React.Dispatch<React.SetStateAction<PoiResult[]>>;
    restroomResultsRef: React.MutableRefObject<PoiResult[]>;
    setRestroomPoiListLoading: React.Dispatch<React.SetStateAction<boolean>>;
    setActivePoiRouteId: React.Dispatch<React.SetStateAction<string | null>>;
    activePoiRouteIdRef: React.MutableRefObject<string | null>;
    setMovingToPoiId: React.Dispatch<React.SetStateAction<string | null>>;
    lastPoiPrimPathRef: React.MutableRefObject<string | null>;
    lastPoiDisplayNameRef: React.MutableRefObject<string | null>;
    lastPoiEndPosRef: React.MutableRefObject<[number, number, number] | null>;
    setRestroomWidgetOpen: React.Dispatch<React.SetStateAction<boolean>>;
    setQuietZoneResults: React.Dispatch<React.SetStateAction<PoiResult[]>>;
    setQuietZonePoiListLoading: React.Dispatch<React.SetStateAction<boolean>>;
    quietZoneResultsRef: React.MutableRefObject<PoiResult[]>;
    setActiveQuietZoneRouteId: React.Dispatch<React.SetStateAction<string | null>>;
    activeQuietZoneRouteIdRef: React.MutableRefObject<string | null>;
    setMovingToQuietZoneId: React.Dispatch<React.SetStateAction<string | null>>;
    lastQuietZonePrimPathRef: React.MutableRefObject<string | null>;
    lastQuietZoneDisplayNameRef: React.MutableRefObject<string | null>;
    setQuietZoneWidgetOpen: React.Dispatch<React.SetStateAction<boolean>>;
    setQuietZoneTrackingScreen: React.Dispatch<React.SetStateAction<boolean>>;
    setRestroomTrackingScreen: React.Dispatch<React.SetStateAction<boolean>>;
    setTriggerZoneNotification: React.Dispatch<React.SetStateAction<{ message: string; zoneType: string } | null>>;
    triggerZoneTimerRef: React.MutableRefObject<number | null>;
    sceneLoadingRef: React.MutableRefObject<boolean>;
    navigationSpotsRef: React.MutableRefObject<NavigationSpot[]>;
    setOsmRouteInfo: React.Dispatch<React.SetStateAction<OsmRouteInfo | null>>;
    setVideoList: React.Dispatch<React.SetStateAction<VideoConfig[]>>;
    setVideoPlayerOpen: React.Dispatch<React.SetStateAction<boolean>>;
    setVideoPlayerConfig: React.Dispatch<React.SetStateAction<VideoConfig | null>>;
    dispatchInteractionAction?: (interactableId: string, action: string, payload: any) => boolean;
    setViewportCaptureStatus: React.Dispatch<React.SetStateAction<'idle' | 'capturing'>>;
    setTransitLiveOverlayStatus: React.Dispatch<React.SetStateAction<TransitLiveOverlayStatusState | null>>;
    setStadiumLodLight: React.Dispatch<React.SetStateAction<boolean>>;
    setCurrentCamera: React.Dispatch<React.SetStateAction<CameraType>>;
    setSeatArrivalCelebrationVisible: React.Dispatch<React.SetStateAction<boolean>>;
    seatArrivalCelebrationTimerRef: React.MutableRefObject<number | null>;
    setSeatArrivalLabel: React.Dispatch<React.SetStateAction<string | null>>;
    setPoiArrivalVisible: React.Dispatch<React.SetStateAction<boolean>>;
    poiArrivalTimerRef: React.MutableRefObject<number | null>;
    setPoiArrivalLabel: React.Dispatch<React.SetStateAction<string | null>>;
    setUsdEditPhase?: React.Dispatch<React.SetStateAction<'idle' | 'selectMesh' | 'selectVertex' | 'selectPrim' | 'primSelected' | 'markerCreated' | 'markerSelected'>>;
    setSelectedVertexInfo?: React.Dispatch<React.SetStateAction<{ index: number; x: number; y: number; z: number } | null>>;
    setEditingMeshPath?: React.Dispatch<React.SetStateAction<string | null>>;
    setEditingVertexCount?: React.Dispatch<React.SetStateAction<number>>;
    setTransformInfo?: React.Dispatch<React.SetStateAction<{ primPath: string; primName: string; x: number; y: number; z: number; rotX: number; rotY: number; rotZ: number } | null>>;
    setUsdEditSaveStatus?: React.Dispatch<React.SetStateAction<{ status: string; message?: string } | null>>;
    setSublayerList?: React.Dispatch<React.SetStateAction<{ identifier: string; displayName: string }[]>>;
    setMarkerPlacementArmed?: React.Dispatch<React.SetStateAction<boolean>>;
    setSelectedMarkerInfo?: React.Dispatch<React.SetStateAction<{ primPath: string; primName: string; x: number; y: number; z: number; rotX: number; rotY: number; rotZ: number; layerDisplayName?: string } | null>>;
    setNextClickSelectsVertex?: React.Dispatch<React.SetStateAction<boolean>>;
    setNextClickSelectsPrim?: React.Dispatch<React.SetStateAction<boolean>>;
    measureModeRef?: React.MutableRefObject<'off' | 'pickFirst' | 'pickSecond'>;
    measurePoint1Ref?: React.MutableRefObject<{ index: number; x: number; y: number; z: number } | null>;
    setMeasureMode?: React.Dispatch<React.SetStateAction<'off' | 'pickFirst' | 'pickSecond'>>;
    setMeasurePoint1?: React.Dispatch<React.SetStateAction<{ index: number; x: number; y: number; z: number } | null>>;
    setMeasurePoint2?: React.Dispatch<React.SetStateAction<{ index: number; x: number; y: number; z: number } | null>>;
    setMeasureResult?: React.Dispatch<React.SetStateAction<number | null>>;
    setAvailableScenes: React.Dispatch<React.SetStateAction<{ id: string; label: string }[]>>;
    setNearestNpc: React.Dispatch<React.SetStateAction<NearestNpcInfo | null>>;
    setNearestIcon: React.Dispatch<React.SetStateAction<NearestIconInfo | null>>;
    // World state sync setters (optional — only wired in streaming window)
    setWeather?: React.Dispatch<React.SetStateAction<WeatherOption>>;
    setSeason?: React.Dispatch<React.SetStateAction<SeasonOption>>;
    setTimeOfDayMinutes?: React.Dispatch<React.SetStateAction<number>>;
    setCameraHeight?: React.Dispatch<React.SetStateAction<number>>;
    setFogIntensity?: React.Dispatch<React.SetStateAction<number>>;
    setTimeOfDay?: React.Dispatch<React.SetStateAction<number>>;
    setDayOfYear?: React.Dispatch<React.SetStateAction<number>>;
    setCloudCoverage?: React.Dispatch<React.SetStateAction<number>>;
    setCumulusEnabled?: React.Dispatch<React.SetStateAction<boolean>>;
    setWeatherPreset?: React.Dispatch<React.SetStateAction<string>>;
    setCurrentPhysics?: React.Dispatch<React.SetStateAction<import('../../types').PhysicsState>>;
    setMovementSpeed?: React.Dispatch<React.SetStateAction<number>>;
    setFirstPersonLocation?: React.Dispatch<React.SetStateAction<{ x: number; y: number; z: number } | null>>;
    setBirdEyeRoutePoints?: React.Dispatch<React.SetStateAction<BirdEyeRouteData | null>>;
    /** Opens the bird-eye map-marker sheet. Wired in `StreamOnlyWindow.tsx` so Kit's `birdEyePinSheet` can reach the nav hook. */
    openMapMarkerSheet?: (data: MapMarkerSheetData) => void;
    setMediaAdminKitRegistry?: React.Dispatch<
        React.SetStateAction<
            | Array<{
                  pattern: string;
                  primPath: string;
                  primName: string;
                  worldTranslate: [number, number, number] | null;
              }>
            | null
        >
    >;
    setMediaContentTheme?: React.Dispatch<React.SetStateAction<string>>;
    setDevLocaleWriteStatus?: React.Dispatch<
        React.SetStateAction<{ ok: boolean; message?: string; error?: string } | null>
    >;
    setAccessibilityDiffVisible?: React.Dispatch<React.SetStateAction<boolean>>;
    setNavmeshDebugOverlayVisible?: React.Dispatch<React.SetStateAction<boolean>>;
}
