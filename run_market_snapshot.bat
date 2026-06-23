@echo off
REM ======================================================================
REM  run_market_snapshot.bat
REM  Executive one-shot driver for the Sandhills Market Snapshot pipeline
REM  (Windows). Mirrors run_market_snapshot.sh: validates the environment
REM  and inputs, runs the pipeline with live status output, and confirms
REM  the NotebookLM-ready document was produced. Any problem stops with a
REM  loud alert and a non-zero exit code.
REM
REM  Usage:   run_market_snapshot.bat
REM ======================================================================
setlocal enabledelayedexpansion

REM Run from the folder this script lives in.
cd /d "%~dp0"

set "PY_SCRIPT=market_snapshot.py"
set "OUTPUT=notebooklm_source.md"

echo.
echo ######################################################################
echo #  SANDHILLS MARKET SNAPSHOT  --  executive pipeline runner          #
echo ######################################################################
echo.
echo ^>^> Working directory: %CD%
echo.

REM ---- 1. locate a Python interpreter ----------------------------------
echo ^>^> [1/4] Checking for Python ...
set "PY="
where python  >nul 2>&1 && set "PY=python"
if not defined PY ( where py >nul 2>&1 && set "PY=py" )
if not defined PY (
    echo ‼ ABORTING: Python is not installed or not on PATH. Install Python 3.8+ and retry. 1>&2
    exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo    Found: %%v

REM ---- 2. confirm pandas is importable ---------------------------------
echo ^>^> [2/4] Checking for required Python package 'pandas' ...
%PY% -c "import pandas" >nul 2>&1
if errorlevel 1 (
    echo    pandas not found -- attempting 'pip install pandas' ...
    %PY% -m pip install pandas
    if errorlevel 1 (
        echo ‼ ABORTING: Could not install pandas. Run '%PY% -m pip install pandas' manually. 1>&2
        exit /b 1
    )
)
echo    pandas is available.

REM ---- 3. verify input files -------------------------------------------
echo ^>^> [3/4] Validating input files ...
if not exist "%PY_SCRIPT%" (
    echo ‼ ABORTING: Pipeline script '%PY_SCRIPT%' is missing. 1>&2
    exit /b 1
)
for %%f in (inventory.csv webstats.csv market_trends.csv) do (
    if not exist "%%f" (
        echo ‼ ABORTING: Required input '%%f' was not found. ^(Was a source export renamed or moved?^) 1>&2
        exit /b 1
    )
    echo    OK  %%f
)

REM ---- 4. run the pipeline ---------------------------------------------
echo.
echo ^>^> [4/4] Running pipeline -- watch the live data validation below ...
echo ----------------------------------------------------------------------
%PY% "%PY_SCRIPT%"
if errorlevel 1 (
    echo ----------------------------------------------------------------------
    echo ‼ ABORTING: The pipeline reported an error ^(see above^). A source file's 1>&2
    echo   columns or format may have changed. The snapshot was NOT generated. 1>&2
    exit /b 1
)
echo ----------------------------------------------------------------------

if not exist "%OUTPUT%" (
    echo ‼ ABORTING: Pipeline finished but '%OUTPUT%' is missing. 1>&2
    exit /b 1
)

echo.
echo ######################################################################
echo #  SUCCESS                                                            #
echo ######################################################################
echo   Deliverable: %CD%\%OUTPUT%
echo.
echo   NEXT STEP: Upload '%OUTPUT%' to Google NotebookLM as a source,
echo   then chat with your live market snapshot immediately.
echo.
endlocal
