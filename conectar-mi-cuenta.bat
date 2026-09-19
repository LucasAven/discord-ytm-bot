@echo off
setlocal
cd /d "%~dp0"
title Conectar mi cuenta de YouTube Music

echo.
echo   =================================================
echo    Conectar tu cuenta de YouTube Music
echo   =================================================
echo.
echo   Esto es OPCIONAL. El bot ya funciona sin esto.
echo   Sirve solo para que puedas pedirle TUS playlists.
echo.
echo   Todo queda en esta computadora. No se manda nada
echo   a ningun lado.
echo.
echo   IMPORTANTE: el archivo que se genera es tu sesion
echo   de Google. No se lo pases a nadie, ni a Lucas.
echo.
pause

docker info >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Docker Desktop no esta abierto. Abrilo desde el menu
  echo   Inicio, espera a que la ballena deje de moverse, y
  echo   volve a hacer doble clic aca.
  echo.
  pause
  exit /b 1
)

cls
echo.
echo   PASO 1 de 3
echo   -----------
echo.
echo   Se va a abrir YouTube Music en tu navegador.
echo   Fijate de estar con tu cuenta iniciada.
echo.
pause
start "" "https://music.youtube.com/"

cls
echo.
echo   PASO 2 de 3
echo   -----------
echo.
echo   En esa pestana de YouTube Music:
echo.
echo    1. Apreta la tecla F12. Se abre un panel al costado.
echo    2. Arriba de ese panel, elegi la solapa "Network".
echo    3. Volve a la pagina y hace clic en cualquier cancion,
echo       para que se mueva algo.
echo    4. En la lista que aparece, escribi  youtubei  en el
echo       casillero de filtro.
echo    5. Hace clic en el PRIMER renglon de la lista.
echo    6. Se abre otro panel. Elegi la solapa "Headers".
echo    7. Baja hasta donde dice "Request Headers". Al lado de
echo       ese titulo hay un boton que dice "Raw". Apretalo.
echo    8. El texto se vuelve un bloque corrido. Seleccionalo
echo       TODO y copialo con Control+C.
echo.
echo   Cuando lo hayas copiado, apreta una tecla aca.
echo.
pause

if exist "browser.json\" rmdir "browser.json" 2>nul
break > headers.txt

cls
echo.
echo   PASO 3 de 3
echo   -----------
echo.
echo   Se va a abrir el Bloc de notas.
echo.
echo    1. Pega ahi lo que copiaste, con Control+V.
echo    2. Guarda con Control+G.
echo    3. Cerra el Bloc de notas.
echo.
echo   Recien cuando lo cierres sigue solo.
echo.
pause
start /wait notepad.exe headers.txt

for %%A in (headers.txt) do if %%~zA LSS 50 (
  echo.
  echo   El archivo quedo vacio o casi vacio, asi que no puedo
  echo   seguir. Volve a hacer doble clic aca para intentar
  echo   de nuevo.
  echo.
  del headers.txt >nul 2>&1
  pause
  exit /b 1
)

cls
echo.
echo   Armando tu sesion. Esto tarda unos segundos.
echo.

docker compose run --rm configurar
set RESULTADO=%errorlevel%

del headers.txt >nul 2>&1

if not "%RESULTADO%"=="0" (
  echo.
  echo   Quedo como estaba, sin tu cuenta. El bot igual funciona
  echo   para buscar temas y para el autoplay.
  echo.
  pause
  exit /b 1
)

echo   Falta un ultimo paso: reinicia el bot para que tome tu
echo   cuenta. Hace doble clic en apagar-bot.bat y despues en
echo   iniciar-bot.bat
echo.
pause
