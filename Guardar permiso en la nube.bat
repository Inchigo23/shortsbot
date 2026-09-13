@echo off
rem Guarda el permiso de YouTube (datos\token_youtube.json) como secreto cifrado en tu repositorio privado de GitHub,
rem para que la nube pueda subir vídeos y leer estadísticas. Ejecútalo después de pulsar "Conectar YouTube".
cd /d "%~dp0"
if not exist "datos\token_youtube.json" (
  echo No encuentro datos\token_youtube.json. Primero pulsa "Conectar YouTube" en el centro de control.
  pause
  exit /b 1
)
"C:\Program Files\GitHub CLI\gh.exe" secret set YOUTUBE_TOKEN -R Inchigo23/shortsbot < "datos\token_youtube.json"
if errorlevel 1 (
  echo.
  echo No se ha podido guardar. Avisa a Claude.
) else (
  echo.
  echo Listo: la nube ya tiene permiso para subir a tu canal.
)
pause
