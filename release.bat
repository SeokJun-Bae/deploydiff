@echo off
setlocal
cd /d "%~dp0"

set "APP_VERSION=%~1"
if "%APP_VERSION%"=="" set "APP_VERSION=0.0.2"
set "TAG=v%APP_VERSION%"

call build-installer.bat %APP_VERSION% || goto :error

where gh >nul 2>nul || (
    echo GitHub CLI is required.
    echo Install it with:
    echo winget install --id GitHub.cli
    goto :error
)

gh auth status >nul 2>nul || (
    echo GitHub CLI login is required.
    echo Run:
    echo gh auth login
    goto :error
)

git diff --quiet
if errorlevel 1 (
    echo Commit your changes before creating a release.
    goto :error
)

git diff --cached --quiet
if errorlevel 1 (
    echo Commit your staged changes before creating a release.
    goto :error
)

if not exist "dist\DeployDiffSetup.exe" (
    echo dist\DeployDiffSetup.exe was not found.
    goto :error
)

git push origin main || goto :error
git tag %TAG% 2>nul
git push origin %TAG% || goto :error

gh release view %TAG% >nul 2>nul
if errorlevel 1 (
    gh release create %TAG% "dist\DeployDiffSetup.exe" --title "DeployDiff %TAG%" --notes "DeployDiff 설치 파일입니다. Assets에서 DeployDiffSetup.exe를 다운로드한 뒤 실행하면 설치 위치를 선택해서 사용할 수 있습니다." || goto :error
) else (
    gh release upload %TAG% "dist\DeployDiffSetup.exe" --clobber || goto :error
)

echo.
echo Release complete: %TAG%
gh release view %TAG%
exit /b 0

:error
echo.
echo Release failed. Review the error output above.
pause
exit /b 1
