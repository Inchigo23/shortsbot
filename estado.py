"""Estado compartido entre el bot y el panel (se guarda en datos/estado.json)."""
import copy
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATOS = BASE / "datos"
DATOS.mkdir(exist_ok=True)
ARCHIVO = DATOS / "estado.json"

logging.basicConfig(
    filename=DATOS / "bot.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
log_archivo = logging.getLogger("shortsbot")
logging.getLogger("werkzeug").setLevel(logging.WARNING)  # sin una línea por cada refresco del panel

_lock = threading.RLock()
_estado: dict = {}


def _vacio():
    return {
        "fuentes": {},  # vídeos originales ya vistos
        "shorts": {},   # shorts generados a partir de ellos
        "log": [],
        "rutinas": {"informe": None, "telemetria": 0},
        "bot": {
            "fase": "arrancando",
            "detalle": "",
            "progreso": None,
            "latido": time.time(),
            "pausado": False,
            "youtube": None,  # nombre del canal si está conectado
            "titulos": "plantilla",
            "encoder": None,
            "agente": None,   # agente que está trabajando ahora mismo
            "agentes": {},    # última actividad de cada agente
        },
    }


def cargar():
    global _estado
    with _lock:
        _estado = _vacio()
        if ARCHIVO.exists():
            try:
                guardado = json.loads(ARCHIVO.read_text(encoding="utf-8"))
                for clave, valor in guardado.items():
                    if clave == "bot":
                        _estado["bot"].update(pausado=valor.get("pausado", False),
                                              agentes=valor.get("agentes", {}))
                    else:
                        _estado[clave] = valor
            except Exception:
                ARCHIVO.replace(ARCHIVO.with_suffix(f".roto-{int(time.time())}.json"))
        # Si el bot se apagó a medias, dejamos las cosas en un estado reintentable.
        for f in _estado["fuentes"].values():
            if f["estado"] == "procesando":
                f["estado"] = "pendiente"
        for s in _estado["shorts"].values():
            if s["estado"] == "subiendo":
                s["estado"] = "listo"
            s["progreso"] = None
        guardar()


def guardar():
    with _lock:
        tmp = ARCHIVO.with_suffix(".tmp")
        tmp.write_text(json.dumps(_estado, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, ARCHIVO)


@contextmanager
def editar():
    """with estado.editar() as e: ...  -> modifica y guarda en disco."""
    with _lock:
        yield _estado
        guardar()


def foto():
    """Copia del estado para leer sin bloquear."""
    with _lock:
        return copy.deepcopy(_estado)


def leer(funcion):
    """Lee algo concreto del estado sin copiarlo entero: estado.leer(lambda e: e["bot"]["pausado"])."""
    with _lock:
        return copy.deepcopy(funcion(_estado))


def bot(**campos):
    """Actualiza el estado en vivo del bot (no se guarda en disco)."""
    with _lock:
        _estado["bot"].update(campos)
        _estado["bot"]["latido"] = time.time()


def fase(fase, detalle="", progreso=None):
    bot(fase=fase, detalle=detalle, progreso=progreso)


def agente(nombre, nota=""):
    """Marca qué agente del centro de control está trabajando (None = ninguno)."""
    with _lock:
        b = _estado["bot"]
        b["agente"] = nombre
        if nombre:
            b["agentes"].setdefault(nombre, {}).update(ultimo=time.time(), nota=nota)
        b["latido"] = time.time()


def log(mensaje, nivel="info"):
    getattr(log_archivo, "error" if nivel == "error" else "warning" if nivel == "aviso" else "info")(mensaje)
    with _lock:
        _estado["log"].append({"t": time.time(), "nivel": nivel, "msg": mensaje})
        del _estado["log"][:-200]
        guardar()
