@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -m venv .venv || goto :error
)

".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt || goto :error

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist DeployDiff.spec del /q DeployDiff.spec

".venv\Scripts\python.exe" -m PyInstaller --onefile --windowed --name DeployDiff main.py || goto :error

echo.
echo Build complete: dist\DeployDiff.exe
exit /b 0

:error
echo.
echo Build failed. Review the error output above.
pause
exit /b 1
