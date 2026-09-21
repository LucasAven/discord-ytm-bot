"""Dónde buscar los archivos cuando el bot corre suelto y cuando va empaquetado.

PyInstaller arma un ejecutable que al arrancar se descomprime solo en una
carpeta temporal, así que ahí `__file__` deja de servir para encontrar nada.
Son dos lugares distintos y conviene no confundirlos:

- Lo que viaja adentro del ejecutable, o sea ffmpeg, sale de `sys._MEIPASS`,
  que es esa carpeta temporal y cambia en cada arranque.
- Lo que tiene que quedar afuera para que la persona lo pueda cambiar, o sea
  `.env` y `browser.json`, va al lado del ejecutable.

Corriendo suelto, con Docker o con python directo, las dos cosas son la
carpeta del código y el ffmpeg del PATH, que es como funcionaba hasta ahora.
"""

from __future__ import annotations

import pathlib
import shutil
import sys


def empaquetado() -> bool:
    return getattr(sys, "frozen", False)


def carpeta_de_datos() -> pathlib.Path:
    """Donde van `.env` y `browser.json`."""
    if empaquetado():
        return pathlib.Path(sys.executable).resolve().parent
    return pathlib.Path(__file__).resolve().parent


def ffmpeg() -> str:
    """La ruta a ffmpeg, adentro del ejecutable o en el PATH."""
    adentro = getattr(sys, "_MEIPASS", None)
    if adentro:
        nombre = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        candidato = pathlib.Path(adentro) / nombre
        if candidato.is_file():
            return str(candidato)
    return shutil.which("ffmpeg") or "ffmpeg"
