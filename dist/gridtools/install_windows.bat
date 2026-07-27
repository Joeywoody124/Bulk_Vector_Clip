@echo off
REM Link this folder into the QGIS plugins directory.
REM A junction (/J) does not need administrator rights, and edits to the code
REM here show up in QGIS after a plugin reload.

setlocal
set "SRC=%~dp0"
if %SRC:~-1%==\ set "SRC=%SRC:~0,-1%"
set "DEST=%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\gridtools"

if exist "%DEST%" (
    echo Something is already at:
    echo   %DEST%
    echo Remove it first ^(rmdir "%DEST%"^) then run this again.
    pause
    exit /b 1
)

if not exist "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins" (
    echo Could not find the QGIS plugins folder at:
    echo   %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins
    echo Start QGIS once to create it, or check you are using the "default" profile.
    pause
    exit /b 1
)

mklink /J "%DEST%" "%SRC%"
if errorlevel 1 (
    echo.
    echo Junction failed. Copy the folder instead:
    echo   xcopy /E /I "%SRC%" "%DEST%"
    pause
    exit /b 1
)

echo.
echo Linked. Now start QGIS and enable "Grid Tools" in
echo   Plugins  -^>  Manage and Install Plugins  -^>  Installed
echo Tick "Show also experimental plugins" in Settings if it is not listed.
pause
