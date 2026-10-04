@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 goto location_error
if exist "venv\Scripts\python.exe" goto use_venv
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto use_python
echo Python 3.10+ tidak ditemukan. Pasang dari https://www.python.org/downloads/windows/
echo Aktifkan launcher py atau Add python.exe to PATH, lalu jalankan ulang.
set "ALI_LICENSE_EXIT=1"
goto cleanup

:use_venv
"venv\Scripts\python.exe" -B "scripts\license_cli.py"
goto result

:use_py
py -3 -B "scripts\license_cli.py"
goto result

:use_python
python -B "scripts\license_cli.py"
goto result

:result
set "ALI_LICENSE_EXIT=%errorlevel%"
:cleanup
popd
if not "%ALI_LICENSE_NO_PAUSE%"=="1" pause
endlocal & exit /b %ALI_LICENSE_EXIT%

:location_error
echo Folder repository tidak dapat dibuka. Tidak ada berkas dibuat.
if not "%ALI_LICENSE_NO_PAUSE%"=="1" pause
endlocal & exit /b 1
