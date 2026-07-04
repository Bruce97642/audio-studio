@echo off
rem Drag-and-drop audio cleaner. File content is ASCII-only on purpose:
rem cmd.exe mis-parses non-ASCII batch files on zh-TW systems (cp950).
chcp 65001 >nul
if "%~1"=="" (
    echo Usage: drag audio files onto this icon to clean them.
    pause
    exit /b
)
:loop
if "%~1"=="" goto done
audio-studio clean "%~1"
shift
goto loop
:done
echo.
echo Done! Cleaned files are next to the originals.
pause
