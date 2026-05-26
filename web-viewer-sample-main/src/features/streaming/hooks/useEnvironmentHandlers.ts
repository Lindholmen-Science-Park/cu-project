import { useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { sendMessage, TRAFFIC_SLIDER_DEBOUNCE_MS } from '../messaging';
import type { CameraDataStats, CameraDepthStatus } from '../types';
import { CameraType, PhysicsState, ControlMode } from '../types';
import { WeatherData } from '../../dev/environment/WeatherService';
import type { WeatherOption, SeasonOption } from '../../cu/types';
import { DEFAULT_TIME_OF_DAY_MINUTES } from '../../cu/constants';
import { beginViewTransition, notifyViewTransitionKitReady } from '../viewTransition';

export function useEnvironmentHandlers(streamReady: boolean) {
    const { t } = useTranslation();
    const [currentCamera, setCurrentCamera] = useState<CameraType>('bird_eye');
    const [currentPhysics, setCurrentPhysics] = useState<PhysicsState>('disabled');
    const [showWeather, setShowWeather] = useState(false);
    const [showEnvironmentalLight, setShowEnvironmentalLight] = useState(false);
    const [fogIntensity, setFogIntensity] = useState(0.0);
    const [timeOfDay, setTimeOfDay] = useState(12.0);
    const [dayOfYear, setDayOfYear] = useState(187);
    const [cloudCoverage, setCloudCoverage] = useState(0.5);
    const [cumulusEnabled, setCumulusEnabled] = useState(true);
    const [weatherPreset, setWeatherPreset] = useState<string>('partlyCloudy');
    const [activeFixedCamera, setActiveFixedCamera] = useState<string | null>(null);
    const [placedCameras, setPlacedCameras] = useState<{ id: string; label: string; primPath?: string }[]>([]);

    // Camera data visualization
    const [cameraDataHeatmapActive, setCameraDataHeatmapActive] = useState(false);
    const [cameraDataTrackerActive, setCameraDataTrackerActive] = useState(false);
    const [cameraDataStats, setCameraDataStats] = useState<CameraDataStats | null>(null);
    const [cameraAreaCubesVisible, setCameraAreaCubesVisible] = useState(false);
    const [cameraDataCalcActive, setCameraDataCalcActive] = useState(false);
    const [cameraDataCalcBaking, setCameraDataCalcBaking] = useState(false);
    const [cameraPathfindingWidgetOpen, setCameraPathfindingWidgetOpen] = useState(false);
    const [cctv1TrafficValue, setCctv1TrafficValue] = useState(1.0);
    const [cameraCosts, setCameraCosts] = useState<Record<string, number>>({
        camera_vip_entrance_area: 1.0,
        camera_main_entrance_exit_area: 1.0,
        camera_main_entrance_entry_area: 1.0,
    });

    // Camera depth
    const [cameraDepthStatus, setCameraDepthStatus] = useState<CameraDepthStatus>('idle');
    const [cameraDepthPointCount, setCameraDepthPointCount] = useState(0);
    const [cameraDepthObstacleCount, setCameraDepthObstacleCount] = useState(0);
    const [cameraDepthPointsVisible, setCameraDepthPointsVisible] = useState(true);
    const [cameraDepthAreasVisible, setCameraDepthAreasVisible] = useState(false);

    // Last first-person position (Kit-authoritative, display copy)
    const [firstPersonLocation, setFirstPersonLocation] = useState<{ x: number; y: number; z: number } | null>(null);

    // Sound
    const [soundAreasVisible, setSoundAreasVisible] = useState(false);
    const [soundDataCalcActive, setSoundDataCalcActive] = useState(false);
    const [soundDataCalcBaking, setSoundDataCalcBaking] = useState(false);
    const [soundCostWidgetOpen, setSoundCostWidgetOpen] = useState(false);
    const [soundCosts, setSoundCosts] = useState<Record<string, number>>({
        sound_location_01_area: 1.0,
        sound_location_02_area: 1.0,
        sound_location_03_area: 1.0,
        sound_location_04_area: 1.0,
    });

    // Debounce refs
    const trafficDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const cameraCostDebounceRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
    const soundCostDebounceRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

    const handleCameraChange = useCallback((cameraType: CameraType) => {
        console.log(`Switching to ${cameraType} camera`);
        setCurrentCamera(cameraType);
        if (cameraType === 'bird_eye') {
            // The scene-load init dispatches `navigationStateSet { autoMove:
            // true, routeId: "player" }` which sets `_auto_move_active = True`
            // in the interactions extension and short-circuits the entire
            // `_on_update` tick (NPC proximity, projectables loop, etc.).
            // Every path to bird-eye must clear that flag or POI map markers
            // and the user-location arrow stay invisible. The CU view-toggle
            // already does this before calling us; the dev camera buttons and
            // the globe exit go straight through `handleCameraChange`. Doing
            // it here once means no entry point can forget. Idempotent —
            // safe to send when CU already cleared it.
            try {
                sendMessage('navigationStateSet', {
                    movementMode: 'pointClick',
                    autoMove: false,
                    routeId: 'player',
                    endPos: null,
                    endpointPath: null,
                });
            } catch { /* best-effort */ }
        }
        if (cameraType !== 'space') {
            sendMessage('cameraViewSwitchRequest', { viewType: cameraType === 'first_person' ? 'firstPerson' : 'birdEye' });
        }
    }, []);

    const handleFixedCameraChange = useCallback((cameraId: string | null, controlMode: ControlMode) => {
        setActiveFixedCamera(cameraId);
        if (!cameraId || cameraId === '') {
            sendMessage('fixedCameraExitRequest', {});
            const movementMode = controlMode === 'pointClick' ? 'pointClick' : controlMode === 'wasd' ? 'wasd' : 'mobileJoystick';
            sendMessage('navigationStateSet', { movementMode, navigationEnabled: true, drawPath: false, autoMove: true, routeId: 'player' });
        } else {
            const placed = placedCameras.find((c) => c.id === cameraId);
            if (placed?.primPath) {
                sendMessage('fixedCameraSwitchRequest', { cameraPrimPath: placed.primPath });
            } else {
                sendMessage('fixedCameraSwitchRequest', { cameraId });
            }
            sendMessage('navigationStateSet', { movementMode: 'disabled', navigationEnabled: false, drawPath: false, autoMove: false, routeId: 'player' });
        }
    }, [placedCameras]);

    const handlePhysicsChange = useCallback(async (physicsState: PhysicsState) => {
        if (!streamReady) { console.warn('Stream not ready, cannot change physics'); return; }
        try {
            console.log(`Physics state changed to: ${physicsState}`);
            sendMessage('physicsControlRequest', { action: physicsState === 'enabled' ? 'start' : 'stop' });
            setCurrentPhysics(physicsState);
        } catch (error) { console.error('Error controlling physics:', error); }
    }, [streamReady]);

    const [showWeatherSeasonPicker, setShowWeatherSeasonPicker] = useState(false);

    const handleWeatherChange = useCallback((_weather: WeatherData) => {}, []);
    const handleWeatherToggle = useCallback(() => { setShowWeather((prev) => !prev); }, []);
    const handleEnvironmentalLightToggle = useCallback(() => { setShowEnvironmentalLight((prev) => !prev); }, []);
    const handleWeatherSeasonPickerToggle = useCallback(() => { setShowWeatherSeasonPicker((prev) => !prev); }, []);

    const handleFogIntensityChange = useCallback((intensity: number) => {
        console.log(`Fog intensity changed to: ${intensity}`);
        setFogIntensity(intensity);
        sendMessage('fogControlRequest', { enabled: intensity > 0, intensity });
    }, []);

    const [movementSpeed, setMovementSpeed] = useState(1.0);

    const handleSpeedChange = useCallback((speed: number) => {
        setMovementSpeed(speed);
        sendMessage('movementSpeedChange', { speed });
    }, []);

    // Default = 1m70 character height − 15 cm eye offset = 155 cm camera height.
    const [cameraHeight, setCameraHeight] = useState(155);

    const handleCameraHeightChange = useCallback((heightCm: number) => {
        setCameraHeight(heightCm);
        sendMessage('cameraHeightChange', { height: heightCm });
    }, []);

    // CU-facing world-settings (simplified weather/season/time pickers)
    const [weather, setWeather] = useState<WeatherOption>('sun');
    const [season, setSeason] = useState<SeasonOption>('summer');
    const [timeOfDayMinutes, setTimeOfDayMinutes] = useState(DEFAULT_TIME_OF_DAY_MINUTES);

    const WEATHER_PRESET: Record<WeatherOption, string> = { sun: 'partlyCloudy', rain: 'rainy', fog: 'foggy', snow: 'snowy' };
    const SEASON_DAY: Record<SeasonOption, number> = { summer: 172, spring: 80, autumn: 266, winter: 355 };
    const applyWeather = useCallback((w: WeatherOption) => {
        beginViewTransition({
            message: t('loading.changingWeather'),
            onFadeOutComplete: () => {
                setWeather(w);
                sendMessage('skyControlRequest', { weatherPreset: WEATHER_PRESET[w] });
                setTimeout(() => notifyViewTransitionKitReady(), 500);
            },
        });
    }, [t]);

    const applySeason = useCallback((s: SeasonOption) => {
        beginViewTransition({
            message: t('loading.changingSeason'),
            onFadeOutComplete: () => {
                setSeason(s);
                sendMessage('seasonChangeRequest', { season: s });
                sendMessage('skyControlRequest', { dayOfYear: SEASON_DAY[s], timeOfDay: timeOfDayMinutes / 60 });
            },
        });
    }, [t, timeOfDayMinutes]);

    const applyTimeOfDay = useCallback((mins: number) => {
        setTimeOfDayMinutes(mins);
        sendMessage('skyControlRequest', { timeOfDay: mins / 60 });
    }, []);

    const handleTimeOfDayChange = useCallback((time: number) => {
        setTimeOfDay(time);
        sendMessage('skyControlRequest', { timeOfDay: time });
    }, []);

    const handleDayOfYearChange = useCallback((day: number) => {
        setDayOfYear(day);
        sendMessage('skyControlRequest', { dayOfYear: day });
    }, []);

    const handleCloudCoverageChange = useCallback((coverage: number) => {
        setCloudCoverage(coverage);
        sendMessage('skyControlRequest', { cloudCoverage: coverage });
    }, []);

    const handleCumulusToggle = useCallback(() => {
        const newState = !cumulusEnabled;
        setCumulusEnabled(newState);
        sendMessage('skyControlRequest', { cumulusEnabled: newState });
    }, [cumulusEnabled]);

    const handleWeatherPresetChange = useCallback((preset: string) => {
        setWeatherPreset(preset);
        sendMessage('skyControlRequest', { weatherPreset: preset });
    }, []);

    const handleCctv1TrafficChange = useCallback((value: number) => {
        setCctv1TrafficValue(value);
        if (trafficDebounceRef.current) clearTimeout(trafficDebounceRef.current);
        trafficDebounceRef.current = window.setTimeout(() => {
            trafficDebounceRef.current = null;
            sendMessage('navmeshCameraAreaCostUpdate', { areaName: 'cctv1_navmesh_area', cost: value });
            sendMessage('peopleDensityUpdate', { density: value, maxDensity: 15 });
            console.log('CCTV1 traffic cost updated:', value);
        }, TRAFFIC_SLIDER_DEBOUNCE_MS);
    }, []);

    const handleCameraCostChange = useCallback((areaName: string, cost: number) => {
        setCameraCosts((prev) => ({ ...prev, [areaName]: cost }));
        if (cameraCostDebounceRef.current[areaName]) clearTimeout(cameraCostDebounceRef.current[areaName]);
        cameraCostDebounceRef.current[areaName] = window.setTimeout(() => {
            delete cameraCostDebounceRef.current[areaName];
            sendMessage('navmeshCameraAreaCostUpdate', { areaName, cost });
            console.log(`Camera cost updated: ${areaName} = ${cost}`);
        }, TRAFFIC_SLIDER_DEBOUNCE_MS);
    }, []);

    const handleCameraDataHeatmapToggle = useCallback(() => {
        const newState = !cameraDataHeatmapActive;
        setCameraDataHeatmapActive(newState);
        sendMessage('cameraDataVisualizationRequest', { action: newState ? 'start' : 'stop', mode: 'heatmap' });
        console.log('Heatmap toggle:', newState);
    }, [cameraDataHeatmapActive]);

    const handleCameraDataTrackerToggle = useCallback(() => {
        const newState = !cameraDataTrackerActive;
        setCameraDataTrackerActive(newState);
        sendMessage('cameraDataVisualizationRequest', { action: newState ? 'start' : 'stop', mode: 'tracker' });
        console.log('Sphere tracker toggle:', newState);
    }, [cameraDataTrackerActive]);

    const handleCameraAreaCubesToggle = useCallback(() => {
        const newState = !cameraAreaCubesVisible;
        setCameraAreaCubesVisible(newState);
        sendMessage('showNavmeshCameraAreasRequest', { visible: newState });
        console.log(`Camera area cubes ${newState ? 'shown' : 'hidden'}`);
    }, [cameraAreaCubesVisible]);

    const handleCameraDataCalcToggle = useCallback(() => {
        if (cameraDataCalcBaking) return;
        const newState = !cameraDataCalcActive;
        setCameraDataCalcActive(newState);
        if (newState) setCameraPathfindingWidgetOpen(true);
        sendMessage('cameraDataCalcToggle', { active: newState });
        console.log(`Camera data calc ${newState ? 'activated' : 'deactivated'}`);
    }, [cameraDataCalcActive, cameraDataCalcBaking]);

    const handleSoundAreasToggle = useCallback(() => {
        const newState = !soundAreasVisible;
        setSoundAreasVisible(newState);
        sendMessage('showSoundAreasRequest', { visible: newState });
        console.log(`Sound areas ${newState ? 'shown' : 'hidden'}`);
    }, [soundAreasVisible]);

    const handleSoundDataCalcToggle = useCallback(() => {
        if (soundDataCalcBaking) return;
        const newState = !soundDataCalcActive;
        setSoundDataCalcActive(newState);
        if (newState) setSoundCostWidgetOpen(true);
        sendMessage('soundDataCalcToggle', { active: newState });
        console.log(`Sound data calc ${newState ? 'activated' : 'deactivated'}`);
    }, [soundDataCalcActive, soundDataCalcBaking]);

    const handleSoundCostChange = useCallback((areaName: string, cost: number) => {
        setSoundCosts((prev) => ({ ...prev, [areaName]: cost }));
        if (soundCostDebounceRef.current[areaName]) clearTimeout(soundCostDebounceRef.current[areaName]);
        soundCostDebounceRef.current[areaName] = window.setTimeout(() => {
            delete soundCostDebounceRef.current[areaName];
            sendMessage('soundAreaCostUpdate', { areaName, cost });
            console.log(`Sound area cost updated: ${areaName} = ${cost}`);
        }, TRAFFIC_SLIDER_DEBOUNCE_MS);
    }, []);

    // Camera depth handlers
    const handleCameraDepthCapture = useCallback(() => {
        setCameraDepthStatus('capturing');
        sendMessage('cameraDepthRequest', { action: 'capture' });
    }, []);

    const handleCameraDepthDetectObstacles = useCallback(() => {
        setCameraDepthStatus('detecting');
        sendMessage('cameraDepthRequest', { action: 'detect_obstacles' });
    }, []);

    const handleCameraDepthClear = useCallback(() => {
        sendMessage('cameraDepthRequest', { action: 'clear' });
    }, []);

    const handleCameraDepthTogglePoints = useCallback((visible: boolean) => {
        setCameraDepthPointsVisible(visible);
        sendMessage('cameraDepthRequest', { action: 'toggle_points', visible });
    }, []);

    const handleCameraDepthToggleAreas = useCallback((visible: boolean) => {
        setCameraDepthAreasVisible(visible);
        sendMessage('showCameraDepthAreasRequest', { visible });
    }, []);

    const handleRemovePlacedCamera = useCallback((cameraId: string) => {
        sendMessage('placedCameraRemove', { cameraId });
    }, []);

    /** Cleanup debounce timers — call on unmount */
    const cleanupDebounces = useCallback(() => {
        if (trafficDebounceRef.current) { clearTimeout(trafficDebounceRef.current); trafficDebounceRef.current = null; }
        Object.values(cameraCostDebounceRef.current).forEach(clearTimeout);
        cameraCostDebounceRef.current = {};
        Object.values(soundCostDebounceRef.current).forEach(clearTimeout);
        soundCostDebounceRef.current = {};
    }, []);

    return {
        // State
        currentCamera, setCurrentCamera, currentPhysics, setCurrentPhysics,
        showWeather, showEnvironmentalLight, showWeatherSeasonPicker,
        fogIntensity, setFogIntensity,
        timeOfDay, setTimeOfDay,
        dayOfYear, setDayOfYear,
        cloudCoverage, setCloudCoverage,
        cumulusEnabled, setCumulusEnabled,
        weatherPreset, setWeatherPreset,
        activeFixedCamera, setActiveFixedCamera,
        placedCameras, setPlacedCameras,
        setCameraHeight,
        cameraDataHeatmapActive, setCameraDataHeatmapActive,
        cameraDataTrackerActive, setCameraDataTrackerActive,
        cameraDataStats, setCameraDataStats,
        cameraAreaCubesVisible,
        cameraDataCalcActive, setCameraDataCalcActive,
        cameraDataCalcBaking, setCameraDataCalcBaking,
        cameraPathfindingWidgetOpen, setCameraPathfindingWidgetOpen,
        cctv1TrafficValue,
        cameraCosts,
        cameraDepthStatus, setCameraDepthStatus,
        cameraDepthPointCount, setCameraDepthPointCount,
        cameraDepthObstacleCount, setCameraDepthObstacleCount,
        cameraDepthPointsVisible, setCameraDepthPointsVisible,
        cameraDepthAreasVisible, setCameraDepthAreasVisible,
        soundAreasVisible,
        soundDataCalcActive, setSoundDataCalcActive,
        soundDataCalcBaking, setSoundDataCalcBaking,
        soundCostWidgetOpen, setSoundCostWidgetOpen,
        soundCosts,
        firstPersonLocation, setFirstPersonLocation,
        // Handlers
        handleCameraChange, handleFixedCameraChange,
        handlePhysicsChange,
        handleWeatherChange, handleWeatherToggle,
        handleEnvironmentalLightToggle, handleWeatherSeasonPickerToggle,
        handleFogIntensityChange, handleSpeedChange, movementSpeed, setMovementSpeed,
        cameraHeight, handleCameraHeightChange,
        handleTimeOfDayChange, handleDayOfYearChange, handleCloudCoverageChange, handleCumulusToggle, handleWeatherPresetChange,
        handleCctv1TrafficChange, handleCameraCostChange,
        handleCameraDataHeatmapToggle, handleCameraDataTrackerToggle,
        handleRemovePlacedCamera,
        handleCameraAreaCubesToggle, handleCameraDataCalcToggle,
        handleSoundAreasToggle, handleSoundDataCalcToggle, handleSoundCostChange,
        handleCameraDepthCapture, handleCameraDepthDetectObstacles,
        handleCameraDepthClear, handleCameraDepthTogglePoints, handleCameraDepthToggleAreas,
        cleanupDebounces,
        // CU-facing world-settings
        weather, setWeather, applyWeather,
        season, setSeason, applySeason,
        timeOfDayMinutes, setTimeOfDayMinutes, applyTimeOfDay,
    };
}
