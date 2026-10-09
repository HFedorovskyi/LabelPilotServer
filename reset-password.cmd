@echo off
REM -- LabelPilot: set a new password for a server user ----------------------------
REM The way back in for a sole administrator who forgot the password. Start menu:
REM LabelPilot > "LabelPilot - password reset" (created by the server, api/start_menu.py).
REM Needs Windows administrator rights on the server computer (the database is writable
REM only by administrators): re-launches itself elevated (UAC) when started without them.
REM Lives in app\backend so signed updates (.lpupdate) can deliver it too.
setlocal
net session >NUL 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
chcp 65001 >NUL
set "BACKEND=%~dp0"
for %%I in ("%BACKEND%..\..") do set "ROOT=%%~fI"
set "PYTHON=%ROOT%\python\python.exe"
set "PYCACHE=%ROOT%\app\runtime-cache\reset-password"
set "DJANGO_DEBUG=0"
if not exist "%PYTHON%" (
  echo LabelPilot Server is not installed here: %PYTHON% is missing.
  pause
  exit /b 1
)
cd /d "%BACKEND%"
REM -E: ignore PYTHON* variables; -s: no user site (same as run-backend.cmd).
"%PYTHON%" -E -s -X utf8 -X "pycache_prefix=%PYCACHE%" manage.py reset_password
echo.
pause
