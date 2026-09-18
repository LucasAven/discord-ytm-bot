"""Un reproductor por guild: cola, loop de reproducción y autoplay vía radio de YTM."""

from __future__ import annotations

import asyncio
import logging
import random

import discord

from ytm import Track, YTMClient

log = logging.getLogger(__name__)

IDLE_TIMEOUT = 300  # se desconecta solo después de 5 min sin nada que sonar
RADIO_BATCH = 15


class GuildPlayer:
    def __init__(
        self,
        bot: discord.Client,
        guild: discord.Guild,
        ytm: YTMClient,
        text_channel: discord.abc.Messageable,
    ):
        self.bot = bot
        self.guild = guild
        self.ytm = ytm
        self.text_channel = text_channel

        self.queue: list[Track] = []
        self.current: Track | None = None
        self.autoplay = True
        self.volume = 0.5

        self._played_ids: set[str] = set()
        self._tracks_added = asyncio.Event()
        self._track_finished = asyncio.Event()
        self._radio_seed: str | None = None

        self.task = bot.loop.create_task(self._loop())

    # ---------- API pública ----------

    def add(self, tracks: list[Track]) -> None:
        self.queue.extend(tracks)
        if tracks and self._radio_seed is None:
            self._radio_seed = tracks[0].video_id
        self._tracks_added.set()

    def add_next(self, track: Track) -> None:
        self.queue.insert(0, track)
        self._tracks_added.set()

    def shuffle(self) -> None:
        random.shuffle(self.queue)

    def clear(self) -> None:
        self.queue.clear()

    def skip(self) -> bool:
        vc = self.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()  # dispara el callback `after` y el loop sigue
            return True
        return False

    async def stop(self) -> None:
        self.queue.clear()
        self.autoplay = False
        self.task.cancel()
        vc = self.guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()

    # ---------- interno ----------

    async def _next_track(self) -> Track | None:
        while True:
            if self.queue:
                return self.queue.pop(0)

            if self.autoplay and self._radio_seed:
                await self._extend_with_radio()
                if self.queue:
                    return self.queue.pop(0)

            self._tracks_added.clear()
            try:
                await asyncio.wait_for(self._tracks_added.wait(), timeout=IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                return None

    async def _extend_with_radio(self) -> None:
        seed = (self.current.video_id if self.current else None) or self._radio_seed
        try:
            candidates = await self.ytm.get_radio(seed, limit=RADIO_BATCH * 2)
        except Exception:
            log.exception("Falló el radio de YTM")
            return

        nuevos = [t for t in candidates if t.video_id not in self._played_ids]
        if not nuevos:
            # Si ya sonó todo el mix, reseteamos el historial para no quedarnos mudos.
            self._played_ids.clear()
            nuevos = candidates

        if nuevos:
            self.queue.extend(nuevos[:RADIO_BATCH])
            await self._send(
                f"🔁 Autoplay: agregué {len(nuevos[:RADIO_BATCH])} temas parecidos."
            )

    async def _loop(self) -> None:
        try:
            while not self.bot.is_closed():
                track = await self._next_track()
                if track is None:
                    await self._send("💤 Nada sonando hace rato, me voy.")
                    await self._disconnect()
                    return

                vc = self.guild.voice_client
                if vc is None or not vc.is_connected():
                    return

                try:
                    source = await self.ytm.stream_source(track, self.volume)
                except Exception:
                    log.exception("No pude extraer el stream de %s", track)
                    await self._send(f"⚠️ No pude reproducir **{track}**, sigo con el que viene.")
                    continue

                self.current = track
                self._played_ids.add(track.video_id)
                self._track_finished.clear()

                vc.play(
                    source,
                    after=lambda err: self.bot.loop.call_soon_threadsafe(
                        self._track_finished.set
                    ),
                )
                await self._send(embed=self._now_playing_embed(track))
                await self._track_finished.wait()
                source.cleanup()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("El loop del player explotó")

    def _now_playing_embed(self, track: Track) -> discord.Embed:
        embed = discord.Embed(
            title=track.title,
            url=track.url,
            description=track.artist,
            color=discord.Color.red(),
        )
        embed.set_author(name="Sonando ahora")
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        if track.duration:
            embed.add_field(name="Duración", value=track.duration)
        if track.requested_by:
            embed.set_footer(text=f"Pedido por {track.requested_by}")
        return embed

    async def _send(self, content: str | None = None, embed: discord.Embed | None = None):
        try:
            await self.text_channel.send(content=content, embed=embed)
        except discord.HTTPException:
            pass

    async def _disconnect(self) -> None:
        vc = self.guild.voice_client
        if vc:
            await vc.disconnect()
