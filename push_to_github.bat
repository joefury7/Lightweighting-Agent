@echo off
title Push Lightweighting Agent to GitHub
echo =====================================================================
echo  Pushing latest changes to https://github.com/joefury7/Lightweighting-Agent
echo =====================================================================
echo.
cd /d "%~dp0"
set PATH=%LOCALAPPDATA%\Programs\MinGit\cmd;%PATH%

git status
echo.
echo Pushing to origin main...
git push -u origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo =====================================================================
    echo  [SUCCESS] Successfully pushed all files to GitHub!
    echo =====================================================================
) else (
    echo.
    echo =====================================================================
    echo  [NOTICE] If GitHub prompts for authentication, please sign in
    echo  or use a GitHub Personal Access Token (PAT) when prompted.
    echo =====================================================================
)

echo.
pause
