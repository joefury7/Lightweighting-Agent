@echo off
title NX Mirror Lightweighting Studio - Server
echo ================================================================
echo  NX Mirror Lightweighting Studio - Backend Server
echo ================================================================
echo.
echo   Mass        : exact NX-journal geometry          :8000/ml/predict
echo   Sag         : GP surrogate trained on FEA runs    :8000/surrogate/predict
echo   Optimizer   : NSGA-II (+ PPO refinement)          :8000/optimize/unified
echo   FEA verify  : NX Nastran SOL 101 / CalculiX       :8000/fea/solve
echo.
set PYTHONUTF8=1
cd /d "%~dp0"
set PY="%LOCALAPPDATA%\Programs\Python311\python.exe"

echo  Checking Python dependencies (first run may take a few minutes)...
%PY% -m pip install -q -r requirements.txt
echo.
echo  Starting server...

REM Open browser to server URL after 5 seconds
start /b cmd /c "timeout /t 5 /nobreak >nul && start http://127.0.0.1:8000/"

REM Start the FastAPI server
%PY% -m uvicorn server.main_server:app --host 0.0.0.0 --port 8000 --reload --reload-dir server --reload-dir ml_engine --reload-dir optimizer --reload-dir cad_engine --reload-dir fea_engine --reload-dir nx_bridge

pause
