@echo off
rem Locate the MSVC x64 environment, then run writer2027/build_win.sh in MSYS2.
rem
rem vcvars64.bat is resolved with vswhere so any Visual Studio 2022 edition
rem (Community, BuildTools, Professional, Enterprise) works. MSYS2 defaults to
rem C:\msys64 and can be overridden with MSYS2_ROOT.
setlocal

set "VCVARS="
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" (
    for /f "usebackq delims=" %%I in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSINSTALL=%%I"
)
if defined VSINSTALL if exist "%VSINSTALL%\VC\Auxiliary\Build\vcvars64.bat" set "VCVARS=%VSINSTALL%\VC\Auxiliary\Build\vcvars64.bat"
for %%D in (Community BuildTools Professional Enterprise) do (
    if not defined VCVARS if exist "%ProgramFiles%\Microsoft Visual Studio\2022\%%D\VC\Auxiliary\Build\vcvars64.bat" set "VCVARS=%ProgramFiles%\Microsoft Visual Studio\2022\%%D\VC\Auxiliary\Build\vcvars64.bat"
)
if not defined VCVARS (
    echo [run_build] vcvars64.bat not found. Install Visual Studio 2022 with the C++ x64 toolset.>&2
    exit /b 1
)
call "%VCVARS%" >nul 2>&1

if not defined MSYS2_ROOT set "MSYS2_ROOT=C:\msys64"
if not exist "%MSYS2_ROOT%\usr\bin\bash.exe" (
    echo [run_build] MSYS2 not found at "%MSYS2_ROOT%". Install MSYS2 or set MSYS2_ROOT.>&2
    exit /b 1
)

for %%I in ("%~dp0..") do set "REPO=%%~fI"
set "POSIXTMP=%TEMP%\naioffice_repo_%RANDOM%.txt"
"%MSYS2_ROOT%\usr\bin\cygpath.exe" -u "%REPO%" > "%POSIXTMP%"
set /p REPOPOSIX=<"%POSIXTMP%"
del "%POSIXTMP%" >nul 2>&1

set "JOBS=16"
"%MSYS2_ROOT%\usr\bin\bash.exe" -lc "cd '%REPOPOSIX%' && ./writer2027/build_win.sh %*"
exit /b %ERRORLEVEL%
