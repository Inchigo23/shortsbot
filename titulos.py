"""Títulos, descripción y etiquetas. Con Claude (mira fotogramas del clip) o con plantillas."""
import base64
import os
import random
import re
from pathlib import Path

from pydantic import BaseModel

import estado


class IdeasShort(BaseModel):
    juego: str
    texto_en_pantalla: str
    titulo: str
    descripcion: str
    etiquetas: list[str]
    publicable: bool
    motivo: str


INSTRUCCIONES = """Eres el editor de un canal de YouTube Shorts de gaming en español (España).
Te paso {n} fotogramas de un clip de {segundos:.0f} segundos grabado en el PC del dueño del canal.
Pista sobre el juego (puede estar vacía o equivocada): "{pista}".

Devuelve:
- juego: nombre del juego que se ve.
- texto_en_pantalla: gancho corto que irá escrito encima del vídeo, máximo 32 caracteres, sin hashtags.
- titulo: título del Short, máximo 80 caracteres, llamativo pero sin mentir sobre lo que pasa; puede llevar 1 emoji.
- descripcion: 1-2 frases naturales + 3-5 hashtags al final (incluye #shorts).
- etiquetas: 5-10 etiquetas de búsqueda.
- publicable: false si en los fotogramas no pasa nada (menús, pantallas de carga, personaje quieto),
  si no es un videojuego, o si se ve información personal (escritorio, chats privados, nombres reales,
  correos, direcciones). En cualquier otro caso true.
- motivo: una frase explicando por qué es o no publicable."""

PLANTILLAS = [
    ("NO ME LO ESPERABA", "{j}: esto no me lo esperaba 😳"),
    ("CASI LO PIERDO TODO", "Casi lo pierdo todo en {j} 💀"),
    ("MOMENTO ÉPICO", "Momento épico en {j} 🔥"),
    ("¿CÓMO HE SOBREVIVIDO?", "¿Cómo he sobrevivido a esto? | {j}"),
    ("ESPERA AL FINAL...", "Espera al final... 👀 | {j}"),
    ("ESTO SALIÓ MAL", "Esto salió muy mal en {j} 😂"),
]

_claude_disponible = bool(
    os.environ.get("ANTHROPIC_API_KEY")
    or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    or (Path.home() / ".config" / "anthropic").exists()  # perfil de `ant auth login`
)


def _hashtag(texto):
    return "#" + re.sub(r"[^\w]", "", texto.title(), flags=re.UNICODE)


def plantilla(juego):
    juego = juego or "Minecraft"
    rotulo, titulo = random.choice(PLANTILLAS)
    return {
        "juego": juego,
        "texto_en_pantalla": rotulo,
        "titulo": titulo.format(j=juego),
        "descripcion": f"Clip de {juego} 🎮\n\n#shorts {_hashtag(juego)} #gaming",
        "etiquetas": [juego, "shorts", "gaming", f"{juego} clips", "momentos épicos"],
        "publicable": True,
        "motivo": "Título automático (plantilla)",
        "autor": "plantilla",
    }


def _con_claude(fotos, pista, segundos, modelo):
    import anthropic

    global _claude_disponible
    cliente = anthropic.Anthropic()
    contenido = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                     "data": base64.standard_b64encode(f.read_bytes()).decode()}}
        for f in fotos
    ]
    contenido.append({"type": "text", "text": INSTRUCCIONES.format(n=len(fotos), segundos=segundos, pista=pista)})
    try:
        respuesta = cliente.beta.messages.parse(
            model=modelo,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            output_format=IdeasShort,
            messages=[{"role": "user", "content": contenido}],
        )
    except TypeError:  # el SDK no encuentra ninguna credencial
        _claude_disponible = False
        estado.log("No hay API key de Anthropic: uso títulos de plantilla.", "aviso")
        return None
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        _claude_disponible = False
        estado.log("La API key de Anthropic no es válida: uso títulos de plantilla.", "error")
        return None
    except anthropic.RateLimitError:
        estado.log("Claude está saturado ahora mismo: uso una plantilla para este Short.", "aviso")
        return None
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        estado.log(f"Fallo al pedir el título a Claude ({e.__class__.__name__}): uso una plantilla.", "aviso")
        return None

    if respuesta.stop_reason == "refusal" or respuesta.parsed_output is None:
        return None
    ideas = respuesta.parsed_output.model_dump()
    ideas["autor"] = "claude"
    return ideas


def generar(fotos, pista, segundos, cfg):
    ideas = None
    if cfg["usar_claude"] and _claude_disponible and fotos:
        ideas = _con_claude(fotos, pista, segundos, cfg["modelo_claude"])
    if ideas is None:
        ideas = plantilla(pista)
    ideas["texto_en_pantalla"] = ideas["texto_en_pantalla"][:40]
    titulo = ideas["titulo"].strip()[:100]
    if "#shorts" not in titulo.lower() and len(titulo) <= 91:
        titulo += " #shorts"
    ideas["titulo"] = titulo
    ideas["etiquetas"] = [e[:30] for e in ideas["etiquetas"]][:15]
    return ideas


def modo():
    return "claude" if _claude_disponible else "plantilla"
