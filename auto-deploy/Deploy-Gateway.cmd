@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Deploy-Gateway.ps1" %*
set "DEPLOY_EXIT=%ERRORLEVEL%"
if not "%DEPLOY_EXIT%"=="0" echo Deployment stopped. Read the error above before retrying.
if "%~1"=="" pause
exit /b %DEPLOY_EXIT%
