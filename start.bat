@echo off
REM Run Rubico on your own Windows computer: double click this file.
REM
REM The first time, it installs everything into a private .venv folder, then
REM starts Rubico and opens the setup page in your browser. After that it just
REM starts Rubico. Your brief only goes out while this computer is on and awake.
REM
REM   start.bat         start Rubico
REM   start.bat demo    try it with fake data, no accounts needed
cd /d "%~dp0"

set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul || goto nopython

if not exist .venv\Scripts\python.exe (
  echo First run: setting things up, about a minute...
  %PY% -m venv .venv || goto failed
)
if not exist .venv\installed.txt (
  .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
  .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt || goto failed
  echo ok> .venv\installed.txt
)

if /i "%~1"=="demo" (
  .venv\Scripts\python.exe demo.py %2 %3 %4
) else (
  .venv\Scripts\python.exe run.py --local %*
)
if not defined RUBICO_NO_PAUSE pause
exit /b

:nopython
echo Rubico needs Python 3.10 or newer.
echo Download it from https://www.python.org/downloads/
echo IMPORTANT: tick "Add python.exe to PATH" in the installer, then run this again.
start https://www.python.org/downloads/
if not defined RUBICO_NO_PAUSE pause
exit /b 1

:failed
echo Something went wrong installing. Check your internet connection and try again.
if not defined RUBICO_NO_PAUSE pause
exit /b 1
