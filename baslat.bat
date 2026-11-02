@echo off
title WinVoice - Sesli Asistan
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo Ollama servisinin hazir olmasi bekleniyor...
set OLLAMA_DENEME=0
:bekle_ollama
curl -s -o nul http://localhost:11434
if not errorlevel 1 goto ollama_hazir
set /a OLLAMA_DENEME+=1
if !OLLAMA_DENEME! geq 60 (
    echo [UYARI] Ollama 60 saniye icinde yanit vermedi, WinVoice yine de baslatiliyor.
    echo         Ollama uygulamasinin acik oldugundan emin olun.
    goto ollama_hazir
)
timeout /t 1 /nobreak >nul
goto bekle_ollama
:ollama_hazir
if "!OLLAMA_DENEME!"=="0" echo Ollama hazir.

if not exist ".venv\Scripts\activate.bat" (
    echo [HATA] Sanal ortam bulunamadi: ".venv\Scripts\activate.bat"
    echo Once sanal ortami olusturup bagimliliklari kurmalisiniz:
    echo     python -m venv .venv
    echo     call .venv\Scripts\activate.bat
    echo     pip install -r requirements.txt
    pause
    exit /b 1
)

echo Sanal ortam etkinlestiriliyor...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [HATA] Sanal ortam etkinlestirilemedi.
    pause
    exit /b 1
)

echo Eski WinVoice surecleri kontrol ediliyor...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -ieq 'pythonw.exe' -or $_.Name -ieq 'python.exe') -and ($_.ExecutablePath -like '*WinVoice*' -or $_.CommandLine -like '*WinVoice*') -and ($_.CommandLine -like '*main.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo WinVoice baslatiliyor... ^(sag alt kosede kucuk bir pencere belirecek^)
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0
