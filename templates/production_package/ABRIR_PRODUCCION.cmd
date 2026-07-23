@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "PRODUCTION_DIR=%~dp0"
set "PACKAGE_DIR=%PRODUCTION_DIR%package"
set "MANIFEST_PATH=%PACKAGE_DIR%\manifest.json"

if defined BARCHARTSTUDIO_ROOT (
    for %%I in ("%BARCHARTSTUDIO_ROOT%") do set "STUDIO_ROOT=%%~fI"
) else (
    for %%I in ("%PRODUCTION_DIR%..\..") do set "STUDIO_ROOT=%%~fI"
)

if not exist "%STUDIO_ROOT%\" (
    echo ERROR: BarChartStudio root was not found: "%STUDIO_ROOT%" 1>&2
    exit /b 1
)

set "OPEN_PACKAGE_MODULE=%STUDIO_ROOT%\src\tools\open_production_package.py"
if not exist "%OPEN_PACKAGE_MODULE%" (
    echo ERROR: Production package command was not found: "%OPEN_PACKAGE_MODULE%" 1>&2
    exit /b 1
)

if defined BARCHARTSTUDIO_PYTHON (
    for %%I in ("%BARCHARTSTUDIO_PYTHON%") do set "PYTHON_EXE=%%~fI"
) else (
    set "PYTHON_EXE=%STUDIO_ROOT%\.venv\Scripts\python.exe"
)

if not exist "%PYTHON_EXE%" (
    echo ERROR: BarChartStudio Python was not found: "%PYTHON_EXE%" 1>&2
    exit /b 1
)

if not exist "%MANIFEST_PATH%" (
    echo ERROR: Production package manifest was not found: "%MANIFEST_PATH%" 1>&2
    exit /b 1
)

pushd "%STUDIO_ROOT%" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Could not enter BarChartStudio root: "%STUDIO_ROOT%" 1>&2
    exit /b 1
)

"%PYTHON_EXE%" -m src.tools.open_production_package "%PACKAGE_DIR%" --root "%STUDIO_ROOT%" %*
set "PYTHON_EXIT_CODE=%ERRORLEVEL%"

popd
endlocal & exit /b %PYTHON_EXIT_CODE%
