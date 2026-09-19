@echo off
setlocal
cd /d "%~dp0"
title Bot de musica

echo.
echo   Apagando el bot...
echo.

docker info >nul 2>&1
if errorlevel 1 (
  echo   Docker Desktop no esta abierto, asi que el bot ya
  echo   no esta corriendo. No hay nada que apagar.
  echo.
  pause
  exit /b 0
)

docker compose down

echo.
echo   Listo, el bot ya no esta online.
echo.
pause
