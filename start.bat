@echo off
title 12306 Smart Ticket Tool
cd /d "%~dp0"

echo ========================================================
echo   12306 Smart Ticket Tool - Launcher
echo ========================================================
echo.

echo [1/2] Starting Backend Service on port 8000...
start "12306-Backend" cmd /k "cd /d "%~dp0backend" && python run.py"

echo [2/2] Starting Frontend Service on port 5173...
start "12306-Frontend" cmd /k "cd /d "%~dp0frontend" && npx vite"

echo.
echo ========================================================
echo   Services are running!
echo   Frontend Web:  http://localhost:5173
echo   Backend Docs:  http://localhost:8000/docs
echo ========================================================
echo.
