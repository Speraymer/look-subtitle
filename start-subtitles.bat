@echo off
cd /d "%~dp0"
set PY=G:\Anaconda\python.exe

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if %errorlevel%==0 (
    echo Subtitle service is already running on 127.0.0.1:8765
    echo Refresh the course page to see subtitles.
    ping -n 3 127.0.0.1 >nul
    exit /b 0
)

echo Starting subtitle service...
start "" /min "%PY%" "look.py" capture
ping -n 4 127.0.0.1 >nul

powershell -NoProfile -Command "try { $r = Invoke-WebRequest 'http://127.0.0.1:8765/health' -UseBasicParsing -TimeoutSec 5; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1"
if %errorlevel%==0 (
    echo OK. Refresh the course page to see subtitles.
) else (
    echo Failed to start. Check capture.err.log
)
ping -n 3 127.0.0.1 >nul
