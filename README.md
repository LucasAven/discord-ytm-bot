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
| `/play <url o búsqueda>` | Tema suelto, playlist de YTM, link de Spotify o búsqueda por texto |
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

Sirve para que el bot siga online cuando vos apagás tu máquina. La idea es que
tu amigo no necesita ninguna credencial tuya.

1. Creá una **segunda aplicación** en el Developer Portal, con su propio token,
   e invitá ese bot al mismo server. Así los dos pueden estar prendidos a la vez
   y nadie tiene que avisar quién lo está corriendo. Con un solo token compartido
   Discord abre dos sesiones del mismo bot y los comandos responden duplicado.
2. Corré `./preparar-copia.sh`, que arma la carpeta en el Escritorio con el
   código, los dos `.bat` y el `LEEME.txt`. Deja afuera `browser.json`, tu `.env`
   y el resto de tus cosas.
3. Completá `DISCORD_TOKEN` y `GUILD_IDS` en el `.env` de esa carpeta, comprimila
   y mandásela.

Él solo instala Docker Desktop y hace doble clic en `iniciar-bot.bat`. El
`LEEME.txt` se lo explica todo, incluido cómo apagarlo.

Esa copia corre **sin** `browser.json`, así que pierde tus playlists privadas y
las recomendaciones atadas a tu cuenta. Todo lo demás anda igual: búsqueda por
texto, links de YouTube y YouTube Music, y el autoplay por radio.

Si tu amigo quiere sus propias playlists, la copia trae
`conectar-mi-cuenta.bat`, que lo guía para copiar los headers y arma el
`browser.json` solo. Le pone la clave `authorization` y detecta si la cuenta es
de marca, que son los dos pasos que si no se hacen dejan la sesión andando a
medias sin avisar. Ese archivo es la sesión de Google de él y no se comparte.

Si querés que tenga tus playlists, la única forma sana es una cuenta de Google
aparte para el bot, con las playlists ahí. No le pases tu `browser.json`, que es
tu sesión de Google entera.

## Ejecutable para Windows (en curso)

La idea es que el amigo no instale Docker. `.github/workflows/windows.yml`
compila un `.exe` con PyInstaller en un runner de Windows, que es obligatorio
porque PyInstaller no cross-compila: desde una Mac no se puede.

Se dispara a mano desde la pestaña Actions, o solo al pushear un tag `v*`. El
artefacto que deja es `bot-de-musica-windows.zip`.

Antes de empaquetar, el workflow corre `bot-de-musica.exe --autotest` sobre el
ejecutable recién compilado. Ese modo chequea ffmpeg, PyNaCl, Opus, una
búsqueda en YouTube Music y un link de Spotify. Un build verde sin eso puede
estar entregando un exe que se muere al abrirlo, que es la peor forma de
mandarle algo a alguien que no va a saber qué mirar.

`rutas.py` es lo que hace que el mismo código sirva suelto y empaquetado.
ffmpeg viaja adentro del ejecutable y sale de `sys._MEIPASS`; `.env` y
`browser.json` quedan al lado del ejecutable para que se puedan cambiar.

**docker2exe y compose2exe no sirven para esto.** Los dos meten la imagen
adentro de un binario, pero ese binario igual necesita Docker corriendo en la
máquina que lo ejecuta. Lo dicen los dos README. Sacan la descarga de la
imagen, no la instalación de Docker Desktop.

## Notas

- **Spotify**: la API no entrega audio, solo metadata, así que `spotify.py` lee
  los nombres de los temas y después cada uno se busca en YouTube Music. Lo que
  suena es la versión de YouTube, que no siempre es la misma grabación.
  Andan los links de tema, álbum y playlist pública, sin credenciales, porque
  los datos salen de la página del reproductor incrustable. Dos límites que
  vienen de Spotify: devuelve **100 temas como máximo** por lista y no dice
  cuántos eran en total, y es una página web y no una API, así que el día que
  cambien el formato hay que arreglar el parser. Cuando eso pase, el bot lo
  detecta y lo dice en el mensaje en vez de romperse.
- Bajar audio de YouTube por fuera de sus clientes va contra sus Términos de
  Servicio. En un server privado entre amigos el riesgo práctico es bajo, pero
  es tu decisión.
- Si yt-dlp empieza a fallar de golpe (pasa cuando YouTube cambia algo), casi
  siempre se arregla con `pip install -U yt-dlp` y rebuild de la imagen.

## Estructura

```
bot.py       # slash commands, ciclo de vida y el modo --autotest
player.py    # cola, loop de reproducción y autoplay por guild
ytm.py       # YouTube Music (búsqueda, playlists, radio) + extracción de audio
spotify.py   # lee temas de links de Spotify, sin credenciales
rutas.py     # dónde están los archivos: suelto o adentro del ejecutable
```
