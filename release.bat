@echo off
REM ==========================================================================
REM  release.bat - build and publish a new MyShell release
REM
REM  Usage:
REM    release.bat <version> ["commit message"]
REM
REM  Examples:
REM    release.bat v1.1.0                      (build + release current commit)
REM    release.bat v1.1.0 "add kill command"   (commit + push, then release)
REM ==========================================================================
setlocal enabledelayedexpansion

if "%~1"=="" (
  echo Usage: release.bat ^<version^> ["commit message"]
  echo Example: release.bat v1.1.0 "add new feature"
  exit /b 1
)
set "VERSION=%~1"
set "MSG=%~2"

if not "%MSG%"=="" (
  echo === Committing and pushing ===
  git add -A
  git commit -m "%MSG%"
  git push
  if errorlevel 1 ( echo Push failed. & exit /b 1 )
)

echo === Building executable ===
python -m PyInstaller --onefile --console --name MyShell --clean myshell.py
if errorlevel 1 ( echo Build failed. & exit /b 1 )

echo === Updating local bin copy ===
if not exist "%USERPROFILE%\bin" mkdir "%USERPROFILE%\bin"
copy /Y dist\MyShell.exe "%USERPROFILE%\bin\myshell.exe" >nul

echo === Locating gh ===
where gh >nul 2>nul
if %errorlevel%==0 ( set "GH=gh" ) else ( set "GH=C:\Program Files\GitHub CLI\gh.exe" )

echo === Creating GitHub release %VERSION% ===
"%GH%" release create %VERSION% dist\MyShell.exe --title "MyShell %VERSION%" --notes "Release %VERSION%"
if errorlevel 1 ( echo Release failed ^(tag may already exist^). & exit /b 1 )

echo.
echo Done! Release %VERSION% published.
endlocal
