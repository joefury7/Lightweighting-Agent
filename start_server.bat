@echo off
title NX Mirror Lightweighting Studio - 4-Pillar AI Server
echo ================================================================
echo  NX Mirror Lightweighting Studio - 4-Pillar AI Backend Server
echo ================================================================
echo.
echo  Pillars:
echo   [P1] FastAPI + Qwen 2.5 Coder Agent      :8000/agent/chat
echo   [P2] XGBoost Surrogate ML Predict         :8000/ml/predict
echo   [P3] NSGA-II 50k Pareto GA Optimizer      :8000/optimize/nsga2
echo   [P4] NASTRAN SOL 101 FEA Engine           :8000/fea/solve
echo.
echo  Starting server...
echo.
set PYTHONUTF8=1
cd /d "%~dp0"

REM Open browser to server URL after 3 seconds
start /b cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8000/"

REM Start the FastAPI server
"%LOCALAPPDATA%\Programs\Python311\python.exe" -m uvicorn server.main_server:app --host 0.0.0.0 --port 8000 --reload

pause
