@echo off
setlocal
set "SCUT_ROOT=%~dp0"
if not defined JAVA_HOME set "JAVA_HOME=%ProgramFiles%\Android\Android Studio\jbr"
set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
set "GRADLE_BIN=%USERPROFILE%\.gradle\wrapper\dists\gradle-8.13-bin\5xuhj0ry160q40clulazy9h7d\gradle-8.13\bin\gradle.bat"
if not exist "%JAVA_HOME%\bin\java.exe" (
  echo Android JDK was not found. Install Android Studio or configure JAVA_HOME, then rerun.
  exit /b 1
)
if not exist "%ANDROID_HOME%\platforms\android-36" (
  echo Android SDK platform 36 was not found. Install it in Android Studio, then rerun.
  exit /b 1
)
if not exist "%GRADLE_BIN%" (
  echo Gradle 8.13 cache is not present. Use Android Studio once or add Gradle 8.13, then rerun.
  exit /b 1
)
call "%GRADLE_BIN%" -p "%SCUT_ROOT%android" :app:assembleDebug
if errorlevel 1 exit /b %ERRORLEVEL%
if not exist "%SCUT_ROOT%dist" mkdir "%SCUT_ROOT%dist"
copy /Y "%SCUT_ROOT%android\app\build\outputs\apk\debug\app-debug.apk" "%SCUT_ROOT%dist\SCUT.apk" >nul
echo Built genuine Android debug APK: %SCUT_ROOT%dist\SCUT.apk
