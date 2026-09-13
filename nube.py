"""ShortsBot en la nube (GitHub Actions): hace, sube y mide los Shorts sin que tu PC esté encendido.

Lo ejecuta .github/workflows/shortsbot.yml cada 2 horas, paso a paso:
  python nube.py plan          🗓️ Planificador: decide qué toca en esta vuelta
  python nube.py guion         ✍️ Guionista:    lee el siguiente guion que escribió Claude
  python nube.py voz           🎙️ Narrador:     le pone voz
  python nube.py animar        🧱 Animador:     genera el mundo de bloques
  python nube.py montar        🎬 Montador:     subtítulos + montaje, y lo deja en "preparados"
  python nube.py subir         🚀 Mensajero:    sube a YouTube el que toca
  python nube.py estadisticas  📊 Estadista:    estadísticas del canal

Datos: nube/estado.json (lo escribe este programa), nube/control.json (lo escribe la app) y
nube/config.json. Los vídeos preparados se guardan en la release «preparados» del repositorio y se
borran solos al subirse. Los guiones llegan a nube/guiones/ en la rama claude/guiones (los escribe una
rutina de Claude en la nube cada día).
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
NUBE = BASE / "nube"
TRABAJO = BASE / "trabajo"
ESTADO, CONTROL, CONFIG = NUBE / "estado.json", NUBE / "control.json", NUBE / "config.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "Inchigo23/shortsbot")
RAMA_GUIONES = "claude/guiones"
CARPETA_GUIONES = "nube/guiones"   # dentro de la rama claude/guiones
ETIQUETA = "preparados"

CONFIG_DEFECTO = {
    "zona": "Europe/Madrid",
    "horas_subida": [12, 16],      # a partir de estas horas sube uno (como mucho uno por franja)
    "max_por_dia": 2,
    "preparados_max": 3,           # vídeos hechos por adelantado esperando su hora
    "privacidad": "private",       # "public" cuando Google verifique tu app
    "horas_estadisticas": 6,
    "voz": "kokoro", "voz_kokoro": "em_alex",
    "voz_piper": "es_ES-davefx-medium", "voz_piper_hablante": None,
}
ESTADO_VACIO = {
    "preparados": [], "subidos": [], "descartados": [], "guiones_usados": [], "canal": {}, "videos_canal": [],
    "historial": [], "parrilla": [], "log": [], "ultimo_ciclo": 0, "ultima_estadistica": 0, "youtube_ok": None,
}


# ------------------------------------------------------------------ utilidades

def leer_json(ruta, defecto):
    try:
        return {**defecto, **json.loads(Path(ruta).read_text(encoding="utf-8"))}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(defecto)


def escribir_json(ruta, datos):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def cargar():
    return leer_json(ESTADO, ESTADO_VACIO), leer_json(CONTROL, {"pausado": False, "descartar": []}), \
        leer_json(CONFIG, CONFIG_DEFECTO)


def log(e, mensaje, nivel="info"):
    print(("⚠️ " if nivel != "info" else "") + mensaje, flush=True)
    e["log"].append({"t": time.time(), "nivel": nivel, "msg": mensaje})
    del e["log"][:-200]


def salida_paso(**valores):
    """Pasa valores al resto del workflow (steps.plan.outputs.*)."""
    lineas = "".join(f"{k}={v}\n" for k, v in valores.items())
    destino = os.environ.get("GITHUB_OUTPUT")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(lineas)
    else:
        print(lineas, end="")


def trabajo(nombre):
    TRABAJO.mkdir(exist_ok=True)
    return TRABAJO / nombre


# ------------------------------------------------------------------ GitHub (release «preparados»)

def _gh(metodo, ruta=None, datos=None, url=None, bruto=None, tipo=None):
    cuerpo = bruto if bruto is not None else (json.dumps(datos).encode() if datos is not None else None)
    req = urllib.request.Request(url or f"https://api.github.com{ruta}", data=cuerpo, method=metodo)
    req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if tipo:
        req.add_header("Content-Type", tipo)
    with urllib.request.urlopen(req, timeout=600) as r:
        contenido = r.read()
        return json.loads(contenido) if contenido else None


def _release():
    try:
        return _gh("GET", f"/repos/{REPO}/releases/tags/{ETIQUETA}")
    except urllib.error.HTTPError as ex:
        if ex.code != 404:
            raise
        return _gh("POST", f"/repos/{REPO}/releases", {
            "tag_name": ETIQUETA, "name": "Vídeos preparados", "prerelease": True,
            "body": "Shorts hechos por ShortsBot esperando su hora de subida. Se borran solos al subirse a YouTube.",
        })


def _subir_archivo(ruta, nombre, tipo):
    rel = _release()
    url = f"https://uploads.github.com/repos/{REPO}/releases/{rel['id']}/assets?name={nombre}"
    return _gh("POST", url=url, bruto=Path(ruta).read_bytes(), tipo=tipo)["id"]


def _borrar_archivo(asset_id):
    if not asset_id:
        return
    try:
        _gh("DELETE", f"/repos/{REPO}/releases/assets/{asset_id}")
    except urllib.error.HTTPError as ex:
        if ex.code != 404:
            raise


def _bajar_archivo(asset_id, destino):
    class SinRedireccion(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None  # la descarga real está en otra web y no debe recibir nuestra clave

    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/assets/{asset_id}")
    req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    req.add_header("Accept", "application/octet-stream")
    try:
        datos = urllib.request.build_opener(SinRedireccion).open(req, timeout=600).read()
    except urllib.error.HTTPError as ex:
        if ex.code not in (301, 302, 303, 307, 308):
            raise
        datos = urllib.request.urlopen(ex.headers["Location"], timeout=600).read()
    Path(destino).write_bytes(datos)


# ------------------------------------------------------------------ previas (rama «previas», siempre 1 commit)

RAMA_PREVIAS = "previas"


def _actualizar_previas(e, nuevas=None):
    """Deja en la rama «previas» solo la versión ligera de cada vídeo preparado, para verla en la app.

    La rama se reescribe entera (un único commit sin historial), así no crece con el tiempo.
    `nuevas`: {nombre_archivo: ruta_local} de previas recién hechas.
    """
    nuevas = nuevas or {}
    try:
        arbol = {x["path"]: x["sha"] for x in _gh("GET", f"/repos/{REPO}/git/trees/{RAMA_PREVIAS}")["tree"]}
        existe = True
    except urllib.error.HTTPError as ex:
        if ex.code not in (404, 409):
            raise
        arbol, existe = {}, False
    entradas = []
    for p in e["preparados"]:
        nombre = f"{p['id']}-previa.mp4"
        if nombre in nuevas:
            contenido = Path(nuevas[nombre]).read_bytes()
        elif nombre in arbol:
            entradas.append({"path": nombre, "mode": "100644", "type": "blob", "sha": arbol[nombre]})
            continue
        elif p.get("asset_previa"):  # vídeos preparados antes de existir la rama
            _bajar_archivo(p["asset_previa"], trabajo(nombre))
            contenido = trabajo(nombre).read_bytes()
        else:
            continue
        blob = _gh("POST", f"/repos/{REPO}/git/blobs",
                   {"content": base64.b64encode(contenido).decode(), "encoding": "base64"})
        entradas.append({"path": nombre, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    if not entradas:
        blob = _gh("POST", f"/repos/{REPO}/git/blobs", {"content": "Sin vídeos preparados.\n", "encoding": "utf-8"})
        entradas.append({"path": "LEEME.txt", "mode": "100644", "type": "blob", "sha": blob["sha"]})
    arbol_nuevo = _gh("POST", f"/repos/{REPO}/git/trees", {"tree": entradas})
    commit = _gh("POST", f"/repos/{REPO}/git/commits",
                 {"message": "Previas de los vídeos preparados", "tree": arbol_nuevo["sha"], "parents": []})
    if existe:
        _gh("PATCH", f"/repos/{REPO}/git/refs/heads/{RAMA_PREVIAS}", {"sha": commit["sha"], "force": True})
    else:
        _gh("POST", f"/repos/{REPO}/git/refs", {"ref": f"refs/heads/{RAMA_PREVIAS}", "sha": commit["sha"]})
    for p in e["preparados"]:  # la copia ligera ya no hace falta en la release
        if p.get("asset_previa"):
            _borrar_archivo(p.pop("asset_previa"))


# ------------------------------------------------------------------ guiones (rama claude/guiones)

def guiones_pendientes(e):
    subprocess.run(["git", "fetch", "-q", "--depth=1", "origin",
                    f"+refs/heads/{RAMA_GUIONES}:refs/remotes/origin/{RAMA_GUIONES}"], capture_output=True)
    r = subprocess.run(["git", "ls-tree", "--name-only", f"origin/{RAMA_GUIONES}", f"{CARPETA_GUIONES}/"],
                       capture_output=True, text=True)
    if r.returncode:
        return []
    nombres = sorted(Path(n).name for n in r.stdout.split() if n.endswith(".json"))
    return [n for n in nombres if n not in e["guiones_usados"]]


def leer_guion(nombre):
    r = subprocess.run(["git", "show", f"origin/{RAMA_GUIONES}:{CARPETA_GUIONES}/{nombre}"],
                       capture_output=True, check=True)
    return json.loads(r.stdout.decode("utf-8"))


# ------------------------------------------------------------------ horario

def _ahora(cfg):
    return datetime.now(ZoneInfo(cfg["zona"]))


def _subidos_el(e, cfg, dia):
    z = ZoneInfo(cfg["zona"])
    return sum(datetime.fromtimestamp(s["subido_en"], z).date() == dia for s in e["subidos"])


def toca_subir(e, cfg):
    ahora = _ahora(cfg)
    franjas_pasadas = sum(ahora.hour >= h for h in cfg["horas_subida"])
    return _subidos_el(e, cfg, ahora.date()) < min(franjas_pasadas, cfg["max_por_dia"])


def calcular_parrilla(e, cfg):
    """Hora aproximada a la que saldrá cada vídeo preparado (el workflow pasa cada 2 horas)."""
    ahora = _ahora(cfg)
    huecos, dia = [], ahora.date()
    usados_hoy = _subidos_el(e, cfg, dia)
    while len(huecos) < len(e["preparados"]):
        franjas = sorted(cfg["horas_subida"])[:cfg["max_por_dia"]]
        for i, h in enumerate(franjas):
            if dia == ahora.date() and i < usados_hoy:
                continue
            momento = datetime.combine(dia, datetime.min.time(), ZoneInfo(cfg["zona"])) + timedelta(hours=h)
            huecos.append(max(momento, ahora).timestamp())
        dia += timedelta(days=1)
    return [{"id": p["id"], "cuando": t} for p, t in zip(e["preparados"], huecos)]


# ------------------------------------------------------------------ pasos

def plan():
    e, ctrl, cfg = cargar()
    accion = (os.environ.get("ACCION") or "ciclo").strip()

    # Vídeos que has descartado desde la app
    cambios_previas = False
    for pid in ctrl.get("descartar", []):
        p = next((x for x in e["preparados"] if x["id"] == pid), None)
        if p:
            _borrar_archivo(p.get("asset"))
            _borrar_archivo(p.get("asset_previa"))
            e["preparados"].remove(p)
            e["descartados"].insert(0, {k: v for k, v in p.items() if k not in ("asset", "asset_previa")}
                                    | {"descartado_en": time.time()})
            del e["descartados"][30:]
            log(e, f"Descartado desde la app: «{p['titulo']}»")
            cambios_previas = True
    if cambios_previas or any(p.get("asset_previa") for p in e["preparados"]):
        _actualizar_previas(e)

    pausado = bool(ctrl.get("pausado"))
    pendientes = guiones_pendientes(e)
    producir = bool(pendientes) and (accion == "producir" or (accion == "ciclo" and not pausado
                                                              and len(e["preparados"]) < cfg["preparados_max"]))
    subir = ""
    if accion.startswith("subir:"):
        pid = accion.split(":", 1)[1]
        subir = pid if any(p["id"] == pid for p in e["preparados"]) else ""
    elif accion == "subir_siguiente" and e["preparados"]:
        subir = e["preparados"][0]["id"]
    elif accion == "ciclo" and not pausado and e["preparados"] and toca_subir(e, cfg):
        subir = e["preparados"][0]["id"]
    estadisticas = accion == "estadisticas" or bool(subir) or \
        time.time() - e["ultima_estadistica"] > cfg["horas_estadisticas"] * 3600
    if os.environ.get("TIENE_YOUTUBE", "true") != "true":
        if subir or accion == "estadisticas":
            log(e, "Falta el secreto YOUTUBE_TOKEN en GitHub: no puedo subir ni leer estadísticas.", "aviso")
        subir, estadisticas = "", False
        e["youtube_ok"] = False

    e["ultimo_ciclo"] = time.time()
    e["pausado"] = pausado
    e["guiones_en_espera"] = len(pendientes)
    e["parrilla"] = calcular_parrilla(e, cfg)
    if pausado and accion == "ciclo":
        print("En pausa desde la app: esta vuelta no hace nada.")
    escribir_json(ESTADO, e)
    salida_paso(producir=str(producir).lower(), guion=pendientes[0] if producir else "", subir=subir,
                estadisticas=str(estadisticas).lower())
    print(f"Plan: producir={producir} ({len(pendientes)} guiones en espera) · subir={subir or 'no'} · "
          f"estadísticas={estadisticas} · preparados={len(e['preparados'])}")


def paso_guion():
    import estudio
    nombre = os.environ["GUION"]
    g = estudio.validar(leer_guion(nombre))
    escribir_json(trabajo("guion.json"), {"nombre": nombre, "guion": g})
    print(f"Guion: «{g['titulo']}» ({sum(len(f.split()) for f in g['narracion'])} palabras)")


def paso_voz():
    import estado
    import voz
    estado._estado = estado._vacio()  # los avisos del estudio solo van a la consola
    e, _, cfg = cargar()
    g = json.loads(trabajo("guion.json").read_text(encoding="utf-8"))["guion"]
    tiempos, dur, motor, credito = voz.narrar(g["narracion"], trabajo("voz.wav"), cfg, avisar=print)
    escribir_json(trabajo("voz.json"), {"tiempos": tiempos, "duracion": dur, "motor": motor, "credito": credito})
    print(f"Voz lista: {motor}, {dur:.1f} s")


def paso_animar():
    import animacion
    import estudio
    datos = json.loads(trabajo("guion.json").read_text(encoding="utf-8"))
    v = json.loads(trabajo("voz.json").read_text(encoding="utf-8"))
    sid, semilla, escena = estudio.identificar(datos["nombre"], datos["guion"])
    marcas = set()

    def progreso(p):
        decena = int(p // 10) * 10
        if decena not in marcas:
            marcas.add(decena)
            print(f"  animando… {decena}%", flush=True)
    inicio = time.time()
    animacion.renderizar(v["duracion"] + 0.7, trabajo("fondo.mp4"), escena, semilla, "libx264", progreso)
    escribir_json(trabajo("animacion.json"), {"id": sid, "escena": escena})
    print(f"Animación lista: {escena} en {time.time() - inicio:.0f} s")


def paso_montar():
    import editor
    import estudio
    e, _, cfg = cargar()
    datos = json.loads(trabajo("guion.json").read_text(encoding="utf-8"))
    g, nombre = datos["guion"], datos["nombre"]
    v = json.loads(trabajo("voz.json").read_text(encoding="utf-8"))
    a = json.loads(trabajo("animacion.json").read_text(encoding="utf-8"))
    duracion = v["duracion"] + 0.7
    estudio.crear_ass(v["tiempos"], g["gancho"], duracion, trabajo("subtitulos.ass"))
    short, previa, mini = trabajo(f"{a['id']}.mp4"), trabajo(f"{a['id']}-previa.mp4"), trabajo("mini.jpg")
    estudio.montar(trabajo("fondo.mp4"), trabajo("voz.wav"), trabajo("subtitulos.ass"), short, duracion, "libx264")
    # Versión ligera para verla en la app sin gastar datos
    subprocess.run([editor.FFMPEG, "-hide_banner", "-y", "-v", "error", "-i", str(short), "-vf", "scale=540:-2",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k",
                    "-movflags", "+faststart", str(previa)], check=True)
    editor.fotograma(short, min(2.0, duracion / 2), mini, ancho=270)

    info = estudio.metadatos(g, a["id"], duracion, a["escena"], v["motor"], v["credito"])
    e["preparados"] = [p for p in e["preparados"] if p["id"] != a["id"]]
    e["preparados"].append(info | {
        "guion": nombre, "creado": time.time(), "tam_mb": round(short.stat().st_size / 1e6, 1),
        "asset": _subir_archivo(short, short.name, "video/mp4"),
        "miniatura": "data:image/jpeg;base64," + base64.b64encode(mini.read_bytes()).decode(),
    })
    _actualizar_previas(e, {previa.name: previa})
    if nombre not in e["guiones_usados"]:
        e["guiones_usados"].append(nombre)
    e["parrilla"] = calcular_parrilla(e, cfg)
    log(e, f"Short preparado: «{info['titulo']}» ({a['escena']['modo']}, {a['escena']['bioma']}, "
           f"{a['escena']['hora']}, voz {v['motor']})")
    escribir_json(ESTADO, e)


def paso_subir():
    import youtube
    e, _, cfg = cargar()
    pid = os.environ["SUBIR"]
    p = next(x for x in e["preparados"] if x["id"] == pid)
    archivo = trabajo(f"{pid}.mp4")
    _bajar_archivo(p["asset"], archivo)
    try:
        vid, privacidad = youtube.subir(archivo, p["titulo"], p["descripcion"], p["etiquetas"], cfg["privacidad"])
    except youtube.NecesitaConectar as ex:
        e["youtube_ok"] = False
        log(e, f"{ex}. Hay que renovar el secreto YOUTUBE_TOKEN (mira LEEME.md).", "error")
        escribir_json(ESTADO, e)
        sys.exit(1)
    except youtube.SinCuota as ex:
        log(e, str(ex), "aviso")
        escribir_json(ESTADO, e)
        return
    _borrar_archivo(p.get("asset"))
    _borrar_archivo(p.get("asset_previa"))
    e["preparados"].remove(p)
    _actualizar_previas(e)
    e["subidos"].insert(0, {k: v for k, v in p.items() if k not in ("asset", "asset_previa", "descripcion")}
                        | {"youtube_id": vid, "privacidad": privacidad, "subido_en": time.time()})
    del e["subidos"][100:]
    e["youtube_ok"] = True
    e["parrilla"] = calcular_parrilla(e, cfg)
    log(e, f"Subido a YouTube ({privacidad}): «{p['titulo']}»")
    escribir_json(ESTADO, e)


def paso_estadisticas():
    import youtube
    e, _, cfg = cargar()
    try:
        canal, videos = youtube.estadisticas_canal()
    except youtube.NecesitaConectar as ex:
        e["youtube_ok"] = False
        log(e, f"{ex}. Hay que renovar el secreto YOUTUBE_TOKEN (mira LEEME.md).", "error")
        escribir_json(ESTADO, e)
        sys.exit(1)
    e["canal"] = canal | {"actualizado": time.time()}
    e["videos_canal"] = videos
    por_id = {v["id"]: v for v in videos}
    for s in e["subidos"]:
        if s.get("youtube_id") in por_id:
            v = por_id[s["youtube_id"]]
            s.update(vistas=v["vistas"], likes=v["likes"], comentarios=v["comentarios"], privacidad=v["privacidad"])
    hoy = _ahora(cfg).date().isoformat()
    punto = {"fecha": hoy, "suscriptores": canal["suscriptores"], "vistas": canal["vistas"], "videos": canal["videos"]}
    if e["historial"] and e["historial"][-1]["fecha"] == hoy:
        e["historial"][-1] = punto
    else:
        e["historial"].append(punto)
    del e["historial"][:-400]
    e["ultima_estadistica"] = time.time()
    e["youtube_ok"] = True
    print(f"Canal «{canal['titulo']}»: {canal['suscriptores']} suscriptores, {canal['vistas']} visitas, "
          f"{canal['videos']} vídeos")
    escribir_json(ESTADO, e)


PASOS = {"plan": plan, "guion": paso_guion, "voz": paso_voz, "animar": paso_animar, "montar": paso_montar,
         "subir": paso_subir, "estadisticas": paso_estadisticas}

if __name__ == "__main__":
    PASOS[sys.argv[1]]()
