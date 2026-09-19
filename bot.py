"""Bot de música privado para Discord, con YouTube Music como fuente."""

from __future__ import annotations

import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from player import GuildPlayer
from ytm import YTMClient

load_dotenv()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("bot")

TOKEN = os.getenv("DISCORD_TOKEN")
AUTH_FILE = os.getenv("YTM_AUTH_FILE", "browser.json")
GUILD_IDS = [
    int(g) for g in os.getenv("GUILD_IDS", "").replace(" ", "").split(",") if g
]

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
ytm = YTMClient(AUTH_FILE)
players: dict[int, GuildPlayer] = {}


async def get_player(interaction: discord.Interaction) -> GuildPlayer | None:
    """Conecta al canal de voz del usuario y devuelve (o crea) el player del guild."""
    user = interaction.user
    if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
        await interaction.followup.send("Metete en un canal de voz primero 🙂")
        return None

    channel = user.voice.channel
    vc = interaction.guild.voice_client
    if vc is None:
        vc = await channel.connect(self_deaf=True)
    elif vc.channel != channel:
        await vc.move_to(channel)

    # connect() agota sus 5 intentos y vuelve sin conectar en vez de tirar error,
    # así que sin este chequeo el bot encola el tema y no suena nada.
    if not vc.is_connected():
        await vc.disconnect(force=True)
        await interaction.followup.send("⚠️ No pude conectarme al canal de voz, probá de nuevo.")
        return None

    player = players.get(interaction.guild.id)
    if player is None or player.task.done():
        player = GuildPlayer(bot, interaction.guild, ytm, interaction.channel)
        players[interaction.guild.id] = player
    else:
        player.text_channel = interaction.channel
    return player


@bot.event
async def on_ready():
    try:
        if GUILD_IDS:
            for gid in GUILD_IDS:
                guild = discord.Object(id=gid)
                bot.tree.copy_global_to(guild=guild)
                await bot.tree.sync(guild=guild)
            log.info("Comandos sincronizados en %s", GUILD_IDS)
        else:
            await bot.tree.sync()
            log.info("Comandos sincronizados globalmente (puede tardar ~1h)")
    except Exception:
        log.exception("No pude sincronizar los comandos")
    log.info("Conectado como %s", bot.user)


@bot.event
async def on_voice_state_update(member, before, after):
    """Si el canal queda vacío, el bot se va solo."""
    if member.bot:
        return
    vc = member.guild.voice_client
    if vc and len([m for m in vc.channel.members if not m.bot]) == 0:
        player = players.pop(member.guild.id, None)
        if player:
            await player.stop()
        elif vc.is_connected():
            await vc.disconnect()


@bot.tree.command(name="play", description="Reproduce un tema, una playlist de YT Music o una búsqueda")
@app_commands.describe(query="URL de YouTube Music o texto para buscar")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    player = await get_player(interaction)
    if player is None:
        return

    try:
        tracks, kind = await ytm.resolve(query)
    except ValueError as e:
        await interaction.followup.send(f"⚠️ {str(e)}")
        return
    except Exception:
        log.exception("Falló resolve(%s)", query)
        await interaction.followup.send("⚠️ Se rompió buscando eso, probá de nuevo.")
        return

    if not tracks:
        await interaction.followup.send("No encontré nada con eso 🤔")
        return

    for t in tracks:
        t.requested_by = interaction.user.display_name
    player.add(tracks)

    if len(tracks) == 1:
        await interaction.followup.send(f"➕ A la cola: **{tracks[0]}**")
    else:
        await interaction.followup.send(f"➕ Agregué {len(tracks)} temas ({kind}).")


@bot.tree.command(name="playlist", description="Lista tus playlists de YouTube Music y reproduce una")
@app_commands.describe(nombre="Parte del nombre de la playlist")
async def playlist(interaction: discord.Interaction, nombre: str | None = None):
    await interaction.response.defer()
    if not ytm.authenticated:
        await interaction.followup.send(
            "No hay sesión de YouTube Music configurada (falta `browser.json`)."
        )
        return

    items = await ytm.get_library_playlists()
    if not items:
        await interaction.followup.send("No encontré playlists en tu biblioteca.")
        return

    if nombre is None:
        listado = "\n".join(f"• {p['title']}" for p in items[:25])
        await interaction.followup.send(f"**Tus playlists:**\n{listado}")
        return

    match = next((p for p in items if nombre.lower() in p["title"].lower()), None)
    if match is None:
        await interaction.followup.send(f"No encontré ninguna que diga «{nombre}».")
        return

    player = await get_player(interaction)
    if player is None:
        return

    tracks = await ytm.get_playlist(match["playlistId"])
    for t in tracks:
        t.requested_by = interaction.user.display_name
    player.add(tracks)
    await interaction.followup.send(
        f"➕ **{match['title']}**: {len(tracks)} temas a la cola."
    )


@bot.tree.command(name="skip", description="Saltea el tema actual")
async def skip(interaction: discord.Interaction):
    player = players.get(interaction.guild.id)
    if player and player.skip():
        await interaction.response.send_message("⏭️ Siguiente.")
    else:
        await interaction.response.send_message("No hay nada sonando.")


@bot.tree.command(name="queue", description="Muestra la cola")
async def queue(interaction: discord.Interaction):
    player = players.get(interaction.guild.id)
    if not player or (not player.queue and not player.current):
        await interaction.response.send_message("La cola está vacía.")
        return

    lineas = []
    if player.current:
        lineas.append(f"**Ahora:** {player.current}")
    for i, t in enumerate(player.queue[:10], start=1):
        lineas.append(f"{i}. {t}")
    restantes = len(player.queue) - 10
    if restantes > 0:
        lineas.append(f"...y {restantes} más")
    lineas.append(f"\nAutoplay: {'on' if player.autoplay else 'off'}")
    await interaction.response.send_message("\n".join(lineas))


@bot.tree.command(name="autoplay", description="Prende o apaga las recomendaciones automáticas")
async def autoplay(interaction: discord.Interaction):
    player = players.get(interaction.guild.id)
    if not player:
        await interaction.response.send_message("No hay nada andando.")
        return
    player.autoplay = not player.autoplay
    estado = "activado" if player.autoplay else "desactivado"
    await interaction.response.send_message(f"🔁 Autoplay {estado}.")


@bot.tree.command(name="shuffle", description="Mezcla la cola")
async def shuffle(interaction: discord.Interaction):
    player = players.get(interaction.guild.id)
    if not player or not player.queue:
        await interaction.response.send_message("No hay cola para mezclar.")
        return
    player.shuffle()
    await interaction.response.send_message("🔀 Mezclada.")


@bot.tree.command(name="pause", description="Pausa la reproducción")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ Pausado.")
    else:
        await interaction.response.send_message("No hay nada sonando.")


@bot.tree.command(name="resume", description="Reanuda la reproducción")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ Dale.")
    else:
        await interaction.response.send_message("No hay nada pausado.")


@bot.tree.command(name="volume", description="Cambia el volumen (0-100)")
async def volume(interaction: discord.Interaction, nivel: app_commands.Range[int, 0, 100]):
    player = players.get(interaction.guild.id)
    if not player:
        await interaction.response.send_message("No hay nada andando.")
        return
    player.volume = nivel / 100
    vc = interaction.guild.voice_client
    if vc and vc.source:
        vc.source.volume = player.volume
    await interaction.response.send_message(f"🔊 Volumen al {nivel}%.")


@bot.tree.command(name="stop", description="Corta todo y se va del canal")
async def stop(interaction: discord.Interaction):
    player = players.pop(interaction.guild.id, None)
    if player:
        await player.stop()
        await interaction.response.send_message("👋 Listo, me fui.")
    else:
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
        await interaction.response.send_message("👋")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Falta DISCORD_TOKEN en el .env")
    bot.run(TOKEN)
