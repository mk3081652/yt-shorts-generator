@echo off
title Viral YouTube Shorts Creator Studio
color 0b

echo ================================================================
echo    VIRAL YOUTUBE SHORTS CREATOR STUDIO (100%% FREE ^& FAST)
echo ================================================================
echo  * Free Neural AI Voiceover (Edge-TTS)
echo  * High-Retention Word-by-Word Viral Subtitles
echo  * 1080x1920 9:16 Vertical HD Video Generation
echo  * Royalty-Free Background Music ^& Auto-Audio Ducking
echo  * YouTube Monetization SEO Kit (High CTR Titles ^& Tags)
echo ================================================================
echo.

:: Check python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.10+ from python.org and try again.
    pause
    exit /b 1
)

echo [1/2] Starting web server on http://localhost:8000 ...
echo [2/2] Opening Studio in your browser...

start "" http://localhost:8000

python -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
