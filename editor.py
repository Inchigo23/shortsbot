"""Edición de vídeo: elegir el mejor momento y convertirlo en un Short vertical 1080x1920."""
import re
import subprocess
import sys
import textwrap
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SIN_VENTANA = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
ANCHO, ALTO = 1080, 1920


def _ffmpeg(args, **kw):
    return subprocess.run([FFMPEG, "-hide_banner", *args], capture_output=True, creationflags=SIN_VENTANA, **kw)


@dataclass
class InfoVideo:
    duracion: float
    ancho: int
    alto: int
    fps: float
    pistas_audio: int


def info(ruta) -> InfoVideo:
    txt = _ffmpeg(["-i", str(ruta)]).stderr.decode("utf-8", "replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", txt)
    if not m:
        raise ValueError("No se puede leer el vídeo (¿está dañado o a medio guardar?)")
    duracion = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    video = re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", txt)
    if not video:
        raise ValueError("El archivo no tiene imagen")
    fps = re.search(r"(\d+(?:\.\d+)?) fps", txt)
    return InfoVideo(
        duracion=duracion,
        ancho=int(video[1]),
        alto=int(video[2]),
        fps=float(fps[1]) if fps else 30.0,
        pistas_audio=len(re.findall(r"Stream #\S+.*?: Audio:", txt)),
    )


def volumen(ruta, paso=0.5):
    """Volumen (dB) de cada trozo de `paso` segundos. None si no hay audio."""
    r = _ffmpeg(["-v", "error", "-i", str(ruta), "-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"])
    muestras = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)
    n = int(8000 * paso)
    trozos = len(muestras) // n
    if trozos == 0:
        return None
    rms = np.sqrt((muestras[: trozos * n].reshape(trozos, n) ** 2).mean(axis=1)) + 1e-3
    return 20 * np.log10(rms / 32768)


def elegir_momentos(ruta, inf: InfoVideo, duracion_short, max_por_video):
    """Devuelve [(inicio, fin), ...] con los momentos más intensos del vídeo.

    El "clímax" (el pico de volumen: explosiones, gritos, golpes...) se coloca al 75% del
    Short, así se ve lo que pasa antes y el vídeo acaba justo después, que engancha más.
    """
    minimo, maximo = duracion_short
    dur = inf.duracion
    if dur < 6:
        return []
    if dur <= maximo + 3:
        return [(0.0, dur)]

    paso = 0.5
    db = volumen(ruta, paso) if inf.pistas_audio else None
    if db is None or db.max() < -55:
        # Sin sonido: las repeticiones de NVIDIA se guardan justo después de la jugada.
        return [(dur - maximo, dur)]

    suave = np.convolve(db, np.ones(4) / 4, mode="same")
    t = np.arange(len(suave)) * paso + paso / 2
    puntuacion = suave.copy()
    if dur <= 600:
        puntuacion += 6.0 * (t / dur)  # en clips cortos, lo bueno suele estar al final
    cuantos = 1 if dur < 240 else max(1, min(max_por_video, int(dur // 120)))

    elegidos = []
    for i in np.argsort(puntuacion)[::-1]:
        ini = t[i] - 0.75 * maximo
        ini = min(max(ini, 0.0), dur - maximo)
        fin = ini + maximo
        if all(fin + 5 <= a or ini >= b + 5 for a, b in elegidos):
            elegidos.append((float(ini), float(fin)))
            if len(elegidos) >= cuantos:
                break
    return sorted(elegidos)


def fotograma(ruta, segundo, salida, ancho=768):
    _ffmpeg(["-y", "-v", "error", "-ss", f"{segundo:.2f}", "-i", str(ruta),
             "-frames:v", "1", "-vf", f"scale={ancho}:-2", "-q:v", "4", str(salida)])
    return Path(salida).exists()


def detectar_encoder():
    """Usa la gráfica NVIDIA para codificar si se puede (mucho más rápido)."""
    r = _ffmpeg(["-v", "error", "-f", "lavfi", "-i", "color=black:s=320x240:d=0.2",
                 "-c:v", "h264_nvenc", "-f", "null", "-"])
    return "h264_nvenc" if r.returncode == 0 else "libx264"


# ---------- Texto encima del vídeo ----------

FUENTES = [r"C:\Windows\Fonts\seguibl.ttf", r"C:\Windows\Fonts\ariblk.ttf", r"C:\Windows\Fonts\arialbd.ttf"]


def _sin_emojis(texto):
    return "".join(
        c for c in texto
        if unicodedata.category(c) not in ("So", "Cs", "Mn") and ord(c) <= 0xFFFF and c not in "\u200d\ufe0f"
    ).strip()


def _fuente(tam):
    for f in FUENTES:
        if Path(f).exists():
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default(tam)


def crear_rotulo(texto, salida):
    """PNG transparente 1080x1920 con el texto arriba, estilo Shorts (blanco con borde negro)."""
    img = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    texto = _sin_emojis(texto).upper()
    if texto:
        d = ImageDraw.Draw(img)
        for tam in range(96, 50, -4):
            fuente = _fuente(tam)
            por_linea = max(8, int(ANCHO * 0.88 / (tam * 0.62)))
            lineas = textwrap.wrap(texto, por_linea)[:3]
            if all(d.textlength(l, font=fuente) <= ANCHO * 0.9 for l in lineas):
                break
        alto_linea = int(tam * 1.15)
        centro = 400  # entre la barra de arriba de YouTube y el vídeo
        y = centro - alto_linea * len(lineas) // 2
        for i, linea in enumerate(lineas):
            color = (255, 214, 0) if i == 0 and len(lineas) > 1 else (255, 255, 255)
            d.text((ANCHO // 2, y), linea, font=fuente, fill=color, anchor="mt",
                   stroke_width=max(6, tam // 10), stroke_fill=(0, 0, 0))
            y += alto_linea
    img.save(salida)


# ---------- Render final ----------

def renderizar(ruta, ini, fin, rotulo_png, salida, inf: InfoVideo, encoder, progreso=None):
    d = fin - ini
    fps = min(round(inf.fps), 60) or 30
    grafo = (
        "[0:v]split=2[a][b];"
        # Fondo: el propio vídeo ampliado y desenfocado
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "scale=270:480,boxblur=6:2,scale=1080:1920,eq=brightness=-0.10:saturation=1.15[fondo];"
        # Juego: recortado a 4:3 para que se vea más grande en vertical
        "[b]crop=w='trunc(min(iw,ih*4/3)/2)*2':h=ih,scale=1080:-2[juego];"
        "[fondo][juego]overlay=x=(W-w)/2:y=(H-h)/2[base];"
        f"[base][1:v]overlay=0:0,fps={fps},format=yuv420p[v]"
    )
    mapas = ["-map", "[v]"]
    if inf.pistas_audio:
        efectos = (f"afade=t=in:d=0.2,afade=t=out:st={max(0.0, d - 0.6):.2f}:d=0.6,"
                   "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000")
        if inf.pistas_audio > 1:  # juego + micro en pistas separadas: se mezclan
            entradas = "".join(f"[0:a:{i}]" for i in range(inf.pistas_audio))
            grafo += f";{entradas}amix=inputs={inf.pistas_audio}:normalize=0,{efectos}[au]"
        else:
            grafo += f";[0:a:0]{efectos}[au]"
        mapas += ["-map", "[au]", "-c:a", "aac", "-b:a", "192k"]

    def ejecutar(enc):
        if enc == "h264_nvenc":
            codec = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0",
                     "-maxrate", "16M", "-bufsize", "32M"]
        else:
            codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
        args = [FFMPEG, "-hide_banner", "-y", "-v", "error",
                "-ss", f"{ini:.2f}", "-t", f"{d:.2f}", "-i", str(ruta), "-i", str(rotulo_png),
                "-filter_complex", grafo, *mapas, *codec, "-profile:v", "high",
                "-t", f"{d:.2f}", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(salida)]
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=SIN_VENTANA)
        for linea in p.stdout:
            if progreso and linea.startswith(b"out_time_us="):
                valor = linea.split(b"=", 1)[1].strip()
                if valor.isdigit():
                    progreso(min(99.0, int(valor) / 1e6 / d * 100))
        error = p.stderr.read().decode("utf-8", "replace")
        return p.wait(), error

    codigo, error = ejecutar(encoder)
    if codigo != 0 and encoder != "libx264":
        codigo, error = ejecutar("libx264")
    if codigo != 0:
        raise RuntimeError(f"ffmpeg falló: {error.strip()[-400:]}")
