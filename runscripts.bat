@echo off
echo ========================================
echo Running Post-Processing Scripts
echo ========================================
echo.

set "SCRIPTS_OK=0"
set "SCRIPTS_WARN=0"

REM --- Seasonal tree textures ---
echo [1] Generating seasonal tree textures...
python "%~dp0kit-app-template-main\source\data\Assets\Tools\generate_seasonal_textures.py"
if %ERRORLEVEL% neq 0 (
    echo     WARNING: Seasonal texture generation failed.
    echo     Fix:     pip install -r kit-app-template-main\source\data\Assets\Tools\requirements.txt
    echo              Then re-run: runscripts.bat
    set /a SCRIPTS_WARN+=1
) else (
    echo     OK: Seasonal textures generated.
    set /a SCRIPTS_OK+=1
)
echo.

REM --- Frost/snow terrain textures ---
echo [2] Generating frost terrain textures...
python "%~dp0kit-app-template-main\source\data\Assets\Tools\generate_frost_textures.py"
if %ERRORLEVEL% neq 0 (
    echo     WARNING: Frost texture generation failed.
    echo     Fix:     pip install -r kit-app-template-main\source\data\Assets\Tools\requirements.txt
    echo              Then re-run: runscripts.bat
    set /a SCRIPTS_WARN+=1
) else (
    echo     OK: Frost textures generated.
    set /a SCRIPTS_OK+=1
)
echo.

REM ---------------------------------------------------------------
REM Add future post-processing scripts here. Copy the block above
REM and change the number, description, and python command.
REM ---------------------------------------------------------------

echo ========================================
echo Post-Processing Summary: %SCRIPTS_OK% succeeded, %SCRIPTS_WARN% warnings
echo ========================================
