"""Arma browser.json a partir de los headers que la persona pegó.

Corre adentro del container. Lee /trabajo/headers.txt y escribe
/trabajo/browser.json. No manda nada a ningún lado y no imprime la cookie.

Hace solos los dos retoques que ytmusicapi no hace:

1. Agrega la clave `authorization`. Sin ella `YTMusic()` trata el archivo como
   OAuth y falla.
2. Detecta si la cuenta es de marca (un canal aparte del personal) y en ese
   caso guarda `x-goog-pageid` y `x-goog-authuser`. Sin eso la sesión queda
   como la cuenta personal, no ve las playlists propias y no avisa.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

from ytmusicapi import YTMusic
from ytmusicapi.helpers import get_authorization, sapisid_from_cookie

TRABAJO = pathlib.Path("/trabajo")
ENTRADA = TRABAJO / "headers.txt"
SALIDA = TRABAJO / "browser.json"

USER_AGENT_POR_DEFECTO = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


def morir(mensaje: str) -> None:
    print()
    print("  NO SE PUDO.")
    print(f"  {mensaje}")
    print()
    sys.exit(1)


def leer_headers_pegados() -> tuple[str, str]:
    """Devuelve (cookie, user_agent) de lo que haya pegado la persona."""
    if not ENTRADA.is_file():
        morir("No encontre el archivo headers.txt.")

    crudo = ENTRADA.read_text(encoding="utf-8", errors="replace")
    if not crudo.strip():
        morir("El archivo headers.txt quedo vacio. Tenes que pegar el texto y guardar.")

    cookie = ""
    user_agent = ""
    for linea in crudo.splitlines():
        limpia = linea.strip().lstrip(":")
        clave, sep, valor = limpia.partition(":")
        if not sep:
            continue
        clave = clave.strip().lower()
        valor = valor.strip()
        if clave == "cookie" and len(valor) > len(cookie):
            cookie = valor
        elif clave == "user-agent" and valor:
            user_agent = valor

    if not cookie and "SAPISID=" in crudo:
        # Pegó la cookie sola, sin el nombre del header adelante.
        cookie = " ".join(crudo.split())

    if not cookie:
        morir(
            "No encontre la linea que empieza con 'cookie:'. Fijate de haber "
            "copiado los headers enteros y no otra cosa."
        )
    if "__Secure-3PAPISID=" not in cookie:
        morir(
            "La cookie que pegaste esta incompleta, le falta una parte que hace "
            "falta si o si. Probablemente copiaste solo un pedazo. Intenta de nuevo."
        )
    return cookie, user_agent or USER_AGENT_POR_DEFECTO


def armar_headers(cookie: str, user_agent: str, authuser: str, pageid: str | None) -> dict:
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate",
        "content-type": "application/json",
        "content-encoding": "gzip",
        "origin": "https://music.youtube.com",
        "user-agent": user_agent,
        "cookie": cookie,
        "x-goog-authuser": authuser,
    }
    if pageid:
        headers["x-goog-pageid"] = pageid
    headers["authorization"] = get_authorization(
        sapisid_from_cookie(cookie) + " " + headers["origin"]
    )
    return headers


def playlists_que_ve(headers: dict) -> list[str] | None:
    try:
        yt = YTMusic(dict(headers))
        return [p.get("title", "?") for p in yt.get_library_playlists(limit=50)]
    except Exception:
        return None


def buscar_pageid(headers: dict) -> str | None:
    try:
        yt = YTMusic(dict(headers))
        html = yt._session.get(
            "https://music.youtube.com/", headers=yt.base_headers, timeout=30
        ).text
    except Exception:
        return None
    encontrado = re.search(r'"DELEGATED_SESSION_ID"\s*:\s*"(\d{5,40})"', html)
    return encontrado.group(1) if encontrado else None


def main() -> None:
    print()
    print("  Leyendo lo que pegaste...")
    cookie, user_agent = leer_headers_pegados()

    base = armar_headers(cookie, user_agent, "0", None)
    try:
        sapisid_from_cookie(cookie)
    except Exception:
        morir("La cookie no tiene el formato esperado. Intenta copiarla de nuevo.")

    print("  Probando la sesion contra YouTube Music...")
    opciones: list[tuple[str, dict]] = [("cuenta principal", base)]

    pageid = buscar_pageid(base)
    if pageid:
        for authuser in ("1", "0"):
            opciones.append(
                (f"canal aparte (slot {authuser})",
                 armar_headers(cookie, user_agent, authuser, pageid))
            )

    mejor_nombre = None
    mejor_headers = None
    mejores: list[str] = []
    for nombre, headers in opciones:
        vistas = playlists_que_ve(headers)
        if vistas is None:
            continue
        if mejor_headers is None or len(vistas) > len(mejores):
            mejor_nombre, mejor_headers, mejores = nombre, headers, vistas

    if mejor_headers is None:
        morir(
            "La sesion no funciono. Suele pasar cuando pasaron varios minutos "
            "entre que copiaste los headers y llegaste hasta aca. Intenta de nuevo."
        )

    SALIDA.write_text(json.dumps(mejor_headers, indent=4), encoding="utf-8")

    print()
    print("  ===============================")
    print("   Listo, tu sesion quedo guardada.")
    print("  ===============================")
    print()
    print(f"  Se conecto como: {mejor_nombre}")
    print(f"  Playlists que ve el bot: {len(mejores)}")
    for titulo in mejores:
        print(f"    - {titulo}")
    print()
    if len(mejores) <= 2:
        print("  Solo aparecen las dos que YouTube crea solo. Si vos tenes mas,")
        print("  fijate de haber copiado los headers con tu cuenta activa en la")
        print("  pagina, y proba de nuevo.")
        print()


if __name__ == "__main__":
    main()
