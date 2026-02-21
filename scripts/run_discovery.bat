@echo off
REM Blender Geometry Nodes Discovery - Windows Launcher
REM
REM Usage: run_discovery.bat [path_to_blender]
REM Example: run_discovery.bat "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
REM
REM If no path provided, tries common install locations.

setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..

REM Use provided path or try to find Blender
if not "%~1"=="" (
    set BLENDER=%~1
) else (
    REM Hardcoded default path
    if exist "C:\Tools\Blender\stable\blender-4.5.6-lts.a78963ed6435\blender.exe" (
        set BLENDER=C:\Tools\Blender\stable\blender-4.5.6-lts.a78963ed6435\blender.exe
    ) else if exist "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe" (
        set BLENDER=C:\Program Files\Blender Foundation\Blender 5.0\blender.exe
    ) else if exist "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe" (
        set BLENDER=C:\Program Files\Blender Foundation\Blender 4.5\blender.exe
    ) else (
        echo ERROR: Could not find Blender. Please provide the path as an argument.
        echo Usage: run_discovery.bat "C:\path\to\blender.exe"
        exit /b 1
    )
)

echo Using Blender: %BLENDER%
echo.

REM Phase 1: Node Catalog Discovery
echo ================================================
echo Phase 1: Discovering geometry node types...
echo ================================================
"%BLENDER%" --background --factory-startup --python "%PROJECT_DIR%\discovery\discover_nodes.py"

if %ERRORLEVEL% NEQ 0 (
    echo Phase 1 failed!
    exit /b 1
)

echo.

REM Phase 2: Connection Compatibility Matrix
echo ================================================
echo Phase 2: Testing connection compatibility...
echo ================================================
"%BLENDER%" --background --factory-startup --python "%PROJECT_DIR%\discovery\test_connections.py"

if %ERRORLEVEL% NEQ 0 (
    echo Phase 2 failed!
    exit /b 1
)

echo.

REM Phase 2b: Node Domain Classification (runs on Python, no Blender needed)
echo ================================================
echo Phase 2b: Classifying nodes by domain...
echo ================================================
python "%PROJECT_DIR%\discovery\classify_nodes.py"

if %ERRORLEVEL% NEQ 0 (
    echo Phase 2b failed!
    exit /b 1
)

echo.

REM Phase 3: Pattern Verification
echo ================================================
echo Phase 3: Verifying known-good patterns...
echo ================================================
"%BLENDER%" --background --factory-startup --python "%PROJECT_DIR%\patterns\verify_patterns.py"

if %ERRORLEVEL% NEQ 0 (
    echo Phase 3 had failures!
    exit /b 1
)

echo.

REM Phase 4: Automated Exploration (runs major domains)
echo ================================================
echo Phase 4: Exploring node behaviors...
echo ================================================
set DOMAINS=mesh curve geometry math input attribute instance pointcloud utility selection material field volume uv io greasepencil

for %%D in (%DOMAINS%) do (
    echo Exploring domain: %%D
    python "%PROJECT_DIR%\explorer\run_explorer.py" --domain %%D --batch-size 30
    echo.
)

echo.

REM Phase 5: Knowledge Base Assembly (runs on Python, no Blender needed)
echo ================================================
echo Phase 5: Assembling knowledge base...
echo ================================================
python "%PROJECT_DIR%\knowledge\build_kb.py"

if %ERRORLEVEL% NEQ 0 (
    echo Phase 5 failed!
    exit /b 1
)

echo.
echo ================================================
echo All phases complete!
echo Output files:
echo   discovery/node_catalog.json
echo   discovery/connection_matrix.json
echo   discovery/node_classification.json
echo   patterns/pattern_catalog.json
echo   explorer/results/*_combined.json
echo   knowledge/blender_geonodes_kb.json
echo.
echo Query the knowledge base:
echo   python knowledge/query.py --stats
echo   python knowledge/query.py "subdivide"
echo   python knowledge/query.py --modified
echo ================================================
