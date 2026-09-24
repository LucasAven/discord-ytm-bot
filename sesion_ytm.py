"""Arma la sesión de YouTube Music a partir de la cookie del navegador.

Lo usa `bot.py` al arrancar: si encuentra `YTM_COOKIE` en el `.env`, se arma el
`browser.json` solo. Vale igual corriendo con Docker y adentro del ejecutable de
Windows, que no tiene Docker y por eso no tiene otra forma de llegar a las
playlists propias.

Hace los dos retoques que `ytmusicapi` no hace y que sin ellos no se nota que
faltan:

1. Agrega la clave `authorization`. Sin ella `YTMusic()` trata el archivo como
   OAuth y falla con un error que habla de otra cosa.
2. Detecta si la cuenta es de marca, o sea un canal aparte del personal, y en
   ese caso guarda `x-goog-pageid` y `x-goog-authuser`. Sin eso la sesión queda
   como la cuenta personal, ve dos playlists que YouTube crea solo y los links
   a las propias fallan como si no existieran.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re

from ytmusicapi import YTMusic
from ytmusicapi.helpers import get_authorization, sapisid_from_cookie

log = logging.getLogger(__name__)

USER_AGENT_POR_DEFECTO = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


class CookieInvalida(ValueError):
    """La cookie no sirve, y el mensaje explica por qué en castellano."""


def limpiar_cookie(crudo: str) -> str:
    """Acepta la cookie sola o la línea entera `cookie: ...` que copió la persona."""
    texto = (crudo or "").strip().strip('"').strip("'")
    if texto.lower().startswith("cookie:"):
        texto = texto.split(":", 1)[1]
    texto = " ".join(texto.split())
    if not texto:
        raise CookieInvalida("No pusiste ninguna cookie.")
    if "__Secure-3PAPISID=" not in texto:
        raise CookieInvalida(
            "La cookie está incompleta, le falta una parte que hace falta sí o sí. "
            "Probablemente se copió solo un pedazo."
        )
    return texto


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


def _playlists_que_ve(headers: dict) -> list[str] | None:
    try:
        yt = YTMusic(dict(headers))
        return [p.get("title", "?") for p in yt.get_library_playlists(limit=50)]
    except Exception:
        return None


def _buscar_pageid(headers: dict) -> str | None:
    try:
        yt = YTMusic(dict(headers))
        html = yt._session.get(
            "https://music.youtube.com/", headers=yt.base_headers, timeout=30
        ).text
    except Exception:
        return None
    encontrado = re.search(r'"DELEGATED_SESSION_ID"\s*:\s*"(\d{5,40})"', html)
    return encontrado.group(1) if encontrado else None


def armar(cookie_cruda: str, user_agent: str | None = None) -> tuple[dict, str, list[str]]:
    """Devuelve (headers, cómo se conectó, playlists que ve). No imprime la cookie."""
    cookie = limpiar_cookie(cookie_cruda)
    user_agent = user_agent or USER_AGENT_POR_DEFECTO

    try:
        sapisid_from_cookie(cookie)
    except Exception as e:
        raise CookieInvalida("La cookie no tiene el formato esperado.") from e

    base = armar_headers(cookie, user_agent, "0", None)
    opciones = [("cuenta principal", base)]

    # Probamos las combinaciones y nos quedamos con la que ve más playlists,
    # porque la de marca contesta igual de bien pero muestra otra biblioteca.
    pageid = _buscar_pageid(base)
    if pageid:
        for authuser in ("1", "0"):
            opciones.append(
                (f"canal aparte (slot {authuser})",
                 armar_headers(cookie, user_agent, authuser, pageid))
            )

    mejor: tuple[str, dict, list[str]] | None = None
    for nombre, headers in opciones:
        vistas = _playlists_que_ve(headers)
        if vistas is None:
            continue
        if mejor is None or len(vistas) > len(mejor[2]):
            mejor = (nombre, headers, vistas)

    if mejor is None:
        raise CookieInvalida(
            "La sesión no funcionó. Suele pasar cuando la cookie ya venció o "
            "cuando se copió mal."
        )
    return mejor[1], mejor[0], mejor[2]


def cookie_guardada(archivo: pathlib.Path) -> str | None:
    """La cookie que quedó en un browser.json, para saber si cambió la del .env."""
    try:
        return json.loads(archivo.read_text(encoding="utf-8")).get("cookie")
    except Exception:
        return None


def guardar(headers: dict, archivo: pathlib.Path) -> None:
    archivo.write_text(json.dumps(headers, indent=4), encoding="utf-8")
