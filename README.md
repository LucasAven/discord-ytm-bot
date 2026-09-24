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

Opcional. Sin esto el bot busca temas, acepta links de YouTube Music y de
Spotify y hace autoplay; lo que suma es ver **tus** playlists.

Se hace pegando la cookie del navegador en `YTM_COOKIE`, dentro del `.env`:

1. Abrí `music.youtube.com` con tu cuenta iniciada.
2. F12 → solapa **Network**.
3. Clic en cualquier tema, para que se mueva algo.
4. Escribí `youtubei` en el filtro y hacé clic en el primer renglón.
5. Solapa **Headers** → botón **Raw**, al lado de *Request Headers*.
6. Copiá el renglón que empieza con `cookie:`.

Va en un solo renglón y entre comillas. Al arrancar, `sesion_ytm.py` arma el
`browser.json` solo, y hace los dos retoques que `ytmusicapi` no hace:

- Calcula la clave `authorization`. Sin ella el archivo se lee como OAuth y
  `YTMusic()` falla con un error que habla de otra cosa.
- Detecta si la cuenta es de marca, o sea un canal aparte del personal, y
  guarda `x-goog-authuser` y `x-goog-pageid`. Sin eso la sesión queda como la
  cuenta personal, ve solo `Liked Music` y `Episodes for Later`, y los links a
  playlists propias fallan como si no existieran, sin ningún error que lo avise.

Para comprobar que quedó bien, el log dice `Sesion lista` con la lista, y
`/playlist` las muestra.

La cookie es tu sesión de Google: no la subas a ningún lado. Vence cada tanto, y
el síntoma engaña, porque el bot sigue diciendo "YTMusic autenticado" pero deja
de ver playlists. Pegá la nueva en el `.env` y reiniciá: el archivo se rehace
solo cuando la cookie cambió.

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

Sirve para que el bot siga online cuando vos apagás tu máquina. Él no necesita
ninguna credencial tuya, ni instalar nada.

1. Creá una **segunda aplicación** en el Developer Portal, con su propio token,
   e invitá ese bot al mismo server. Con un token compartido Discord abre dos
   sesiones del mismo bot: las dos reciben cada comando, gana la que contesta
   primero y la otra muere con `10062`. El síntoma engaña, porque el bot
   contesta bien y no hace nada.
2. Bajá `bot-de-musica-windows.zip` del último run, en la pestaña **Actions**.
3. Completá `DISCORD_TOKEN` y `GUILD_IDS` en el `.env` que viene adentro del
   zip, y mandáselo.

Él descomprime y hace doble clic en el `.exe`. El `LEEME.txt` del zip le explica
el resto: el cartel de SmartScreen que sale la primera vez, cómo apagarlo, y
cómo poner su propia `YTM_COOKIE` si quiere sus playlists.

No le pases tu `browser.json` ni tu `YTM_COOKIE`, que son tu sesión de Google
entera. Si querés que el bot tenga *tus* playlists en la máquina de él, la única
forma sana es una cuenta de Google aparte para el bot, con las playlists ahí.

## Cómo se compila el .exe

`.github/workflows/windows.yml` lo arma con PyInstaller en un runner de Windows.
El runner es obligatorio porque PyInstaller no cross-compila: desde una Mac no
se puede.

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

Las playlists propias van por `YTM_COOKIE`, igual que acá, porque `sesion_ytm.py`
viaja adentro del ejecutable. Si la cookie no sirve, avisa en el log y sigue sin
sesión, sin pisar el `browser.json` que ya estuviera.

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
spotify.py    # lee temas de links de Spotify, sin credenciales
rutas.py      # dónde están los archivos: suelto o adentro del ejecutable
sesion_ytm.py # arma browser.json desde la cookie del navegador
```
