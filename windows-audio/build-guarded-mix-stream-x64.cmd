@echo off
setlocal
pushd "%~dp0" || exit /b 1
call "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" || exit /b 1
cl /nologo /std:c++17 /O2 /EHsc /W4 scut_guarded_mix_pcm_stream.cpp /Fe:scut-guarded-mix-pcm-stream.exe ole32.lib uuid.lib
