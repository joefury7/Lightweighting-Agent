@echo off
title Siemens NX CAM - Optomechanical Mirror Launcher
echo ========================================================
echo  Launching NX Manufacturing - NX CAM with 3D Mirror CAD
echo ========================================================
taskkill /F /IM ugraf.exe 2>nul
timeout /t 1 /nobreak >nul
set "SPLM_LICENSE_SERVER=27800@localhost"
set "UGII_BASE_DIR=C:\Program Files\Siemens\NX2007"
set "UGII_ROOT_DIR=C:\Program Files\Siemens\NX2007\NXBIN"
cd /d "C:\Program Files\Siemens\NX2007\MACH\auxiliary\nxcam"
start "" "C:\Program Files\Siemens\NX2007\NXBIN\ugraf.exe" -nxcam -retrieve:"%~dp0primary_mirror_560mm.prt"
echo NX CAM launched successfully!
timeout /t 3 /nobreak >nul
