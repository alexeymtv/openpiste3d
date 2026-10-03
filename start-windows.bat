@echo off
REM Double-click this file to open the viewer.
REM It starts a small web server in this folder and opens the page itself.
REM The server is needed because a browser will not load the tileset from a
REM page opened straight off the disk.
cd /d "%~dp0"
echo.
echo   OpenPiste3D - starting a local server in:
echo   %CD%
echo.
echo   The viewer will open in your browser. Leave this window open while
echo   you use it; close it, or press Ctrl-C, to stop the server.
echo.
REM serve.py opens the browser itself, on whichever port it ends up using,
REM so nothing is opened from here.
where py >nul 2>nul
if %errorlevel%==0 (
  py serve.py
  goto :eof
)
where python >nul 2>nul
if %errorlevel%==0 (
  python serve.py
  goto :eof
)
echo   Python was not found on this computer.
echo.
echo   Either install Python from https://www.python.org/downloads/
echo   (tick "Add python.exe to PATH" during setup), or, if you have Node.js:
echo.
echo       npx --yes serve .
echo       then open http://localhost:3000/viewer/
echo.
pause
