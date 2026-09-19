@echo off
setlocal
cd /d "%~dp0"
title Bot de musica

echo.
echo   ===============================
echo    Bot de musica - iniciando
echo   ===============================
echo.

docker info >nul 2>&1
if errorlevel 1 (
  echo   Docker Desktop no esta abierto.
  echo.
  echo   Abrilo desde el menu Inicio y espera a que el icono de
  echo   la ballena deje de moverse. Despues volve a hacer doble
  echo   clic en este mismo archivo.
  echo.
  pause
  exit /b 1
)

if not exist ".env" (
  echo   Falta el archivo .env, que es el que tiene la clave del bot.
  echo   Pediselo a Lucas y dejalo en esta misma carpeta.
  echo.
  pause
  exit /b 1
)

echo   Preparando. La primera vez tarda unos minutos porque
echo   descarga todo. Las siguientes son casi instantaneas.
echo.

docker compose up -d --build
if errorlevel 1 (
  echo.
  echo   No se pudo iniciar.
  echo   Sacale una foto a esta ventana y mandasela a Lucas.
  echo.
  pause
  exit /b 1
)

echo.
echo   ===============================
echo    Listo. El bot ya esta online.
echo   ===============================
echo.
echo   Entra a Discord y escribi /play seguido del nombre
echo   de un tema.
echo.
echo   Para apagarlo, doble clic en apagar-bot.bat
echo   Esta ventana la podes cerrar, el bot sigue andando.
echo.
pause
