@echo off
rem Enciende ShortsBot en segundo plano y abre el panel. Si ya estaba encendido, solo abre el panel.
cd /d "%~dp0"
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0bot.py" --abrir
