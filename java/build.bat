@echo off
setlocal enabledelayedexpansion

if "%~1"=="" (
  echo Usage: build.bat ^<tablecard.apk^>
  exit /b 1
)

set "APK=%~f1"
set "SCRIPT_DIR=%~dp0"
set "BUILD_DIR=%SCRIPT_DIR%build"
set "CLASSES_DIR=%BUILD_DIR%\classes"
set "NATIVE_DIR=%SCRIPT_DIR%native"
set "SRC_DIR=%SCRIPT_DIR%com"

if not exist "%APK%" (
  echo APK not found: %APK%
  exit /b 1
)

if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
mkdir "%CLASSES_DIR%" 2>nul
mkdir "%NATIVE_DIR%" 2>nul

echo Extracting libbluetoothhelper.so from APK...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Add-Type -AssemblyName System.IO.Compression.FileSystem; " ^
  "$apk = '%APK%'; " ^
  "$zip = [IO.Compression.ZipFile]::OpenRead($apk); " ^
  "$entries = $zip.Entries | Where-Object { $_.FullName -match 'lib/.+/libbluetoothhelper\.so$' }; " ^
  "if (-not $entries) { Write-Error 'libbluetoothhelper.so not found in APK'; exit 1 }; " ^
  "$entry = $entries | Select-Object -First 1; " ^
  "$dest = Join-Path '%NATIVE_DIR%' 'libbluetoothhelper.so'; " ^
  "[IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dest, $true); " ^
  "Write-Host ('Extracted: ' + $entry.FullName); " ^
  "$zip.Dispose()"
if errorlevel 1 exit /b 1

where javac >nul 2>&1
if errorlevel 1 (
  echo javac not found. Install JDK and add it to PATH.
  exit /b 1
)

where jar >nul 2>&1
if errorlevel 1 (
  echo jar not found. Install JDK and add it to PATH.
  exit /b 1
)

echo Compiling JniUtils + EncodeBridge...
javac -encoding UTF-8 -d "%CLASSES_DIR%" ^
  "%SRC_DIR%\bupin\blesdk\jni\JniUtils.java" ^
  "%SCRIPT_DIR%EncodeBridge.java"
if errorlevel 1 exit /b 1

echo Creating pm970-encoder.jar...
jar cf "%SCRIPT_DIR%pm970-encoder.jar" -C "%CLASSES_DIR%" .
if errorlevel 1 exit /b 1

echo.
echo Done: %SCRIPT_DIR%pm970-encoder.jar
echo Native lib: %NATIVE_DIR%\libbluetoothhelper.so
echo.
echo Run encoder (example^):
echo   set JAVA_TOOL_OPTIONS=-Djava.library.path=%NATIVE_DIR%
echo   java -Djava.library.path=%NATIVE_DIR% -cp "%SCRIPT_DIR%pm970-encoder.jar" com.bupin.pm970.EncodeBridge create_image
