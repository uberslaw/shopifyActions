@echo off
REM Windows launcher for WPF / double-click / Task Scheduler.
REM Usage: checkout.cmd "https://shop/products/handle" [--json] [...]
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 -m shopify_actions %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python -m shopify_actions %*
  exit /b %ERRORLEVEL%
)

echo ERROR: Python 3 not found. Install Python 3.10+ and ensure "py" or "python" is on PATH. 1>&2
exit /b 127
