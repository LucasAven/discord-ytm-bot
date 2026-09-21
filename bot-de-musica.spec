# -*- mode: python ; coding: utf-8 -*-
"""Receta de PyInstaller. Se usa igual en Windows y en macOS.

ffmpeg viaja adentro del ejecutable y `rutas.ffmpeg()` lo busca ahí. El
workflow lo deja en esta carpeta antes de compilar; si no está, el build sigue
y el ejecutable cae al ffmpeg del PATH, que es lo que pasa en una prueba local.
"""

import pathlib

from PyInstaller.utils.hooks import collect_all

binarios, datos, ocultos = [], [], []
# collect_all y no imports sueltos: ytmusicapi lleva sus traducciones, yt_dlp
# arma los extractores en runtime, discord trae los .dll de Opus para Windows y
# nacl lo carga discord.py por su cuenta, asi que PyInstaller no lo ve solo.
# Sin nacl el bot arranca igual y despues no puede mandar audio.
for paquete in ("discord", "yt_dlp", "ytmusicapi", "nacl", "cffi"):
    b, d, o = collect_all(paquete)
    binarios += b
    datos += d
    ocultos += o

# PyNaCl llega a libsodium via cffi, y cffi carga esta extension por su cuenta,
# asi que no aparece en ningun import y PyInstaller la deja afuera. Sin ella el
# bot arranca, se conecta y no puede mandar una sola muestra de audio.
ocultos.append("_cffi_backend")

for nombre in ("ffmpeg.exe", "ffmpeg"):
    if pathlib.Path(nombre).is_file():
        binarios.append((nombre, "."))
        break

a = Analysis(
    ["bot.py"],
    pathex=[],
    binaries=binarios,
    datas=datos,
    hiddenimports=ocultos,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="bot-de-musica",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
