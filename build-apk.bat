@echo off
setlocal
echo ==========================================================
echo   Sehat Saathi - Native Android APK Build Pipeline
echo ==========================================================

cd /d "%~dp0frontend"

echo [1/3] Building Frontend PWA...
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo Frontend build failed!
    pause
    exit /b %ERRORLEVEL%
)

echo [2/3] Syncing Android project...
call npx cap sync android

echo [3/3] Compiling Android APK with Gradle...
if exist "android\gradlew.bat" (
    cd android
    call gradlew.bat assembleDebug
    if %ERRORLEVEL% EQU 0 (
        echo ==========================================================
        echo   SUCCESS: APK generated at frontend\android\app\build\outputs\apk\debug\app-debug.apk
        echo ==========================================================
    ) else (
        echo Gradle build completed with warnings or Android SDK not found.
        echo To finish compiling, open Android Studio by running: npx cap open android
    )
    cd ..
)

cd /d "%~dp0"
echo Done!
pause
