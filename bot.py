"""Bot de música privado para Discord, con YouTube Music como fuente."""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import subprocess
import sys

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import rutas
import sesion_ytm
from player import GuildPlayer
from ytm import YTMClient

load_dotenv(rutas.carpeta_de_datos() / ".env")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("bot")

TOKEN = os.getenv("DISCORD_TOKEN")
AUTH_FILE = os.getenv("YTM_AUTH_FILE") or str(
    rutas.carpeta_de_datos() / "browser.json"
)
GUILD_IDS = [
    int(g) for g in os.getenv("GUILD_IDS", "").replace(" ", "").split(",") if g
]
YTM_COOKIE = os.getenv("YTM_COOKIE", "")


def preparar_sesion_ytm() -> None:
    """Arma browser.json desde la cookie del .env, que es la unica via sin Docker.

    Rehace el archivo cuando la cookie del .env es otra, asi renovarla es
    pegar la nueva y volver a abrir el bot. Si algo falla avisa y sigue: el
    bot anda igual para buscar temas y para el autoplay.
    """
    if not YTM_COOKIE.strip():
        return

    archivo = pathlib.Path(AUTH_FILE)
    try:
        cookie = sesion_ytm.limpiar_cookie(YTM_COOKIE)
    except sesion_ytm.CookieInvalida as e:
        log.warning("YTM_COOKIE no sirve: %s", e)
        return

    if archivo.is_file() and sesion_ytm.cookie_guardada(archivo) == cookie:
        return

    log.info("Armando la sesion de YouTube Music desde YTM_COOKIE...")
    try:
        headers, como, playlists = sesion_ytm.armar(cookie)
    except sesion_ytm.CookieInvalida as e:
        log.warning("No pude usar YTM_COOKIE: %s", e)
        return
    except Exception:
        log.exception("Se rompio armando la sesion de YouTube Music")
        return

    try:
        sesion_ytm.guardar(headers, archivo)
    except OSError as e:
        log.warning("No pude escribir %s: %s", archivo, e)
        return

    log.info("Sesion lista (%s), %d playlists: %s",
             como, len(playlists), ", ".join(playlists) or "ninguna")
    if len(playlists) <= 2:
        log.warning(
            "Solo aparecen las que YouTube crea solo. Si tenes mas, copia la "
            "cookie otra vez con tu cuenta activa en music.youtube.com."
        )


preparar_sesion_ytm()

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


INTERACTION_DESCONOCIDA = 10062


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Traduce el 10062 a una linea que dice que hacer.

    Discord tira ese error cuando la interaction ya fue respondida, y eso pasa
    cuando hay dos bots prendidos con el mismo token: los dos reciben el
    comando y gana el que contesta primero. El traceback por defecto son
    quince lineas que terminan en un 404 y no nombran la causa. Visto desde
    Discord engana todavia mas, porque el bot contesta bien y no hace nada.
    """
    original = getattr(error, "original", error)
    comando = interaction.command.name if interaction.command else "?"

    if isinstance(original, discord.NotFound) and original.code == INTERACTION_DESCONOCIDA:
        log.warning(
            "/%s no se ejecuto: otra sesion del bot contesto primero. Casi "
            "seguro hay dos prendidos con el mismo token, apaga uno.",
            comando,
        )
        return

    log.exception("Fallo /%s", comando, exc_info=original)
    try:
        aviso = "⚠️ Se rompió ejecutando eso, probá de nuevo."
        if interaction.response.is_done():
            await interaction.followup.send(aviso)
        else:
            await interaction.response.send_message(aviso)
    except discord.HTTPException:
        pass


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
    # Discord invalida la interaction a los 3 segundos, y desconectarse del canal
    # puede tardar más que eso, así que primero avisamos y después cortamos.
    await interaction.response.defer()
    player = players.pop(interaction.guild.id, None)
    if player:
        await player.stop()
    else:
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
    await interaction.followup.send("👋 Listo, me fui.")


async def autotest() -> None:
    """Prueba que el ejecutable sirva, sin necesidad de token ni de Discord.

    La corre el workflow que compila el .exe. Un build que termina en verde
    igual puede estar entregando algo que se muere al abrirlo, y esa es la
    forma más fácil de mandarle a alguien un archivo que no anda.
    """
    print(f"python {sys.version.split()[0]} en {sys.platform}, "
          f"empaquetado={rutas.empaquetado()}")
    print(f"carpeta de datos: {rutas.carpeta_de_datos()}")

    binario = rutas.ffmpeg()
    salida = subprocess.run(
        [binario, "-version"], capture_output=True, text=True, timeout=60
    )
    if salida.returncode != 0:
        raise SystemExit(f"ffmpeg no corre: {binario}")
    adentro = binario.startswith(getattr(sys, "_MEIPASS", "\0"))
    print(f"ffmpeg ok ({'adentro del exe' if adentro else 'del PATH'}): "
          f"{salida.stdout.splitlines()[0]}")

    # Esto es lo que discord.py importa de verdad para cifrar la voz. Chequear
    # solo `import nacl` da verde con el bot igual de mudo.
    try:
        import nacl.secret  # noqa: F401
        import nacl.utils  # noqa: F401
    except Exception as e:
        raise SystemExit(f"PyNaCl no cargo ({e!r}), el bot no podria mandar audio")
    from discord.voice_client import has_nacl

    if not has_nacl:
        raise SystemExit("discord.py no ve PyNaCl, el bot no podria mandar audio")
    print("pynacl ok")


    discord.opus._load_default()
    if discord.opus.is_loaded():
        print("opus ok")
    elif sys.platform == "win32":
        # En Windows discord.py carga el .dll que trae adentro, asi que si aca
        # falla es que el empaquetado lo perdio y el bot no podria sonar.
        raise SystemExit("Opus no cargo, el bot no podria mandar audio")
    else:
        print("opus no cargo, normal fuera de Windows: ahi sale del sistema")

    tracks, _ = await ytm.resolve("bohemian rhapsody queen")
    if not tracks:
        raise SystemExit("La busqueda en YouTube Music no devolvio nada")
    print(f"busqueda ok: {tracks[0]}")

    tracks, kind = await ytm.resolve(
        "https://open.spotify.com/album/4m2880jivSbbyEGAKfITCa"
    )
    if len(tracks) < 5:
        raise SystemExit(f"Spotify devolvio solo {len(tracks)} temas")
    print(f"spotify ok: {len(tracks)} temas ({kind})")

    print("autotest ok")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        asyncio.run(autotest())
        raise SystemExit(0)
    if not TOKEN:
        raise SystemExit("Falta DISCORD_TOKEN en el .env")
    bot.run(TOKEN)
