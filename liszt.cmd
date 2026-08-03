@echo off
rem Liszt command dispatcher for Windows. Run "liszt help" for the command list.
setlocal

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"

set "CMD=%~1"
if "%CMD%"=="" set "CMD=help"

rem Collect everything after the command so it can be passed through.
set "ARGS="
shift
:collect
if "%~1"=="" goto dispatch
set ARGS=%ARGS% %1
shift
goto collect

:dispatch
if /i "%CMD%"=="help"   goto help
if /i "%CMD%"=="-h"     goto help
if /i "%CMD%"=="--help" goto help

if not exist "%VENV_PY%" (
  echo No virtual environment found at .venv. Run install.ps1 first: powershell -ExecutionPolicy Bypass -File install.ps1
  exit /b 1
)

if /i "%CMD%"=="new"         ("%VENV_PY%" "%ROOT%tools\new_scenario.py" %ARGS% & exit /b)
if /i "%CMD%"=="validate"    ("%VENV_PY%" "%ROOT%tools\validate.py" %ARGS% & exit /b)
if /i "%CMD%"=="strict"      ("%VENV_PY%" "%ROOT%tools\validate.py" --strict %ARGS% & exit /b)
if /i "%CMD%"=="publishable" ("%VENV_PY%" "%ROOT%tools\validate.py" --publishable --strict %ARGS% & exit /b)
if /i "%CMD%"=="coverage"    ("%VENV_PY%" "%ROOT%tools\coverage.py" %ARGS% & exit /b)
if /i "%CMD%"=="viewer"      ("%VENV_PY%" "%ROOT%tools\build_viewer.py" %ARGS% & exit /b)
if /i "%CMD%"=="serve"       ("%VENV_PY%" "%ROOT%tools\serve.py" %ARGS% & exit /b)
if /i "%CMD%"=="session"     ("%VENV_PY%" "%ROOT%tools\apply_session.py" %ARGS% & exit /b)
if /i "%CMD%"=="publish"     ("%VENV_PY%" "%ROOT%tools\publish_library.py" %ARGS% & exit /b)
if /i "%CMD%"=="pin"         ("%VENV_PY%" "%ROOT%tools\pin_frameworks.py" %ARGS% & exit /b)
if /i "%CMD%"=="verify-pin"  ("%VENV_PY%" "%ROOT%tools\pin_frameworks.py" --verify %ARGS% & exit /b)
if /i "%CMD%"=="doctor"      ("%VENV_PY%" "%ROOT%tools\doctor.py" %ARGS% & exit /b)
if /i "%CMD%"=="render"      goto render
if /i "%CMD%"=="update"      goto update

echo unknown command: %CMD%
call :help
exit /b 2

:render
"%VENV_PY%" -c "import pptx" >nul 2>&1
if errorlevel 1 (
  echo The render command needs the deck packages, which are not installed.
  echo Add them with: powershell -ExecutionPolicy Bypass -File install.ps1 -WithDeck
  exit /b 1
)
"%VENV_PY%" "%ROOT%tools\render_slides.py" %ARGS%
exit /b

:update
echo Pulling the latest changes ...
git -C "%ROOT%." pull --ff-only
if errorlevel 1 exit /b 1
echo Refreshing the packages ...
"%VENV_PY%" -m pip install --quiet --no-cache-dir -r "%ROOT%requirements\base.txt"
if errorlevel 1 exit /b 1
"%VENV_PY%" -c "import pptx" >nul 2>&1
if not errorlevel 1 (
  "%VENV_PY%" -m pip install --quiet --no-cache-dir -r "%ROOT%requirements\deck.txt"
  if errorlevel 1 exit /b 1
)
echo Validating ...
"%VENV_PY%" "%ROOT%tools\validate.py"
exit /b

:help
echo usage: liszt ^<command^> [options]
echo.
echo   new           start a new scenario record, or a use case with --use-case
echo   validate      check every record against the schema and the quality bar
echo   strict        like validate, but warnings fail too
echo   publishable   check only records at status: published
echo   coverage      coverage, exposure, and maturity rollup
echo   viewer        rebuild the static viewer page and liszt-data.json
echo   serve         rebuild the viewer, then serve it on a local address
echo   session       apply a session file back into the records
echo   render        rebuild the slide deck, needs the deck packages
echo   publish       write the records out as Markdown pages
echo   pin           vendor the pinned framework artifacts, needs network
echo   verify-pin    re-check the pinned artifact checksums, no network
echo   doctor        check this machine and explain anything that is off
echo   update        pull the latest changes, refresh the packages, validate
echo   help          show this list
echo.
echo Anything after the command is passed through to the tool it runs.
exit /b 0
