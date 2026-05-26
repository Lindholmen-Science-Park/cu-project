@echo off
echo ========================================
echo Cleaning Kit Build Artifacts
echo ========================================
echo.
echo This script removes cached build artifacts so the next
echo startstream.bat / startcomposer.bat performs a fresh build.
echo.
echo Required after:
echo   - Pulling a Kit SDK version update from git
echo   - Changing .kit profile dependencies
echo   - Troubleshooting extension resolution failures
echo.

set "KIT_DIR=%~dp0kit-app-template-main"

if not exist "%KIT_DIR%" (
    echo ERROR: kit-app-template-main folder not found.
    echo Run this script from the project root.
    pause
    exit /b 1
)

echo Folders to remove:
if exist "%KIT_DIR%\_build" (echo   _build  [FOUND]) else (echo   _build  [not present])
if exist "%KIT_DIR%\_repo"  (echo   _repo   [FOUND]) else (echo   _repo   [not present])
echo.

set /p CONFIRM="Proceed with clean? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo Cancelled.
    pause
    exit /b 0
)

echo.
if exist "%KIT_DIR%\_build" (
    echo Removing _build...
    rmdir /s /q "%KIT_DIR%\_build"
    if errorlevel 1 (
        echo WARNING: Could not fully remove _build. Close any Kit processes and retry.
    ) else (
        echo   _build removed.
    )
) else (
    echo   _build already clean.
)

if exist "%KIT_DIR%\_repo" (
    echo Removing _repo...
    rmdir /s /q "%KIT_DIR%\_repo"
    if errorlevel 1 (
        echo WARNING: Could not fully remove _repo. Close any Kit processes and retry.
    ) else (
        echo   _repo removed.
    )
) else (
    echo   _repo already clean.
)

echo.
echo ========================================
echo Clean complete. Run startstream.bat to rebuild.
echo ========================================
pause
