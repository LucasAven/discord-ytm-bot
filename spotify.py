"""Lee temas, álbumes y playlists públicas de Spotify, sin credenciales.

Spotify no tiene una API abierta, pero la página del reproductor que se puede
incrustar en un blog sí es pública, y trae la lista de temas en un JSON adentro
del HTML. De ahí sacamos nombre y artista de cada uno. Después cada tema se
busca en YouTube Music, que es lo único que el bot sabe reproducir, así que lo
que suena es la versión de YouTube y no siempre es la misma grabación.

Dos límites que vienen de Spotify y que desde acá no se pueden esquivar:

1. Esa página devuelve 100 temas como máximo. En una lista más larga los que
   sobran no vienen, y el JSON tampoco dice cuántos eran en total, así que lo
   único que podemos hacer es avisar cuando llegan justo 100.
2. Es una página web, no una API con contrato. Si Spotify le cambia el formato
   esto deja de andar sin aviso previo.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

TOPE = 100  # lo máximo que devuelve la página de Spotify

# Los links copiados del navegador vienen con el idioma adelante: /intl-es/track/...
_RUTA = re.compile(r"/(?:intl-[a-z]{2}/)?(track|album|playlist)/([A-Za-z0-9]+)")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
_JSON_EN_EL_HTML = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)

_NOMBRE = {"track": "tema", "album": "álbum", "playlist": "playlist"}


@dataclass
class Item:
    """Un tema como lo nombra Spotify, que es todo lo que necesitamos para buscarlo."""

    title: str
    artist: str

    def __str__(self) -> str:
        return f"{self.title} {self.artist}".strip()


@dataclass
class Listing:
    kind: str  # track, album o playlist
    name: str
    items: list[Item] = field(default_factory=list)
    truncated: bool = False

    @property
    def kind_name(self) -> str:
        return _NOMBRE.get(self.kind, self.kind)


def parse_url(url: str) -> tuple[str, str] | None:
    """Devuelve (tipo, id) de un link de Spotify, o None si no lo reconocemos."""
    encontrado = _RUTA.search(url)
    return (encontrado.group(1), encontrado.group(2)) if encontrado else None


def fetch(kind: str, spotify_id: str) -> Listing:
    """Trae los temas de Spotify. Bloquea: llamalo en un thread aparte."""
    entidad = _entidad(kind, spotify_id)
    nombre = entidad.get("title") or entidad.get("name") or "Sin nombre"

    if kind == "track":
        artistas = [a.get("name") for a in entidad.get("artists") or [] if a.get("name")]
        artista = ", ".join(artistas) or entidad.get("subtitle") or ""
        return Listing(kind=kind, name=nombre, items=[Item(nombre, artista)])

    # En un álbum los temas no repiten el artista, así que usamos el del álbum.
    artista_de_la_lista = entidad.get("subtitle") or ""
    items = []
    for t in entidad.get("trackList") or []:
        titulo = t.get("title")
        if titulo:
            items.append(Item(titulo, t.get("subtitle") or artista_de_la_lista))

    if not items:
        raise ValueError(
            f"Esa {_NOMBRE.get(kind, kind)} de Spotify no tiene temas que pueda leer."
        )

    return Listing(kind=kind, name=nombre, items=items, truncated=len(items) >= TOPE)


def _entidad(kind: str, spotify_id: str) -> dict:
    url = f"https://open.spotify.com/embed/{kind}/{spotify_id}"
    pedido = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(pedido, timeout=20) as respuesta:
            html = respuesta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        log.info("Spotify contestó %s para %s/%s", e.code, kind, spotify_id)
        raise ValueError(_no_pude(kind)) from e
    except Exception as e:
        log.info("No pude hablar con Spotify: %s", e)
        raise ValueError(
            "No pude conectarme con Spotify. Probá de nuevo en un rato."
        ) from e

    encontrado = _JSON_EN_EL_HTML.search(html)
    if not encontrado:
        # Esto es lo que va a pasar el día que Spotify cambie su página.
        log.warning("La página de Spotify vino sin el JSON esperado (%s bytes)", len(html))
        raise ValueError(
            "Spotify cambió su página y por ahora no puedo leer sus links. "
            "Pasame el nombre del tema y lo busco igual."
        )

    try:
        datos = json.loads(encontrado.group(1))
    except json.JSONDecodeError as e:
        raise ValueError(_no_pude(kind)) from e

    entidad = (
        datos.get("props", {})
        .get("pageProps", {})
        .get("state", {})
        .get("data", {})
        .get("entity")
    )
    if not isinstance(entidad, dict) or not entidad:
        raise ValueError(_no_pude(kind))
    return entidad


def _no_pude(kind: str) -> str:
    return (
        f"No pude abrir esa {_NOMBRE.get(kind, kind)} de Spotify. "
        "Fijate que el link esté bien y que sea pública."
    )
