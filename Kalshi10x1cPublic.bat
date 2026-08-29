@echo off
setlocal
set "ROOT=%~dp0"
where py >nul 2>&1
if errorlevel 1 goto use_python
py -3 "%ROOT%run_buy_planner.py" %*
exit /b %errorlevel%
:use_python
where python >nul 2>&1
if errorlevel 1 goto no_python
python "%ROOT%run_buy_planner.py" %*
exit /b %errorlevel%
:no_python
echo Python 3.11 or newer is required.
exit /b 9009
