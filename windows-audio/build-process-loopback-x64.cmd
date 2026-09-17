@echo off
setlocal
pushd "%~dp0" || exit /b 1
call "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" || exit /b 1
cl /nologo /std:c++17 /O2 /EHsc /W4 /DWINAPI_FAMILY=WINAPI_FAMILY_DESKTOP_APP scut_process_loopback.cpp /Fe:scut-process-loopback.exe ole32.lib uuid.lib mmdevapi.lib || exit /b 1
cl /nologo /std:c++17 /O2 /EHsc /W4 scut_tone_player.cpp /Fe:scut-tone-player.exe winmm.lib || exit /b 1
