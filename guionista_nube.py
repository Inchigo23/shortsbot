"""Ayudante de la Sala de guionistas: ver qué guiones hay y mandar guiones nuevos a la nube.

  python guionista_nube.py estado            títulos ya usados/pendientes y cuántos esperan
  python guionista_nube.py subir A.json ...  valida cada guion y lo sube a nube/guiones (rama claude/guiones)
  python guionista_nube.py iconos            lista de ilustraciones disponibles para "visuales"
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

GH = r"C:\Program Files\GitHub CLI\gh.exe"
REPO = "Inchigo23/shortsbot"
RAMA = "claude/guiones"
CARPETA = "nube/guiones"


def _gh(*args, entrada=None):
    r = subprocess.run([GH, "api", *args], capture_output=True, text=True, encoding="utf-8", input=entrada)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r.stdout


def _raw(ruta, ref):
    return _gh(f"repos/{REPO}/contents/{ruta}?ref={ref}", "-H", "Accept: application/vnd.github.raw+json")


def estado():
    usados = set(json.loads(_raw("nube/estado.json", "main")).get("guiones_usados", []))
    try:
        archivos = [f["name"] for f in json.loads(_gh(f"repos/{REPO}/contents/{CARPETA}?ref={RAMA}"))
                    if f["name"].endswith(".json")]
    except RuntimeError:
        archivos = []
    pendientes = [a for a in archivos if a not in usados]
    print(f"Guiones esperando en la nube: {len(pendientes)}")
    print("Temas ya tratados (no repetir):")
    for a in sorted(archivos):
        try:
            g = json.loads(_raw(f"{CARPETA}/{a}", RAMA))
            print(f"  - {g.get('titulo', a)} | gancho: {g.get('gancho', '')}"
                  f"{' (en espera)' if a in pendientes else ''}")
        except (RuntimeError, json.JSONDecodeError):
            print(f"  - {a}")


def subir(rutas):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import estudio
    import ilustraciones
    for ruta in rutas:
        ruta = Path(ruta)
        g = estudio.validar(json.loads(ruta.read_text(encoding="utf-8")))
        malos = [v for v in g.get("visuales", []) if v and v not in ilustraciones.ICONOS]
        if malos:
            raise SystemExit(f"{ruta.name}: estas ilustraciones no existen: {malos}. Usa: python guionista_nube.py iconos")
        if g.get("visuales") and len(g["visuales"]) != len(g["narracion"]):
            raise SystemExit(f"{ruta.name}: «visuales» tiene que tener un elemento por frase de «narracion»")
        contenido = json.dumps(g, ensure_ascii=False, indent=2) + "\n"
        cuerpo = json.dumps({"message": f"Guion: {g['titulo']}", "branch": RAMA,
                             "content": base64.b64encode(contenido.encode("utf-8")).decode()})
        _gh("-X", "PUT", f"repos/{REPO}/contents/{CARPETA}/{ruta.name}", "--input", "-", entrada=cuerpo)
        print(f"Subido a la nube: {ruta.name} — «{g['titulo']}»")


def iconos():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ilustraciones
    print(", ".join(ilustraciones.ICONOS))


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else "estado"
    {"estado": lambda: estado(), "subir": lambda: subir(sys.argv[2:]), "iconos": lambda: iconos()}[orden]()
