"""Estudio: convierte un guion escrito por Claude en un Short completo.

Guion (guiones/pendientes/*.json):
{
  "titulo": "El creeper nació por un error 😳",
  "gancho": "EL CREEPER FUE UN ERROR",          # texto fijo arriba del vídeo (máx. ~30 letras)
  "narracion": ["Frase 1.", "Frase 2.", ...],   # 90-140 palabras en total (unos 35-50 s)
  "descripcion": "Texto + #hashtags",
  "etiquetas": ["minecraft", "curiosidades"],
  "fuentes": ["https://minecraft.wiki/..."],     # de dónde salen los datos
  "escena": {"bioma": "bosque", "hora": "dia", "modo": "parkour"}   # opcional
}
"""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import animacion
import editor
import estado
import voz

BASE = Path(__file__).resolve().parent
GUIONES = BASE / "guiones"
PENDIENTES, HECHOS, ERRORES = GUIONES / "pendientes", GUIONES / "hechos", GUIONES / "errores"
FUENTES = estado.DATOS / "fuentes"
TMP = estado.DATOS / "tmp"
SHORTS = BASE / "shorts"
MINIS = estado.DATOS / "miniaturas"
for _c in (PENDIENTES, HECHOS, ERRORES, FUENTES, TMP, SHORTS, MINIS):
    _c.mkdir(parents=True, exist_ok=True)

# Letra de los subtítulos: Segoe UI Black si estamos en tu Windows; si no (en la nube), Anton (licencia OFL,
# carpeta fuentes/ del repositorio).
_SEGOE = Path(r"C:\Windows\Fonts\seguibl.ttf")
if _SEGOE.exists():
    if not (FUENTES / _SEGOE.name).exists():
        shutil.copy(_SEGOE, FUENTES / _SEGOE.name)
    FUENTE_NOMBRE = "Segoe UI Black"
else:
    FUENTES, FUENTE_NOMBRE = BASE / "fuentes", "Anton"


def pendientes():
    return sorted(PENDIENTES.glob("*.json"), key=lambda p: p.stat().st_mtime)


def leer(ruta):
    return validar(json.loads(Path(ruta).read_text(encoding="utf-8")))


def validar(g):
    for campo in ("titulo", "gancho", "narracion", "descripcion"):
        if not g.get(campo):
            raise ValueError(f"al guion le falta «{campo}»")
    if not isinstance(g["narracion"], list) or not all(isinstance(f, str) for f in g["narracion"]):
        raise ValueError("«narracion» tiene que ser una lista de frases")
    palabras = sum(len(f.split()) for f in g["narracion"])
    if not 25 <= palabras <= 220:
        raise ValueError(f"la narración tiene {palabras} palabras (tiene que tener entre 25 y 220)")
    g.setdefault("etiquetas", ["minecraft", "curiosidades", "shorts"])
    g.setdefault("fuentes", [])
    return g


# ------------------------------------------------------------- subtítulos

def _t(seg):
    h, resto = divmod(max(0.0, seg), 3600)
    m, s = divmod(resto, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _limpio(texto):
    return re.sub(r"[{}\\]", "", texto).upper()


def _trozos(tiempos, max_palabras=3, max_letras=16):
    trozos, actual = [], []
    for p in tiempos:
        actual.append(p)
        if (len(actual) >= max_palabras or len(" ".join(w for w, _, _ in actual)) >= max_letras
                or p[0][-1:] in ",.;:?!"):
            trozos.append(actual)
            actual = []
    if actual:
        trozos.append(actual)
    return trozos


def _gancho_en_lineas(texto):
    palabras = _limpio(texto).split()
    if len(" ".join(palabras)) <= 14 or len(palabras) < 2:
        return "{\\c&H00D7FF&}" + " ".join(palabras)
    corte = min(range(1, len(palabras)), key=lambda i: abs(len(" ".join(palabras[:i])) - len(" ".join(palabras[i:]))))
    return "{\\c&H00D7FF&}" + " ".join(palabras[:corte]) + "\\N{\\c&HFFFFFF&}" + " ".join(palabras[corte:])


def crear_ass(tiempos, gancho, duracion, ruta):
    lineas = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Sub,{FUENTE_NOMBRE},100,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,0,0,0,0,100,100,1,0,1,8,4,5,70,70,0,1",
        f"Style: Gancho,{FUENTE_NOMBRE},84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,0,0,0,0,100,100,1,0,1,8,3,8,60,60,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 1,{_t(0)},{_t(duracion)},Gancho,,0,0,0,,{{\\pos(540,250)}}{_gancho_en_lineas(gancho)}",
    ]
    trozos = _trozos(tiempos)
    for n, trozo in enumerate(trozos):
        siguiente = trozos[n + 1][0][1] if n + 1 < len(trozos) else None
        fin_trozo = siguiente if siguiente is not None and siguiente - trozo[-1][2] < 0.4 else trozo[-1][2] + 0.15
        palabras = [_limpio(w) for w, _, _ in trozo]
        for i, (_, ini, fin) in enumerate(trozo):
            desde = trozo[0][1] if i == 0 else ini
            hasta = trozo[i + 1][1] if i + 1 < len(trozo) else fin_trozo
            texto = " ".join(("{\\c&H00D7FF&}" + w + "{\\c&HFFFFFF&}") if j == i else w for j, w in enumerate(palabras))
            salto = "{\\fscx84\\fscy84\\t(0,90,\\fscx100\\fscy100)}" if i == 0 else ""
            lineas.append(f"Dialogue: 0,{_t(desde)},{_t(hasta)},Sub,,0,0,0,,{{\\pos(540,1190)}}{salto}{texto}")
    Path(ruta).write_text("\n".join(lineas) + "\n", encoding="utf-8")


# ------------------------------------------------------------- montaje

def montar(fondo, audio, ass, salida, duracion, encoder, progreso=None):
    """Junta animación + voz + subtítulos. Rutas relativas a BASE (el filtro ass no quiere «C:»)."""
    rel = lambda p: Path(p).resolve().relative_to(BASE).as_posix()  # noqa: E731
    grafo = (f"[0:v]ass={rel(ass)}:fontsdir={rel(FUENTES)}[v];"
             f"[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,apad[a]")

    def ejecutar(enc):
        limite = ["-maxrate", "10M", "-bufsize", "20M"]  # ~10 Mbps: lo que recomienda YouTube para 1080p
        codec = (["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "8M", *limite]
                 if enc == "h264_nvenc" else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", *limite])
        p = subprocess.Popen(
            [editor.FFMPEG, "-hide_banner", "-y", "-v", "error", "-i", rel(fondo), "-i", rel(audio),
             "-filter_complex", grafo, "-map", "[v]", "-map", "[a]", *codec, "-profile:v", "high",
             "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-t", f"{duracion:.2f}", "-movflags", "+faststart",
             "-progress", "pipe:1", "-nostats", rel(salida)],
            cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=editor.SIN_VENTANA)
        for linea in p.stdout:
            if progreso and linea.startswith(b"out_time_us="):
                v = linea.split(b"=", 1)[1].strip()
                if v.isdigit():
                    progreso(min(99.0, int(v) / 1e6 / duracion * 100))
        return p.wait(), p.stderr.read().decode("utf-8", "replace")

    codigo, error = ejecutar(encoder)
    if codigo != 0 and encoder != "libx264":
        codigo, error = ejecutar("libx264")
    if codigo != 0:
        raise RuntimeError(f"ffmpeg falló al montar: {error.strip()[-400:]}")


# ------------------------------------------------------------- producción

def identificar(nombre_guion, g):
    """Id del Short, semilla (el mismo guion da siempre el mismo mundo) y escena de la animación."""
    import numpy as np
    sid = "g-" + re.sub(r"[^a-z0-9-]", "", Path(nombre_guion).stem.lower())[:40]
    semilla = int(hashlib.sha1(sid.encode()).hexdigest()[:8], 16)
    return sid, semilla, animacion.elegir_escena(np.random.default_rng(semilla), g.get("escena"))


def metadatos(g, sid, duracion, escena, motor, credito):
    descripcion = g["descripcion"]
    if g["fuentes"]:
        descripcion += "\n\nFuentes: " + " · ".join(g["fuentes"][:3])
    if credito:
        descripcion += "\n" + credito
    titulo = g["titulo"].strip()[:100]
    if "#shorts" not in titulo.lower() and len(titulo) <= 91:
        titulo += " #shorts"
    return {
        "id": sid, "titulo": titulo, "texto_en_pantalla": g["gancho"], "descripcion": descripcion,
        "etiquetas": [e[:30] for e in g["etiquetas"]][:15], "duracion": round(duracion, 1),
        "escena": escena, "fuentes": g["fuentes"], "voz": motor,
    }


def producir(ruta, encoder, cfg):
    """Hace el Short del guion (en tu PC). Devuelve los datos para la cola de subida."""
    g = leer(ruta)
    sid, semilla, escena = identificar(Path(ruta).name, g)

    estado.agente("guionista", f"Guion recibido: «{g['titulo']}»")
    estado.agente("narrador", f"Poniendo voz a «{g['gancho']}»")
    estado.fase("editando", f"Grabando la voz de «{g['titulo']}»", 2)
    audio = TMP / f"{sid}.wav"
    tiempos, dur_voz, motor, credito = voz.narrar(g["narracion"], audio, cfg, avisar=lambda m: estado.log(m, "aviso"))
    estado.agente("narrador", f"Voz lista ({motor}, {dur_voz:.0f} s)")
    duracion = dur_voz + 0.7

    estado.agente("animador", f"Animando un {escena['modo']} en {escena['bioma']} ({escena['hora']})")
    fondo = TMP / f"{sid}-fondo.mp4"
    animacion.renderizar(duracion, fondo, escena, semilla, encoder,
                         progreso=lambda p: estado.bot(progreso=round(5 + p * 0.8),
                                                       detalle=f"Animando el mundo de bloques ({p:.0f}%)"))

    estado.agente("montador", f"Subtítulos y montaje de «{g['gancho']}»")
    estado.fase("editando", f"Montando «{g['titulo']}»", 86)
    ass = TMP / f"{sid}.ass"
    crear_ass(tiempos, g["gancho"], duracion, ass)
    salida = SHORTS / f"{sid}.mp4"
    montar(fondo, audio, ass, salida, duracion, encoder, progreso=lambda p: estado.bot(progreso=round(86 + p * 0.13)))
    mini = MINIS / f"{sid}.jpg"
    editor.fotograma(salida, min(2.0, duracion / 2), mini, ancho=360)
    for f in (audio, fondo, ass):
        f.unlink(missing_ok=True)
    return {**metadatos(g, sid, duracion, escena, motor, credito), "archivo": str(salida), "miniatura": str(mini)}


def archivar(ruta, ok, error=None):
    destino = (HECHOS if ok else ERRORES) / Path(ruta).name
    shutil.move(str(ruta), destino)
    if error:
        destino.with_suffix(".error.txt").write_text(str(error), encoding="utf-8")
