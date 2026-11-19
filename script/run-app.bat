@echo off
rem synop-fill: double-click to start the app in the background and open the browser. Thai messages live in app.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app.ps1" start %*
