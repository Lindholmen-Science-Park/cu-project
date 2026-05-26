@echo off
echo ========================================
echo Starting Younite AI Training
echo ========================================
echo.

REM Navigate to project directory
cd kit-app-template-main

REM Check if Python is available
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ and add it to your PATH
    pause
    exit /b 1
)

REM Check if training script exists
if not exist "tools\ai_training\train.py" (
    echo ERROR: Training script not found at tools\ai_training\train.py
    pause
    exit /b 1
)

REM Default to Ollama training
set PROVIDER=ollama
set MODEL=llama3.1

REM Check command line arguments (case-insensitive)
set ARG1=%1
REM If ARG1 is empty or matches script name, treat as no arguments (use default)
if "%ARG1%"=="" goto :skip_args
if /i "%ARG1%"=="starttraining" goto :skip_args
if /i "%ARG1%"=="starttraining.bat" goto :skip_args

REM Check if it's a valid provider argument
if /i "%ARG1%"=="openai" (
    set PROVIDER=openai
    set MODEL=gpt-4o-mini
    echo Using OpenAI provider with model: %MODEL%
    echo.
    echo NOTE: Make sure OPENAI_API_KEY environment variable is set
    echo       Set it with: set OPENAI_API_KEY=your_key_here
    echo.
    goto :skip_args
)
if /i "%ARG1%"=="ollama" (
    set PROVIDER=ollama
    if not "%2"=="" set MODEL=%2
    echo Using Ollama provider with model: %MODEL%
    echo.
    echo NOTE: Make sure Ollama is installed and running
    echo       Download from: https://ollama.ai
    echo.
    goto :skip_args
)

REM If we get here, ARG1 is not empty and not a valid provider
echo ========================================
echo ERROR: Invalid provider argument: "%ARG1%"
echo ========================================
echo.
echo Usage: starttraining.bat [openai^|ollama] [model_name]
echo.
echo Examples:
echo   starttraining.bat           - Train with Ollama (default)
echo   starttraining.bat ollama     - Train with Ollama
echo   starttraining.bat ollama llama3.2  - Train with specific Ollama model
echo   starttraining.bat openai     - Train with OpenAI
echo.
echo Note: Provider name is case-insensitive (OpenAI, openai, OLLAMA, ollama all work)
echo.
pause
exit /b 1

:skip_args

echo Starting training with provider: %PROVIDER%
echo Model: %MODEL%
echo.

REM Run the training script
python tools\ai_training\train.py --provider %PROVIDER% --model %MODEL%

if %ERRORLEVEL% neq 0 (
    echo.
    echo ========================================
    echo ERROR: Training failed!
    echo ========================================
    pause
    exit /b 1
)

echo.
echo ========================================
echo Training completed successfully!
echo ========================================
echo.
echo Next steps:
if "%PROVIDER%"=="ollama" (
    echo 1. Test your model: ollama run %MODEL%-younite
    echo 2. Set environment variable: set MODEL=%MODEL%-younite
    echo 3. Restart your application to use the trained model
) else (
    echo 1. Wait for OpenAI fine-tuning to complete (check status at platform.openai.com)
    echo 2. Once complete, set environment variable: set MODEL=ft:gpt-4o-mini-...
    echo 3. Restart your application to use the trained model
)
echo.
pause

