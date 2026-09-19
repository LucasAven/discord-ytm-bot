# Bot de música privado (Discord + YouTube Music)

Bot de uso personal para un server chico. Usa tu propia sesión de YouTube Music,
así que reproduce tus playlists y, cuando se termina la cola, sigue solo con el
mix/radio de YTM (las mismas recomendaciones que te da la app).

## Cómo funciona

1. `ytmusicapi` habla con YouTube Music usando las cookies de tu navegador
   (sin API oficial, sin credenciales de Google Cloud).
2. `yt-dlp` resuelve la URL de audio del tema.
3. `FFmpeg` transcodifica ese stream y `discord.py` lo manda al canal de voz.

El autoplay usa `get_watch_playlist(..., radio=True)`, que es exactamente lo que
alimenta el "reproducción automática" de la app de YouTube Music.

## Setup

### 1. Crear el bot en Discord

1. https://discord.com/developers/applications → New Application.
2. Pestaña **Bot** → Reset Token → copiá el token.
3. Pestaña **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`;
   permisos `Connect`, `Speak`, `Send Messages`, `Use Slash Commands`.
4. Abrí la URL generada e invitá el bot a tu server.

No hace falta activar ningún Privileged Intent.

### 2. Sesión de YouTube Music

```bash
pip install ytmusicapi
ytmusicapi browser
```

Te va a pedir que pegues los **request headers** de una request a
`music.youtube.com` (DevTools → Network → cualquier request POST a
`/youtubei/v1/...` → Copy → Copy request headers). Eso genera `browser.json`.

Ese archivo es tu sesión: no lo subas a ningún lado. Dura varios meses; cuando
caduque, corré el comando de nuevo.

> **Si usás una cuenta de marca** (un canal aparte del personal, con su propio
> nombre y avatar), copiá los headers con ese canal activo y asegurate de que
> queden en `browser.json` las claves `x-goog-authuser` y `x-goog-pageid`. Sin
> ellas el bot se autentica con tu cuenta personal y solo ve `Liked Music` y
> `Episodes for Later`, sin ningún error que lo avise. Para saber si te está
> pasando, corré `/playlist` y contá si aparecen todas.

> Podés saltear este paso: el bot arranca igual, pero sin playlists privadas ni
> recomendaciones personalizadas.

### 3. Configurar

```bash
cp .env.example .env
```

Completá `DISCORD_TOKEN` y `GUILD_IDS` (el ID de tu server: click derecho sobre
el server con el Modo Desarrollador activado → Copiar ID).

### 4. Levantarlo

**Con Docker (recomendado, es lo portable):**

```bash
docker compose up -d --build
docker compose logs -f
```

**Sin Docker:**

```bash
# Necesitás ffmpeg instalado y en el PATH
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

## Comandos

| Comando | Qué hace |
|---|---|
| `/play <url o búsqueda>` | Tema suelto, playlist de YTM o búsqueda por texto |
| `/playlist [nombre]` | Lista tus playlists; con nombre, encola la que coincida |
| `/skip` | Siguiente |
| `/queue` | Muestra la cola y el estado del autoplay |
| `/autoplay` | Prende/apaga las recomendaciones automáticas |
| `/shuffle` | Mezcla la cola |
| `/pause` · `/resume` | Obvio |
| `/volume <0-100>` | Volumen |
| `/stop` | Corta todo y se desconecta |

Si el canal de voz queda vacío, o pasan 5 minutos sin nada que sonar, el bot se
va solo.

## Pasarle el proyecto a un amigo

Que se clone la carpeta, ponga **su propio** `browser.json` y su `.env`, y corra
`docker compose up -d`. El único cuidado: **que no lo corran los dos a la vez con
el mismo `DISCORD_TOKEN`** — Discord abre dos sesiones para el mismo bot y los
comandos empiezan a responder a duplicado. Si van a alternar, el que arranca
avisa y el otro hace `docker compose down`.

Si quieren tener los dos prendido al mismo tiempo, creen dos aplicaciones
distintas en el Developer Portal (dos bots, dos tokens) e invítenlas al mismo
server.

## Notas

- **Spotify**: la API no entrega audio, solo metadata. Los bots que "reproducen
  Spotify" en realidad leen los nombres de los temas y los buscan en YouTube.
  Para eso hace falta registrar una app en el dashboard de Spotify (gratis, pero
  es el paso de API que querías evitar). Por eso acá está sin soporte.
- Bajar audio de YouTube por fuera de sus clientes va contra sus Términos de
  Servicio. En un server privado entre amigos el riesgo práctico es bajo, pero
  es tu decisión.
- Si yt-dlp empieza a fallar de golpe (pasa cuando YouTube cambia algo), casi
  siempre se arregla con `pip install -U yt-dlp` y rebuild de la imagen.

## Estructura

```
bot.py       # slash commands y ciclo de vida
player.py    # cola, loop de reproducción y autoplay por guild
ytm.py       # YouTube Music (búsqueda, playlists, radio) + extracción de audio
```
