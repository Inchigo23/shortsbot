"""Narrador: convierte el guion en voz y calcula cuándo suena cada palabra (para los subtítulos).

Motores (ajuste "voz" en config.json):
  - "piper":  voces locales Piper (modelo en "voz_piper", hablante en "voz_piper_hablante").
  - "kokoro": voces locales Kokoro (voz en "voz_kokoro": em_alex, ef_dora o em_santa).
  - "google": Google Cloud Text-to-Speech (necesita facturación activa y el permiso cloud-platform).
Si el motor elegido falla, se usa Piper para no parar la producción.
"""
import base64
import io
import json
import re
import wave
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
VOCES = BASE / "datos" / "voces"
PAUSA = 0.28  # silencio entre frases (s)
# Licencias que piden mencionar la voz en la descripción del vídeo
CREDITOS = {"es_ES-sharvard-medium": "Voz: Piper «sharvard» (CC BY 3.0, Univ. de Edimburgo)"}
_cache = {}


# ------------------------------------------------------------------ motores

def _motor_piper(modelo="es_ES-davefx-medium", hablante=None):
    from piper import PiperVoice, SynthesisConfig
    ruta = VOCES / f"{modelo}.onnx"
    if not ruta.exists():
        raise FileNotFoundError(f"Falta la voz {ruta.name} en datos/voces")
    if modelo not in _cache:
        _cache[modelo] = PiperVoice.load(str(ruta))
    voz = _cache[modelo]
    if isinstance(hablante, str):  # "M" / "F" según el mapa del modelo
        hablante = json.loads(ruta.with_suffix(".onnx.json").read_text(encoding="utf-8"))["speaker_id_map"][hablante]
    ajustes = SynthesisConfig(speaker_id=hablante, length_scale=0.95, noise_scale=0.667, noise_w_scale=0.8)

    def frase(texto):
        audio = np.concatenate([np.frombuffer(c.audio_int16_bytes, dtype=np.int16) for c in voz.synthesize(texto, ajustes)])
        return audio, voz.config.sample_rate
    return frase


def _motor_kokoro(nombre="em_alex"):
    from kokoro_onnx import Kokoro
    if "kokoro" not in _cache:
        _cache["kokoro"] = Kokoro(str(VOCES / "kokoro-v1.0.int8.onnx"), str(VOCES / "voices-v1.0.bin"))
    k = _cache["kokoro"]

    def frase(texto):
        muestras, tasa = k.create(texto, voice=nombre, speed=1.0, lang="es")
        return (np.clip(muestras, -1, 1) * 32767).astype(np.int16), tasa
    return frase


def _motor_google(nombre_voz):
    import youtube
    servicio = youtube.servicio_voz()

    def frase(texto):
        cuerpo = {
            "input": {"text": texto},
            "voice": {"languageCode": nombre_voz[:5], "name": nombre_voz},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000},
        }
        r = servicio.text().synthesize(body=cuerpo).execute()
        with wave.open(io.BytesIO(base64.b64decode(r["audioContent"]))) as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()
    return frase


# ------------------------------------------------------------------ narración

def _pesos(palabras):
    # Las palabras largas tardan más en decirse; las comas y puntos añaden una pausa corta.
    return np.array([len(re.sub(r"\W", "", p)) + 2 + (2 if p[-1:] in ",.;:?!" else 0) for p in palabras], float)


def _narrar(frases, salida_wav, sintetizar):
    trozos, tiempos, t, tasa = [], [], 0.0, None
    for frase in frases:
        frase = frase.strip()
        if not frase:
            continue
        audio, tasa = sintetizar(frase)
        # Quita el silencio del principio y del final para que el ritmo sea ágil
        voz_on = np.flatnonzero(np.abs(audio) > 600)
        if len(voz_on):
            audio = audio[max(0, voz_on[0] - int(0.03 * tasa)): voz_on[-1] + int(0.06 * tasa)]
        dur = len(audio) / tasa
        palabras = frase.split()
        pesos = _pesos(palabras)
        limites = np.concatenate([[0], np.cumsum(pesos) / pesos.sum()]) * dur
        tiempos += [(p, t + limites[i], t + limites[i + 1]) for i, p in enumerate(palabras)]
        trozos += [audio, np.zeros(int(PAUSA * tasa), dtype=np.int16)]
        t += dur + PAUSA
    with wave.open(str(salida_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tasa)
        w.writeframes(np.concatenate(trozos).tobytes())
    return tiempos, t


def narrar(frases, salida_wav, cfg, avisar=None):
    """Genera salida_wav. Devuelve ([(palabra, inicio, fin), ...], duración, nombre de la voz, crédito o None)."""
    motor = cfg.get("voz", "piper")
    modelo = cfg.get("voz_piper", "es_ES-davefx-medium")
    try:
        if motor == "kokoro":
            nombre = cfg.get("voz_kokoro", "em_alex")
            tiempos, dur = _narrar(frases, salida_wav, _motor_kokoro(nombre))
            return tiempos, dur, f"Kokoro {nombre}", None
        if motor == "google":
            tiempos, dur = _narrar(frases, salida_wav, _motor_google(cfg.get("voz_google", "es-ES-Chirp3-HD-Puck")))
            return tiempos, dur, "Google", None
        tiempos, dur = _narrar(frases, salida_wav, _motor_piper(modelo, cfg.get("voz_piper_hablante")))
        return tiempos, dur, f"Piper {modelo.split('-')[1]}", CREDITOS.get(modelo)
    except Exception as ex:
        if motor == "piper" and modelo == "es_ES-davefx-medium":
            raise
        if avisar:
            avisar(f"Narrador: la voz «{motor}» ha fallado ({str(ex)[:160]}). Uso la voz local de siempre.")
        tiempos, dur = _narrar(frases, salida_wav, _motor_piper())
        return tiempos, dur, "Piper davefx", None
