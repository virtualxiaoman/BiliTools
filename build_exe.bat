@echo off
setlocal

rem BiliTools Windows build and release-package script.
rem It creates dist\BiliTools.exe and dist\BiliTools-windows-x64.zip.

cd /d "%~dp0"
set "PYTHON=%~dp0venv\Scripts\python.exe"
set "SPEC=%~dp0bilitools.spec"
set "EXE=%~dp0dist\BiliTools.exe"
set "ZIP=%~dp0dist\BiliTools-windows-x64.zip"
set "PACKAGE_DIR=%TEMP%\BiliTools-package-%RANDOM%-%RANDOM%"

if not exist "%PYTHON%" (
    echo [ERROR] Virtual environment Python was not found:
    echo         %PYTHON%
    echo Create the virtual environment and install dependencies first.
    pause
    exit /b 1
)

if not exist "%SPEC%" (
    echo [ERROR] PyInstaller spec file was not found:
    echo         %SPEC%
    pause
    exit /b 1
)

if not exist "%~dp0assets\fonts" (
    echo [ERROR] Required assets folder was not found:
    echo         %~dp0assets\fonts
    pause
    exit /b 1
)

if not exist "%~dp0assets\imgs" (
    echo [ERROR] Required assets folder was not found:
    echo         %~dp0assets\imgs
    pause
    exit /b 1
)

rem A running BiliTools.exe locks the output file and causes WinError 5.
echo [INFO] Closing any running BiliTools.exe process...
taskkill /F /IM BiliTools.exe >nul 2>&1

rem Give Windows a moment to release the executable handle.
timeout /t 1 /nobreak >nul

echo [INFO] Building BiliTools...
echo [INFO] Project directory: %~dp0
"%PYTHON%" -m PyInstaller "%SPEC%" --noconfirm --clean
if errorlevel 1 (
    echo.
    echo [FAILED] Build failed. If WinError 5 persists, close Explorer previews,
    echo         antivirus locking, or other programs using dist\BiliTools.exe.
    pause
    exit /b 1
)

if not exist "%EXE%" (
    echo.
    echo [FAILED] PyInstaller finished, but the output file was not found:
    echo          %EXE%
    pause
    exit /b 1
)

rem Create a clean distributable folder. Only static assets are included:
rem fonts and imgs are required by the UI; user settings, caches, and cookies are excluded.
echo [INFO] Creating release ZIP...
if exist "%PACKAGE_DIR%" rmdir /S /Q "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%\assets\fonts" >nul
mkdir "%PACKAGE_DIR%\assets\imgs" >nul
copy /Y "%EXE%" "%PACKAGE_DIR%\BiliTools.exe" >nul
xcopy "%~dp0assets\fonts" "%PACKAGE_DIR%\assets\fonts" /E /I /Y /Q >nul
if errorlevel 1 goto :package_failed
xcopy "%~dp0assets\imgs" "%PACKAGE_DIR%\assets\imgs" /E /I /Y /Q >nul
if errorlevel 1 goto :package_failed

powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%PACKAGE_DIR%\*' -DestinationPath '%ZIP%' -Force"
if errorlevel 1 goto :package_failed

if not exist "%ZIP%" goto :package_failed
rmdir /S /Q "%PACKAGE_DIR%"

echo.
echo [SUCCESS] Build completed:
echo           EXE: %EXE%
echo           ZIP: %ZIP%
echo.
echo Distribute the ZIP file. After extraction, keep BiliTools.exe and assets together.
pause
exit /b 0

:package_failed
echo.
echo [FAILED] The EXE was built, but creation of the release ZIP failed.
echo          EXE: %EXE%
echo          Temporary package folder: %PACKAGE_DIR%
pause
exit /b 1
