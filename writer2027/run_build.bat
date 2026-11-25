@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
set JOBS=16
set "REPO=%~dp0.."
C:\msys64\usr\bin\bash.exe -lc "cd "$(cygpath -u '%REPO%')" && ./writer2027/build_win.sh %*"