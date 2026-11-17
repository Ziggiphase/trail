@echo off
title Building the Trail installer
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
if %errorlevel%==0 (
  explorer "%~dp0dist"
)
echo.
pause
