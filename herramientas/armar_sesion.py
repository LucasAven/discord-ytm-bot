"""Arma browser.json a partir de los headers que la persona pegó.

Corre adentro del container, lo lanza `conectar-mi-cuenta.bat`. Lee
/trabajo/headers.txt y escribe /trabajo/browser.json. No manda nada a ningún
lado y no imprime la cookie.

Toda la lógica de la sesión vive en `sesion_ytm.py`, que es el mismo módulo que
usa el bot cuando encuentra `YTM_COOKIE` en el `.env`. Acá solo está la parte
de leer lo pegado y hablarle a la persona.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import sesion_ytm  # noqa: E402  hace falta el sys.path de arriba

TRABAJO = pathlib.Path("/trabajo")
ENTRADA = TRABAJO / "headers.txt"
SALIDA = TRABAJO / "browser.json"


def morir(mensaje: str) -> None:
    print()
    print("  NO SE PUDO.")
    print(f"  {mensaje}")
    print()
    sys.exit(1)


def leer_headers_pegados() -> tuple[str, str]:
    """Devuelve (cookie, user_agent) de lo que haya pegado la persona."""
    if not ENTRADA.is_file():
        morir("No encontre el archivo headers.txt.")

    crudo = ENTRADA.read_text(encoding="utf-8", errors="replace")
    if not crudo.strip():
        morir("El archivo headers.txt quedo vacio. Tenes que pegar el texto y guardar.")

    cookie = ""
    user_agent = ""
    for linea in crudo.splitlines():
        limpia = linea.strip().lstrip(":")
        clave, sep, valor = limpia.partition(":")
        if not sep:
            continue
        clave = clave.strip().lower()
        valor = valor.strip()
        if clave == "cookie" and len(valor) > len(cookie):
            cookie = valor
        elif clave == "user-agent" and valor:
            user_agent = valor

    if not cookie and "SAPISID=" in crudo:
        # Pegó la cookie sola, sin el nombre del header adelante.
        cookie = " ".join(crudo.split())

    if not cookie:
        morir(
            "No encontre la linea que empieza con 'cookie:'. Fijate de haber "
            "copiado los headers enteros y no otra cosa."
        )
    return cookie, user_agent


def main() -> None:
    print()
    print("  Leyendo lo que pegaste...")
    cookie, user_agent = leer_headers_pegados()

    print("  Probando la sesion contra YouTube Music...")
    try:
        headers, como, playlists = sesion_ytm.armar(cookie, user_agent or None)
    except sesion_ytm.CookieInvalida as e:
        morir(str(e))
    except Exception as e:
        morir(f"Algo salio mal hablando con YouTube Music: {e}")

    sesion_ytm.guardar(headers, SALIDA)

    print()
    print("  ===============================")
    print("   Listo, tu sesion quedo guardada.")
    print("  ===============================")
    print()
    print(f"  Se conecto como: {como}")
    print(f"  Playlists que ve el bot: {len(playlists)}")
    for titulo in playlists:
        print(f"    - {titulo}")
    print()
    if len(playlists) <= 2:
        print("  Solo aparecen las dos que YouTube crea solo. Si vos tenes mas,")
        print("  fijate de haber copiado los headers con tu cuenta activa en la")
        print("  pagina, y proba de nuevo.")
        print()


if __name__ == "__main__":
    main()
