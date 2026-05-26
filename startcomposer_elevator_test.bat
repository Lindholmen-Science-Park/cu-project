@echo off
echo ========================================
echo Starting Composer (elevator test scene)
echo ========================================
echo.

REM Experimental: scene + assets under source/data/Assets/Elevator/ (gitignored).
set "YOUNITE_KIT_EXTRA_ARGS=--enable younite.elevator_test_extension"
call startcomposer.bat elevator_test_scene
IF DEFINED YOUNITE_KIT_EXTRA_ARGS set "YOUNITE_KIT_EXTRA_ARGS="
