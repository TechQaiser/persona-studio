@echo off
REM ============================================================
REM  Persona - one-click launcher
REM  Double-click this file to start the engine API + dashboard
REM  and open the web console in your browser.
REM ============================================================
setlocal EnableDelayedExpansion
title Persona launcher
cd /d "%~dp0"

echo(
echo   ====================================================
echo      PERSONA  -  starting up
echo   ====================================================
echo(

REM ---- 1. Find Python ---------------------------------------
set "PY="
where python  >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py"
if not defined PY (
  echo   [X] Python was not found.
  echo       Install Python 3.9+ from https://www.python.org/downloads/
  echo       and tick "Add python.exe to PATH" during setup, then re-run this file.
  echo(
  pause
  exit /b 1
)
echo   [ok] Python found: %PY%

REM ---- 2. Find Node --------------------------------------------
where node >nul 2>&1
if errorlevel 1 (
  echo   [X] Node.js was not found.
  echo       Install Node.js 18+ from https://nodejs.org/ then re-run this file.
  echo(
  pause
  exit /b 1
)
echo   [ok] Node.js found
echo(

REM ---- 3. First-run setup (only once) --------------------------
if not exist "%~dp0.persona_setup_done" (
  echo   First run detected - installing dependencies. This can take a few minutes...
  echo(

  echo   [1/3] Installing the engine ^(Python^)...
  pushd "%~dp0engine"
  %PY% -m pip install -e ".[api,launch]"
  if errorlevel 1 (
    echo   [X] Engine install failed. See the messages above.
    popd & pause & exit /b 1
  )
  echo(
  echo   [2/3] Downloading the Chromium browser for launches...
  %PY% -m playwright install chromium
  popd
  echo(

  echo   [3/3] Installing the dashboard ^(Node^)...
  pushd "%~dp0dashboard"
  call npm install
  if errorlevel 1 (
    echo   [X] Dashboard install failed. See the messages above.
    popd & pause & exit /b 1
  )
  popd

  > "%~dp0.persona_setup_done" echo done
  echo(
  echo   [ok] Setup complete.
  echo(
) else (
  echo   [ok] Dependencies already installed ^(delete .persona_setup_done to re-run setup^).
  echo(
)

REM ---- 3b. Choose the default engine for NEW profiles ---------
echo   Which browser engine should NEW profiles use by default?
echo(
echo     [1] CloakBrowser   (recommended - strongest stealth)   ^<-- default
echo     [2] Camoufox       (patched Firefox)
echo     [3] Patchright     (patched Playwright)
echo     [4] Playwright     (built-in, always works)
echo     [Enter] keep the current setting
echo(
set "ENGCHOICE="
set /p "ENGCHOICE=  Type 1-4 and press Enter (or just Enter to skip): "

set "ENGINE="
if "%ENGCHOICE%"=="1" set "ENGINE=cloak"
if "%ENGCHOICE%"=="2" set "ENGINE=camoufox"
if "%ENGCHOICE%"=="3" set "ENGINE=patchright"
if "%ENGCHOICE%"=="4" set "ENGINE=playwright"

if defined ENGINE (
  echo(
  echo   Setting default engine to "%ENGINE%" ...
  pushd "%~dp0engine"
  %PY% -m persona default-engine %ENGINE%
  popd
) else (
  echo(
  echo   Keeping the current default engine.
)
echo(

REM ---- 4. Start the engine API in its own window --------------
echo   Starting the engine API on http://localhost:8787 ...
start "Persona Engine API" cmd /k "cd /d "%~dp0engine" && %PY% -m persona serve"

REM ---- 5. Start the dashboard in its own window ---------------
echo   Starting the dashboard on http://localhost:5173 ...
start "Persona Dashboard" cmd /k "cd /d "%~dp0dashboard" && npm run dev"

REM ---- 6. Give the dashboard a moment, then open the browser --
echo(
echo   Waiting for the dashboard to come up...
timeout /t 6 /nobreak >nul
start "" "http://localhost:5173"

echo(
echo   ====================================================
echo      Persona is running.
echo      Dashboard : http://localhost:5173
echo      Engine API: http://localhost:8787
echo(
echo      Two terminal windows opened (engine + dashboard).
echo      To stop everything, just close those two windows.
echo   ====================================================
echo(
echo   You can close THIS window.
timeout /t 8 /nobreak >nul
exit /b 0
