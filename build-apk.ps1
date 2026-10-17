# Sehat Saathi - Mobile Android APK Build Pipeline
# Automates the entire APK build process from Vite PWA to native Android APK.

param(
    [switch]$OpenStudio = $false
)

$ErrorActionPreference = "Stop"
$WorkspaceRoot = $PSScriptRoot
$FrontendDir = Join-Path $WorkspaceRoot "frontend"
$AndroidDir = Join-Path $WorkspaceRoot "android"

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  Sehat Saathi - Native Android APK Build Pipeline        " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

# 1. Verify Node and npm
Write-Host "[1/5] Checking Node.js and environment..." -ForegroundColor Cyan
if (-not (Get-Command "npm" -ErrorAction SilentlyContinue)) {
    Write-Error "npm is not installed or not in PATH."
}

# 2. Build Frontend PWA assets
Write-Host "[2/5] Compiling Frontend PWA (TypeScript + Vite)..." -ForegroundColor Cyan
Set-Location $FrontendDir
& npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Error "Frontend compilation failed."
}

$DistPath = Join-Path $FrontendDir "dist"
if (-not (Test-Path $DistPath)) {
    Write-Error "dist folder was not created."
}
Write-Host "  ✓ Production bundle compiled to $DistPath" -ForegroundColor Green

# 3. Ensure Capacitor dependencies are installed
Write-Host "[3/5] Syncing Capacitor Android project..." -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $FrontendDir "node_modules/@capacitor/android"))) {
    Write-Host "  Installing @capacitor/core, @capacitor/cli, @capacitor/android..." -ForegroundColor Yellow
    & npm install --save @capacitor/core @capacitor/android
    & npm install --save-dev @capacitor/cli
}

# 4. Initialize or Sync Android
Set-Location $FrontendDir
if (-not (Test-Path (Join-Path $FrontendDir "android"))) {
    Write-Host "  Adding Android platform via Capacitor..." -ForegroundColor Yellow
    & npx cap add android
}

Write-Host "  Syncing web assets to native Android project..." -ForegroundColor Yellow
& npx cap sync android

# 5. Build APK via Gradle
$AndroidProjectDir = Join-Path $FrontendDir "android"
$Gradlew = Join-Path $AndroidProjectDir "gradlew.bat"

if (Test-Path $Gradlew) {
    Write-Host "[4/5] Building Android APK (assembleDebug)..." -ForegroundColor Cyan
    Set-Location $AndroidProjectDir
    
    # Check if Java is available for Gradle
    if (Get-Command "java" -ErrorAction SilentlyContinue) {
        & .\gradlew.bat assembleDebug
        if ($LASTEXITCODE -eq 0) {
            $ApkPath = Join-Path $AndroidProjectDir "app\build\outputs\apk\debug\app-debug.apk"
            if (Test-Path $ApkPath) {
                Write-Host "==========================================================" -ForegroundColor Green
                Write-Host "  ✓ APK BUILT SUCCESSFULLY!                                " -ForegroundColor Green
                Write-Host "  Output: $ApkPath" -ForegroundColor Yellow
                Write-Host "==========================================================" -ForegroundColor Green
            }
        } else {
            Write-Host "  Note: Gradle build failed or Android SDK not found. You can open Android Studio." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  JDK / java command not found in PATH. You can open Android Studio to compile the APK." -ForegroundColor Yellow
    }
}

if ($OpenStudio) {
    Write-Host "[5/5] Launching Android Studio..." -ForegroundColor Cyan
    Set-Location $FrontendDir
    & npx cap open android
} else {
    Write-Host "`nTo open the project in Android Studio at any time, run:" -ForegroundColor Cyan
    Write-Host "  cd frontend; npx cap open android`n" -ForegroundColor White
}

Set-Location $WorkspaceRoot
Write-Host "Pipeline execution complete!" -ForegroundColor Green
