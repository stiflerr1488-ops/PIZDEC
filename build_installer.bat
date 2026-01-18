@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
)

if exist build rmdir /s /q build

python setup.py build
if errorlevel 1 (
  echo.
  echo BUILD FAILED
  pause
  exit /b 1
)

echo.
echo DONE. Portable build folder(s):
dir /b build\exe.*
echo.
pause
