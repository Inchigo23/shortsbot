"""Configuración: se lee de config.json (se crea con valores por defecto si no existe)."""
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARCHIVO = BASE / "config.json"

POR_DEFECTO = {
    # Carpetas donde el bot busca vídeos nuevos (se miran también las subcarpetas).
    # NVIDIA guarda las repeticiones en Videos\NVIDIA\<Juego>\...
    "carpetas_vigiladas": ["%USERPROFILE%\\Videos\\NVIDIA", "entrada"],
    # Límite de subidas para que YouTube no lo vea como spam.
    "max_shorts_por_dia": 2,
    "horas_entre_subidas": 4,
    "horario_subida": [12, 22],  # solo sube entre las 12:00 y las 22:00
    # "private" hasta que Google verifique tu app; luego puedes poner "public".
    "privacidad": "private",
    "subir_a_youtube": True,
    # Duración de cada Short en segundos [mínimo, máximo].
    "duracion_short": [15, 45],
    # De un vídeo largo (>4 min) saca como mucho estos Shorts.
    "max_shorts_por_video": 3,
    # No edita ni sube mientras juegas, para no darte lag.
    "pausar_mientras_juegas": True,
    "procesos_juego": ["javaw.exe", "Minecraft.Windows.exe"],
    # Títulos con Claude (necesita una API key de Anthropic). Si no, usa plantillas.
    "usar_claude": True,
    "modelo_claude": "claude-opus-5",
    "minutos_entre_busquedas": 2,
    # Limpieza: borra la copia local de los Shorts ya subidos a YouTube (y de los descartados) pasados
    # estos días. Nunca toca tus grabaciones originales.
    "borrar_subidos_tras_dias": 1,
    "borrar_descartados_tras_dias": 3,
    # Estudio: vídeos hechos desde cero con guiones de Claude (carpeta guiones/pendientes).
    "hacer_videos_propios": True,
    "hora_guionistas": 10,        # a esta hora Claude escribe los guiones del día (tarea programada)
    "guiones_por_dia": 2,
    # Voz: "piper" o "kokoro" (locales y gratis) o "google" (necesita facturación en Google Cloud).
    "voz": "piper",
    "voz_piper": "es_ES-davefx-medium",   # o "es_ES-sharvard-medium"
    "voz_piper_hablante": None,           # sharvard: "M" (hombre) o "F" (mujer)
    "voz_kokoro": "em_alex",              # em_alex (hombre), ef_dora (mujer), em_santa (hombre)
    "voz_google": "es-ES-Chirp3-HD-Puck",
    # Marca el vídeo como "contenido alterado o sintético" en YouTube. Solo es obligatorio si el
    # contenido parece real; una animación de bloques con voz de IA no lo necesita.
    "marcar_sintetico": False,
    "puerto_panel": 8765,
}


def _ruta(p):
    p = Path(os.path.expandvars(os.path.expanduser(p)))
    return p if p.is_absolute() else BASE / p


def cargar():
    cfg = dict(POR_DEFECTO)
    if ARCHIVO.exists():
        cfg.update(json.loads(ARCHIVO.read_text(encoding="utf-8")))
    else:
        ARCHIVO.write_text(json.dumps(POR_DEFECTO, ensure_ascii=False, indent=2), encoding="utf-8")
    cfg["carpetas"] = [_ruta(p) for p in cfg["carpetas_vigiladas"]]
    for c in cfg["carpetas"]:
        if c.parent == BASE or BASE in c.parents:
            c.mkdir(parents=True, exist_ok=True)
    return cfg
