@echo off
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process '%~dpnx0' -Verb RunAs"
    exit /b
)

cd /d "C:\Users\Onur\Documents\GitHub\WinVoice"
call claude.cmd
pause