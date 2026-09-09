@echo off
setlocal
cd /d "%~dp0"

set "APP_VERSION=%~1"
if "%APP_VERSION%"=="" set "APP_VERSION=0.0.2"
set "TAG=v%APP_VERSION%"

where gh >nul 2>nul
if errorlevel 1 goto :missing_gh

gh auth status >nul 2>nul
if errorlevel 1 goto :missing_login

git diff --quiet
if errorlevel 1 goto :dirty_worktree

git diff --cached --quiet
if errorlevel 1 goto :dirty_index

call build-installer.bat %APP_VERSION% || goto :error

if not exist "dist\DeployDiffSetup.exe" goto :missing_setup

git push origin main || goto :error
git tag %TAG% 2>nul
git push origin %TAG% || goto :error

gh release view %TAG% >nul 2>nul
if errorlevel 1 goto :create_release
goto :upload_release

:create_release
gh release create %TAG% "dist\DeployDiffSetup.exe" --title "DeployDiff %TAG%" --notes "DeployDiff installer. Download DeployDiffSetup.exe from Assets and run it to choose an install location." || goto :error
goto :done

:upload_release
gh release upload %TAG% "dist\DeployDiffSetup.exe" --clobber || goto :error
goto :done

:done
echo.
echo Release complete: %TAG%
gh release view %TAG%
exit /b 0

:missing_gh
echo GitHub CLI is required.
echo Install it with:
echo winget install --id GitHub.cli
goto :error

:missing_login
echo GitHub CLI login is required.
echo Run:
echo gh auth login
goto :error

:dirty_worktree
echo Commit your changes before creating a release.
goto :error

:dirty_index
echo Commit your staged changes before creating a release.
goto :error

:missing_setup
echo dist\DeployDiffSetup.exe was not found.
goto :error

:error
echo.
echo Release failed. Review the error output above.
pause
exit /b 1
