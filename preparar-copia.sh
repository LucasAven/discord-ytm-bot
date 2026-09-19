#!/usr/bin/env bash
# Arma la carpeta que se le pasa a un amigo para que corra el bot en su PC.
# Deja afuera browser.json y el .env propio, que son credenciales.
set -euo pipefail

ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO="${1:-$HOME/Desktop/bot-de-musica}"

rm -rf "$DESTINO"
mkdir -p "$DESTINO"

for f in Dockerfile docker-compose.yml requirements.txt bot.py player.py ytm.py \
         iniciar-bot.bat apagar-bot.bat conectar-mi-cuenta.bat LEEME.txt; do
    cp "$ORIGEN/$f" "$DESTINO/$f"
done
mkdir -p "$DESTINO/herramientas"
cp "$ORIGEN/herramientas/armar_sesion.py" "$DESTINO/herramientas/"

cat > "$DESTINO/.env" <<'ENV'
# Token del SEGUNDO bot, no el tuyo. Developer Portal, nueva
# aplicacion, pestana Bot, Reset Token.
DISCORD_TOKEN=

# El ID del server. El mismo que usas vos.
GUILD_IDS=
ENV

# La red de seguridad de todo esto: que no se cuele ninguna credencial.
# Hoy no puede pasar porque arriba se copia una lista fija, pero si alguien
# la cambia por un cp -r esto lo frena antes de que la carpeta salga.
for prohibido in browser.json oauth.json .venv .git backlog.md; do
    if [ -e "$DESTINO/$prohibido" ]; then
        echo "ERROR: se colo $prohibido en la copia. No la mandes." >&2
        exit 1
    fi
done

echo "Copia lista en: $DESTINO"
echo
echo "Falta que completes DISCORD_TOKEN y GUILD_IDS en $DESTINO/.env"
echo "Despues comprimi la carpeta y mandasela."
