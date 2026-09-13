@echo off
rem Guarda el permiso de YouTube (datos\token_youtube.json) como secreto cifrado en tu repositorio privado
rem de GitHub, para que la nube pueda subir videos. Ejecutalo despues de pulsar "Conectar YouTube".
cd /d "%~dp0"
set REGISTRO=datos\guardar_permiso.log
echo [%date% %time%] Guardando el permiso en la nube... > "%REGISTRO%"

if not exist "datos\token_youtube.json" goto sin_token

"C:\Program Files\GitHub CLI\gh.exe" secret set YOUTUBE_TOKEN -R Inchigo23/shortsbot < "datos\token_youtube.json" >> "%REGISTRO%" 2>&1
if errorlevel 1 goto fallo

echo OK >> "%REGISTRO%"
echo.
echo  Listo: la nube ya tiene permiso para subir a tu canal.
echo.
pause
exit /b 0

:sin_token
echo SIN TOKEN >> "%REGISTRO%"
echo.
echo  No encuentro el permiso de YouTube. Primero pulsa "Conectar YouTube" en el centro de control.
echo.
pause
exit /b 1

:fallo
echo.
echo  No se ha podido guardar. Esto es lo que ha pasado:
echo.
type "%REGISTRO%"
echo.
echo  Dile a Claude que lo mire.
pause
exit /b 1
