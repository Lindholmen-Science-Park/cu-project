@echo off
echo ========================================
echo Starting Younite Streaming Services (Viewer Only)
echo ========================================
echo.

REM Optional argument: scene name (without extension) to open from source/data/scenes
IF NOT "%~1"=="" (
    set "YOUNITE_SCENE_NAME=%~1"
    echo Scene argument detected: %YOUNITE_SCENE_NAME%
) ELSE (
    echo No scene argument provided. Defaulting to main_scene.usda
)
echo.

REM Step 0: Check if Ollama is running (non-blocking)
echo Step 0: Checking Ollama service...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo WARNING: Ollama does not appear to be running!
    echo.
    echo The app will start, but AI chat features will not work.
    echo.
    echo To enable AI chat:
    echo   1. Install Ollama from https://ollama.ai
    echo   2. Start Ollama (it runs as a service after installation)
    echo   3. Train your model: starttraining.bat ollama llama3.1
    echo.
    echo Continuing with app startup...
    echo.
) else (
    echo SUCCESS: Ollama is running - AI chat will be available
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

REM Step 1: Start USD viewer streaming (builds and launches)
echo Step 1: Starting USD Viewer Streaming with Geometry Streaming...
cd kit-app-template-main
start "USD Viewer Streaming" cmd /k "set AI_AGENT_API_URL=%AI_AGENT_API_URL%&& set AI_AGENT_USERNAME=%AI_AGENT_USERNAME%&& set AI_AGENT_PASSWORD=%AI_AGENT_PASSWORD%&& set AI_AGENT_LANGUAGE=%AI_AGENT_LANGUAGE%&& set AI_AGENT_DISCONNECT_GRACE=%AI_AGENT_DISCONNECT_GRACE%&& set CESIUM_ION_TOKEN=%CESIUM_ION_TOKEN%&& set TRAFIKLAB_GTFS_RT_KEY=%TRAFIKLAB_GTFS_RT_KEY%&& set TRAFIKLAB_GTFS_SWEDEN3_RT_KEY=%TRAFIKLAB_GTFS_SWEDEN3_RT_KEY%&& set SAMTRAFIKEN_GTFS_RT_KEY=%SAMTRAFIKEN_GTFS_RT_KEY%&& set TRANSIT_LIVE_GTFS_RT_OPERATOR=%TRANSIT_LIVE_GTFS_RT_OPERATOR%&& set TRANSIT_LIVE_VEHICLEPOSITIONS_URL=%TRANSIT_LIVE_VEHICLEPOSITIONS_URL%&& set TRANSIT_LIVE_RADIUS_KM=%TRANSIT_LIVE_RADIUS_KM%&& set TRANSIT_LIVE_CENTER_LAT=%TRANSIT_LIVE_CENTER_LAT%&& set TRANSIT_LIVE_CENTER_LON=%TRANSIT_LIVE_CENTER_LON%&& set TRANSIT_LIVE_POLL_SEC=%TRANSIT_LIVE_POLL_SEC%&& set TRANSIT_LIVE_MAX_VEHICLES=%TRANSIT_LIVE_MAX_VEHICLES%&& set TRANSIT_LIVE_SCENE_RADIUS_CM=%TRANSIT_LIVE_SCENE_RADIUS_CM%&& set TRANSIT_LIVE_OSM_GRID_CELL_CM=%TRANSIT_LIVE_OSM_GRID_CELL_CM%&& set TRANSIT_LIVE_SOURCE=%TRANSIT_LIVE_SOURCE%&& set VASTTRAFIK_CLIENT_ID=%VASTTRAFIK_CLIENT_ID%&& set VASTTRAFIK_CLIENT_SECRET=%VASTTRAFIK_CLIENT_SECRET%&& set VASTTRAFIK_PLANERA_BASE=%VASTTRAFIK_PLANERA_BASE%&& set TRANSIT_LIVE_VEHICLE_ALT_OFFSET_M=%TRANSIT_LIVE_VEHICLE_ALT_OFFSET_M%&& set TRANSIT_LIVE_VEHICLE_WGS84_HEIGHT_M=%TRANSIT_LIVE_VEHICLE_WGS84_HEIGHT_M%&& set TRANSIT_LIVE_SNAP_TO_GROUND=%TRANSIT_LIVE_SNAP_TO_GROUND%&& set TRANSIT_LIVE_VEHICLE_Y_FROM_OSM=%TRANSIT_LIVE_VEHICLE_Y_FROM_OSM%&& set TRANSIT_LIVE_VEHICLE_OSM_Y_OFFSET_CM=%TRANSIT_LIVE_VEHICLE_OSM_Y_OFFSET_CM%&& set TRANSIT_LIVE_VEHICLE_POST_Y_LIFT_CM=%TRANSIT_LIVE_VEHICLE_POST_Y_LIFT_CM%&& set TRANSIT_LIVE_VEHICLE_CLEARANCE_CM=%TRANSIT_LIVE_VEHICLE_CLEARANCE_CM%&& set TRANSIT_LIVE_MOVE_BLEND_SEC=%TRANSIT_LIVE_MOVE_BLEND_SEC%&& set TRANSIT_LIVE_MOVE_BLEND_MAX_JUMP_CM=%TRANSIT_LIVE_MOVE_BLEND_MAX_JUMP_CM%&& set TRANSIT_LIVE_OSM_ROUTE_BETWEEN_UPDATES=%TRANSIT_LIVE_OSM_ROUTE_BETWEEN_UPDATES%&& set TRANSIT_LIVE_OSM_ROUTE_MODE=%TRANSIT_LIVE_OSM_ROUTE_MODE%&& set TRANSIT_LIVE_OSM_ROUTE_MAX_PER_POLL=%TRANSIT_LIVE_OSM_ROUTE_MAX_PER_POLL%&& set TRANSIT_LIVE_OSM_MAIN_COMPONENT_ONLY=%TRANSIT_LIVE_OSM_MAIN_COMPONENT_ONLY%&& set TRANSIT_LIVE_OSM_GRAPH_PATH=%TRANSIT_LIVE_OSM_GRAPH_PATH%&& set TRANSIT_LIVE_VASTTRAFIK_BBOX_RADIUS_KM=%TRANSIT_LIVE_VASTTRAFIK_BBOX_RADIUS_KM%&& set NUCLEUS_SPATIAL_SOUNDS_FOLDER=%NUCLEUS_SPATIAL_SOUNDS_FOLDER%&& start_streaming.bat"
cd ..
echo SUCCESS: USD Viewer Streaming with Geometry Streaming starting...
echo.

REM Step 2: Build web-app
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

REM Step 3: Start web-app
echo Step 3: Starting Web App...
start "Web Viewer" cmd /k "npm run dev"
cd ..
echo SUCCESS: Web Viewer starting...
echo.

echo ========================================
echo SUCCESS: Streaming services started successfully!
echo ========================================
echo.
echo Check the new command windows that opened:
echo USD Viewer Streaming: Lightweight streaming server with Geometry Streaming enabled
echo Web Viewer: Browser interface to view the streaming content
echo.
echo NOTE: USD Composer was skipped - this is viewer-only mode
echo Geometry Streaming is now enabled by default for optimal performance
echo.
echo Press any key to exit...
pause >nul

REM Clean up environment variable in current shell
IF DEFINED YOUNITE_SCENE_NAME (
    set "YOUNITE_SCENE_NAME="
)
