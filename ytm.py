"""Capa de acceso a YouTube Music: búsqueda, playlists, radio y streaming."""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import queue
import re
import threading
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import discord
import yt_dlp
from ytmusicapi import YTMusic

log = logging.getLogger(__name__)

YDL_OPTS = {
    "format": "bestaudio[ext=m4a]/bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
}

# Sin estos flags, si el CDN corta la conexión el tema se muere a la mitad.
FFMPEG_BEFORE = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
    "-loglevel warning"
)
FFMPEG_OPTS = "-vn"

PREBUFFER_FRAMES = 150  # 3 s de audio antes de empezar a sonar
BUFFER_FRAMES = 750  # tope del colchón, 15 s


class BufferedAudioSource(discord.AudioSource):
    """Colchón entre ffmpeg y discord.py.

    discord.py arranca su reloj de 20 ms apenas llamás a play() y el pipe de
    ffmpeg solo aguanta unos 0.3 s. Si la red se traba un segundo, el thread de
    audio se queda sin datos y después manda todo junto para recuperar el
    atraso, que es lo que se escucha acelerado. Un hilo aparte llena este colchón
    para que esos baches no lleguen a Discord.
    """

    def __init__(self, source: discord.AudioSource):
        self._source = source
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=BUFFER_FRAMES)
        self._ready = threading.Event()
        self._ended = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._fill, daemon=True)
        self._thread.start()

    def _fill(self) -> None:
        try:
            while not self._stop.is_set():
                data = self._source.read()
                if not data:
                    return
                while not self._stop.is_set():
                    try:
                        self._queue.put(data, timeout=0.2)
                        break
                    except queue.Full:
                        continue
                if self._queue.qsize() >= PREBUFFER_FRAMES:
                    self._ready.set()
        finally:
            self._ended.set()
            self._ready.set()

    def wait_until_ready(self, timeout: float = 20.0) -> None:
        self._ready.wait(timeout)

    def read(self) -> bytes:
        while True:
            try:
                return self._queue.get(timeout=0.5)
            except queue.Empty:
                if self._ended.is_set():
                    return b""

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        self._stop.set()
        self._source.cleanup()


@dataclass
class Track:
    video_id: str
    title: str
    artist: str
    duration: str | None = None
    thumbnail: str | None = None
    requested_by: str | None = None

    @property
    def url(self) -> str:
        return f"https://music.youtube.com/watch?v={self.video_id}"

    def __str__(self) -> str:
        return f"{self.title} — {self.artist}"


def _artists(item: dict) -> str:
    artists = item.get("artists") or []
    names = [a.get("name") for a in artists if a.get("name")]
    if not names:
        album = item.get("album")
        if isinstance(album, dict) and album.get("name"):
            names = [album["name"]]
    return ", ".join(names) or "Desconocido"


def _thumb(item: dict) -> str | None:
    thumbs = item.get("thumbnails") or []
    return thumbs[-1]["url"] if thumbs else None


def _to_track(item: dict) -> Track | None:
    vid = item.get("videoId")
    if not vid:
        return None
    return Track(
        video_id=vid,
        title=item.get("title") or "Sin título",
        artist=_artists(item),
        duration=item.get("duration") or item.get("length"),
        thumbnail=_thumb(item),
    )


class YTMClient:
    """Todo lo que toca la red corre en un thread aparte para no bloquear el loop."""

    def __init__(self, auth_file: str | None = None):
        if auth_file and os.path.exists(auth_file):
            self.ytm = YTMusic(auth_file)
            self.authenticated = True
            log.info("YTMusic autenticado con %s", auth_file)
        else:
            self.ytm = YTMusic()
            self.authenticated = False
            log.warning(
                "YTMusic sin auth: no vas a poder usar playlists privadas ni "
                "recomendaciones personalizadas."
            )

    async def _run(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, functools.partial(func, *args, **kwargs)
        )

    # ---------- resolución de lo que pide el usuario ----------

    async def resolve(self, query: str) -> tuple[list[Track], str]:
        """Devuelve (tracks, descripción) a partir de una URL o texto libre."""
        query = query.strip()

        if re.match(r"https?://", query):
            parsed = urlparse(query)
            params = parse_qs(parsed.query)

            playlist_id = (params.get("list") or [None])[0]
            if playlist_id:
                tracks = await self.get_playlist(playlist_id)
                return tracks, f"playlist ({len(tracks)} temas)"

            video_id = (params.get("v") or [None])[0]
            if not video_id and "youtu.be" in parsed.netloc:
                video_id = parsed.path.lstrip("/")
            if video_id:
                track = await self.get_track(video_id)
                return ([track] if track else []), "tema"

            # Spotify u otro link: caemos a buscar por el texto del link.
            if "spotify.com" in parsed.netloc:
                raise ValueError(
                    "Los links de Spotify no se pueden resolver sin sus credenciales. "
                    "Pasame el nombre del tema o una playlist de YouTube Music."
                )

        results = await self._run(self.ytm.search, query, filter="songs", limit=1)
        if not results:
            results = await self._run(self.ytm.search, query, limit=5)
        for item in results:
            track = _to_track(item)
            if track:
                return [track], "tema"
        return [], "nada"

    async def get_track(self, video_id: str) -> Track | None:
        data = await self._run(self.ytm.get_song, video_id)
        details = data.get("videoDetails", {})
        return Track(
            video_id=video_id,
            title=details.get("title") or "Sin título",
            artist=details.get("author") or "Desconocido",
            thumbnail=(details.get("thumbnail", {}).get("thumbnails") or [{}])[-1].get("url"),
        )

    async def get_playlist(self, playlist_id: str, limit: int = 200) -> list[Track]:
        data = await self._run(self.ytm.get_playlist, playlist_id, limit)
        tracks = [_to_track(t) for t in data.get("tracks", [])]
        return [t for t in tracks if t]

    async def get_library_playlists(self) -> list[dict]:
        if not self.authenticated:
            return []
        return await self._run(self.ytm.get_library_playlists, 50)

    async def get_radio(self, video_id: str, limit: int = 25) -> list[Track]:
        """El mix automático de YTM: esto es lo que hace que la música siga sola."""
        data = await self._run(
            self.ytm.get_watch_playlist, videoId=video_id, radio=True, limit=limit
        )
        tracks = [_to_track(t) for t in data.get("tracks", [])]
        return [t for t in tracks if t]

    # ---------- audio ----------

    async def stream_source(self, track: Track, volume: float = 0.5):
        """Resuelve la URL justo antes de reproducir: los links de Google expiran."""
        info = await self._run(self._extract, track.video_id)
        url = info["url"]
        source = discord.FFmpegPCMAudio(
            url, before_options=FFMPEG_BEFORE, options=FFMPEG_OPTS
        )
        buffered = BufferedAudioSource(source)
        await self._run(buffered.wait_until_ready)
        return discord.PCMVolumeTransformer(buffered, volume=volume)

    @staticmethod
    def _extract(video_id: str) -> dict:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
        if "entries" in info:
            info = info["entries"][0]
        return info
