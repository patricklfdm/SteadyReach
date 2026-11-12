@echo off
setlocal
pushd "%~dp0"
set "HECRAS_SETUP_ROOT=%CD%"
set "PYTHONUTF8=1"
set "PYTHONNOUSERSITE=1"
set "SetupNoPause="
for %%A in (%*) do if /I "%%~A"=="--no-pause" set "SetupNoPause=1"
if exist ".venv\Scripts\python.exe" goto existing
if exist ".venv" goto incomplete
echo Preparing checkout-local Python. This may take several minutes.
echo No administrator rights or security-policy changes are requested.
powershell.exe -NoProfile -Command ^
 "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; $root=$env:HECRAS_SETUP_ROOT; $trace=$false; try {" ^
 "function Assert-Hash($path,$expected) { $h=[Security.Cryptography.SHA256]::Create(); $s=[IO.File]::OpenRead($path); try { $actual=[BitConverter]::ToString($h.ComputeHash($s)).Replace('-','').ToLower() } finally { $s.Dispose(); $h.Dispose() }; if ($actual -ne $expected) { throw ('Hash mismatch; retained: '+$path) } };" ^
 "$logs=Join-Path $root 'status\setup'; New-Item -ItemType Directory -Force $logs | Out-Null; Start-Transcript -Path (Join-Path $logs ('python_'+[guid]::NewGuid().ToString('N')+'.log')) | Out-Null; $trace=$true;" ^
 "$spec=(Get-Content -LiteralPath (Join-Path $root 'scripts\setup_downloads.json') -Raw | ConvertFrom-Json).uv; $downloads=Join-Path $root '.tools\downloads'; New-Item -ItemType Directory -Force $downloads | Out-Null; $zip=Join-Path $downloads $spec.name;" ^
 "if (-not (Test-Path -LiteralPath $zip)) { $part=$zip+'.'+[guid]::NewGuid().ToString('N')+'.partial'; Invoke-WebRequest -UseBasicParsing -Uri $spec.url -OutFile $part; Assert-Hash $part $spec.sha256; Move-Item -LiteralPath $part -Destination $zip };" ^
 "Assert-Hash $zip $spec.sha256; $stage=Join-Path $root ('.tools\setup_staging\uv_'+[guid]::NewGuid().ToString('N')); Add-Type -AssemblyName System.IO.Compression.FileSystem; [IO.Compression.ZipFile]::ExtractToDirectory($zip,$stage); $uv=Join-Path $stage 'uv.exe';" ^
 "$env:UV_PYTHON_INSTALL_DIR=Join-Path $root '.tools\python'; $env:UV_CACHE_DIR=Join-Path $root '.tools\uv_cache'; & $uv --no-config --system-certs python install 3.12.14 --no-bin --no-registry; if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' };" ^
 "$python=(& $uv --no-config python find --managed-python 3.12.14).Trim(); if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python)) { throw 'Python lookup failed' }; & $python -m venv (Join-Path $root '.venv'); if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }; Stop-Transcript | Out-Null; exit 0" ^
 "} catch { Write-Host $_; if ($trace) { Stop-Transcript | Out-Null }; exit 2 }"
if errorlevel 1 goto failed
goto existing
:existing
".venv\Scripts\python.exe" scripts\setup_windows.py %*
set "SetupExit=%ERRORLEVEL%"
goto finished
:incomplete
echo Existing .venv is incomplete. It was preserved. See docs\WINDOWS_SETUP_EN.md.
:failed
set "SetupExit=2"
echo Setup stopped. Keep status\setup logs. See docs\WINDOWS_SETUP_EN.md.
:finished
if not defined SetupNoPause pause
popd
endlocal & exit /b %SetupExit%
