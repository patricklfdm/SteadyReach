@echo off
setlocal
pushd "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" goto local
call setup_workflow.cmd --no-pause
if not exist ".venv\Scripts\python.exe" goto failed
:local
".venv\Scripts\python.exe" app.py serve
goto done
:failed
echo Environment preparation did not complete. See status\setup.
:done
pause
popd
endlocal
