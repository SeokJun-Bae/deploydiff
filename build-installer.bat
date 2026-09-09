@echo off
setlocal
cd /d "%~dp0"

set "APP_VERSION=%~1"
if "%APP_VERSION%"=="" set "APP_VERSION=0.0.2"

call build.bat || goto :error

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if exist "%ISCC%" goto :build_installer

echo Inno Setup is required to build DeployDiffSetup.exe.
echo Install it with:
echo winget install --id JRSoftware.InnoSetup -e --source winget
goto :error

:build_installer
echo Building installer for version %APP_VERSION%...
"%ISCC%" "/DMyAppVersion=%APP_VERSION%" "installer.iss" || goto :error

echo.
echo Installer complete: dist\DeployDiffSetup.exe
start "" "%~dp0dist"
exit /b 0

:error
echo.
echo Installer build failed. Review the error output above.
pause
exit /b 1
