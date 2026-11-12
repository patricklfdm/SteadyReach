@echo off
setlocal
pushd "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" workflow.py doctor --full --require-delivery --brief --output status/doctor.json
set "CheckExit=%ERRORLEVEL%"
goto finished
:missing
echo Run setup_workflow.cmd first. No environment was changed.
set "CheckExit=2"
:finished
if /I not "%~1"=="--no-pause" pause
popd
endlocal & exit /b %CheckExit%
