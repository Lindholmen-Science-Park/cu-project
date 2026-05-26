@echo off
echo ========================================
echo Starting Younite Streaming (PRODUCTION Kit profile)
echo ========================================
echo.
echo Kit loads younite.usd_viewer_streaming_base.kit — production extensions only.
echo Web UI: same dev build as startstream.bat (swap for production web later).
echo.

REM Optional argument: scene name (without extension) to open from source/data/scenes
IF NOT "%~1"=="" (
    set "YOUNITE_SCENE_NAME=%~1"
    echo Scene argument detected: %YOUNITE_SCENE_NAME%
) ELSE (
    echo No scene argument provided. Defaulting to main_scene.usda
)
echo.

REM Load credentials from .env (kept out of version control)
if exist "%~dp0.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
        set "%%A=%%B"
    )
) else (
    echo WARNING: .env file not found — AI Agent credentials are not set.
    echo          Copy .env.example to .env and fill in the values.
)

REM Step 1: USD viewer streaming — prod kit (builds inside start_streaming_prod.bat)
echo Step 1: Starting USD Viewer Streaming (production extension set)...
cd kit-app-template-main
start "USD Viewer Streaming (Prod)" cmd /k "set AI_AGENT_API_URL=%AI_AGENT_API_URL%&& set AI_AGENT_USERNAME=%AI_AGENT_USERNAME%&& set AI_AGENT_PASSWORD=%AI_AGENT_PASSWORD%&& set AI_AGENT_LANGUAGE=%AI_AGENT_LANGUAGE%&& set AI_AGENT_DISCONNECT_GRACE=%AI_AGENT_DISCONNECT_GRACE%&& set CESIUM_ION_TOKEN=%CESIUM_ION_TOKEN%&& set TRAFIKLAB_GTFS_RT_KEY=%TRAFIKLAB_GTFS_RT_KEY%&& set TRAFIKLAB_GTFS_SWEDEN3_RT_KEY=%TRAFIKLAB_GTFS_SWEDEN3_RT_KEY%&& set SAMTRAFIKEN_GTFS_RT_KEY=%SAMTRAFIKEN_GTFS_RT_KEY%&& set TRANSIT_LIVE_GTFS_RT_OPERATOR=%TRANSIT_LIVE_GTFS_RT_OPERATOR%&& set TRANSIT_LIVE_VEHICLEPOSITIONS_URL=%TRANSIT_LIVE_VEHICLEPOSITIONS_URL%&& set TRANSIT_LIVE_RADIUS_KM=%TRANSIT_LIVE_RADIUS_KM%&& set TRANSIT_LIVE_CENTER_LAT=%TRANSIT_LIVE_CENTER_LAT%&& set TRANSIT_LIVE_CENTER_LON=%TRANSIT_LIVE_CENTER_LON%&& set TRANSIT_LIVE_POLL_SEC=%TRANSIT_LIVE_POLL_SEC%&& set TRANSIT_LIVE_MAX_VEHICLES=%TRANSIT_LIVE_MAX_VEHICLES%&& set TRANSIT_LIVE_SCENE_RADIUS_CM=%TRANSIT_LIVE_SCENE_RADIUS_CM%&& set TRANSIT_LIVE_OSM_GRID_CELL_CM=%TRANSIT_LIVE_OSM_GRID_CELL_CM%&& set TRANSIT_LIVE_SOURCE=%TRANSIT_LIVE_SOURCE%&& set VASTTRAFIK_CLIENT_ID=%VASTTRAFIK_CLIENT_ID%&& set VASTTRAFIK_CLIENT_SECRET=%VASTTRAFIK_CLIENT_SECRET%&& set VASTTRAFIK_PLANERA_BASE=%VASTTRAFIK_PLANERA_BASE%&& set TRANSIT_LIVE_VEHICLE_ALT_OFFSET_M=%TRANSIT_LIVE_VEHICLE_ALT_OFFSET_M%&& set TRANSIT_LIVE_VEHICLE_WGS84_HEIGHT_M=%TRANSIT_LIVE_VEHICLE_WGS84_HEIGHT_M%&& set TRANSIT_LIVE_SNAP_TO_GROUND=%TRANSIT_LIVE_SNAP_TO_GROUND%&& set TRANSIT_LIVE_VEHICLE_Y_FROM_OSM=%TRANSIT_LIVE_VEHICLE_Y_FROM_OSM%&& set TRANSIT_LIVE_VEHICLE_OSM_Y_OFFSET_CM=%TRANSIT_LIVE_VEHICLE_OSM_Y_OFFSET_CM%&& set TRANSIT_LIVE_VEHICLE_POST_Y_LIFT_CM=%TRANSIT_LIVE_VEHICLE_POST_Y_LIFT_CM%&& set TRANSIT_LIVE_VEHICLE_CLEARANCE_CM=%TRANSIT_LIVE_VEHICLE_CLEARANCE_CM%&& set TRANSIT_LIVE_MOVE_BLEND_SEC=%TRANSIT_LIVE_MOVE_BLEND_SEC%&& set TRANSIT_LIVE_MOVE_BLEND_MAX_JUMP_CM=%TRANSIT_LIVE_MOVE_BLEND_MAX_JUMP_CM%&& set TRANSIT_LIVE_OSM_ROUTE_BETWEEN_UPDATES=%TRANSIT_LIVE_OSM_ROUTE_BETWEEN_UPDATES%&& set TRANSIT_LIVE_OSM_ROUTE_MODE=%TRANSIT_LIVE_OSM_ROUTE_MODE%&& set TRANSIT_LIVE_OSM_ROUTE_MAX_PER_POLL=%TRANSIT_LIVE_OSM_ROUTE_MAX_PER_POLL%&& set TRANSIT_LIVE_OSM_MAIN_COMPONENT_ONLY=%TRANSIT_LIVE_OSM_MAIN_COMPONENT_ONLY%&& set TRANSIT_LIVE_OSM_GRAPH_PATH=%TRANSIT_LIVE_OSM_GRAPH_PATH%&& set TRANSIT_LIVE_VASTTRAFIK_BBOX_RADIUS_KM=%TRANSIT_LIVE_VASTTRAFIK_BBOX_RADIUS_KM%&& set NUCLEUS_SPATIAL_SOUNDS_FOLDER=%NUCLEUS_SPATIAL_SOUNDS_FOLDER%&& start_streaming_prod.bat"
cd ..
echo.

REM Step 2: Build web-app (same as startstream.bat for now)
echo Step 2: Building Web App...
cd web-viewer-sample-main
call npm run build
if %ERRORLEVEL% neq 0 (
    echo ERROR: Web app build failed!
    pause
    exit /b 1
)
echo SUCCESS: Web app build completed successfully!
echo.

REM Step 3: Start web-app dev server
echo Step 3: Starting Web App...
start "Web Viewer" cmd /k "npm run dev"
cd ..
echo.

echo ========================================
echo SUCCESS: Production Kit + web dev viewer started
echo ========================================
echo.
echo USD Viewer Streaming (Prod): production Kit profile
echo Web Viewer: Browser interface (dev build — replace for real prod later)
echo.
echo Press any key to exit...
pause >nul

IF DEFINED YOUNITE_SCENE_NAME (
    set "YOUNITE_SCENE_NAME="
)
