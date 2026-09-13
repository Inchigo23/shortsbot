"""Panel web: http://localhost:8765 en el PC, o con el QR desde el móvil (misma Wi-Fi)."""
import secrets
import socket
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, make_response, request, send_file

import estado
import estudio

BASE = Path(__file__).resolve().parent
CLAVE = estado.DATOS / "clave_panel.txt"
LOCALES = {"127.0.0.1", "::1"}


def _clave():
    if not CLAVE.exists():
        CLAVE.write_text(secrets.token_urlsafe(16), encoding="utf-8")
    return CLAVE.read_text(encoding="utf-8").strip()


def _crear_iconos():
    """Icono de la app (diseño propio): núcleo brillante con una órbita y 3 agentes."""
    from PIL import Image, ImageDraw, ImageFilter
    for tam in (192, 512):
        ruta = estado.DATOS / f"icono-{tam}.png"
        if ruta.exists():
            continue
        s = tam / 512
        img = Image.new("RGBA", (tam, tam), (6, 10, 24, 255))
        brillo = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
        ImageDraw.Draw(brillo).ellipse([int(136 * s), int(136 * s), int(376 * s), int(376 * s)], fill=(94, 242, 255, 150))
        img.alpha_composite(brillo.filter(ImageFilter.GaussianBlur(int(40 * s))))
        d = ImageDraw.Draw(img)
        d.ellipse([int(60 * s), int(170 * s), int(452 * s), int(342 * s)], outline=(143, 246, 255, 220), width=max(2, int(12 * s)))
        d.ellipse([int(196 * s), int(196 * s), int(316 * s), int(316 * s)], fill=(215, 252, 255, 255))
        # triángulo de "play" en el núcleo
        d.polygon([(int(236 * s), int(222 * s)), (int(236 * s), int(290 * s)), (int(292 * s), int(256 * s))], fill=(6, 52, 68, 255))
        for cx, cy, color in ((88, 214, (251, 191, 36)), (430, 300, (232, 121, 249)), (256, 92, (74, 222, 128))):
            r = int(30 * s)
            d.regular_polygon((int(cx * s), int(cy * s), r), 6, fill=color)
        img.save(ruta)


def _ip_local():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def crear_app(trabajador, cfg):
    app = Flask(__name__, static_folder=None)
    clave = _clave()
    _crear_iconos()

    def es_local():
        return request.remote_addr in LOCALES

    @app.before_request
    def comprobar_acceso():
        # En el PC entra sin más; desde el móvil hace falta la clave del QR.
        if es_local() or clave in (request.cookies.get("k"), request.args.get("k")):
            return None
        return ("<meta name=viewport content='width=device-width'><h2 style='font-family:sans-serif'>"
                "Escanea el QR que aparece en el panel del PC para entrar.</h2>", 401)

    @app.get("/")
    def inicio():
        r = make_response(send_file(BASE / "panel.html"))
        r.headers["Cache-Control"] = "no-store"
        if request.args.get("k") == clave:
            r.set_cookie("k", clave, max_age=3600 * 24 * 365, samesite="Lax")
        return r

    # ---- App instalable (PWA): en el PC con "Instalar", en el móvil con "Añadir a pantalla de inicio"
    @app.get("/manifest.webmanifest")
    def manifiesto():
        inicio = "/" if es_local() else f"/?k={clave}"
        r = jsonify({
            "name": "ShortsBot · Centro de control", "short_name": "ShortsBot", "lang": "es",
            "start_url": inicio, "scope": "/", "display": "standalone",
            "background_color": "#060a18", "theme_color": "#060a18",
            "description": "Controla ShortsBot: qué está haciendo, la parrilla de subidas y los Shorts.",
            "icons": [{"src": "/icono-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                      {"src": "/icono-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
        })
        r.mimetype = "application/manifest+json"
        return r

    @app.get("/icono-<int:tam>.png")
    def icono(tam):
        ruta = estado.DATOS / f"icono-{tam}.png"
        return send_file(ruta, mimetype="image/png", max_age=86400) if ruta.exists() else ("", 404)

    @app.get("/sw.js")
    def service_worker():
        r = make_response(send_file(BASE / "sw.js", mimetype="text/javascript"))
        r.headers["Cache-Control"] = "no-cache"
        return r

    @app.get("/api/estado")
    def api_estado():
        e = estado.foto()
        hoy = datetime.now().date()
        shorts = sorted(e["shorts"].values(), key=lambda s: s["creado"], reverse=True)
        for s in shorts:
            for campo in ("archivo", "miniatura", "origen"):
                s.pop(campo, None)
        datos = {
            "ahora": time.time(),
            "bot": e["bot"],
            "shorts": shorts[:80],
            "log": e["log"][-60:][::-1],
            "pendientes": sum(f["estado"] in ("pendiente", "procesando") for f in e["fuentes"].values()),
            "en_cola": sum(s["estado"] == "listo" for s in e["shorts"].values()),
            "subidos_hoy": sum(bool(s["subido_en"]) and datetime.fromtimestamp(s["subido_en"]).date() == hoy
                               for s in e["shorts"].values()),
            "subidos_total": sum(s["estado"] == "subido" for s in e["shorts"].values()),
            "max_dia": cfg["max_shorts_por_dia"],
            "privacidad": cfg["privacidad"],
            "proxima": trabajador.proxima_subida(),
            "parrilla": trabajador.parrilla()[:20],
            "rutinas": trabajador.rutinas(),
            "fuentes_total": len(e["fuentes"]),
            "guiones_pendientes": len(estudio.pendientes()),
            "hechos_estudio": sum(s.get("tipo") == "estudio" for s in e["shorts"].values()),
            "vistas_total": sum(s.get("vistas", 0) for s in e["shorts"].values()),
            "carpetas": [str(c) for c in cfg["carpetas"]],
            "local": es_local(),
        }
        if es_local():
            datos["url_movil"] = f"http://{_ip_local()}:{cfg['puerto_panel']}/?k={clave}"
        return jsonify(datos)

    @app.post("/api/accion")
    def api_accion():
        cuerpo = request.get_json(force=True)
        nombre = cuerpo.get("accion")
        if nombre in ("mostrar", "conectar_youtube") and not es_local():
            return jsonify(mensaje="Eso solo se puede hacer desde el PC.")
        return jsonify(mensaje=trabajador.accion(nombre, cuerpo.get("id")))

    @app.post("/api/orden")
    def api_orden():
        texto = (request.get_json(force=True).get("texto") or "").strip()[:200]
        if not texto:
            return jsonify(mensaje="Dime algo, por ejemplo «¿qué haces?»")
        return jsonify(mensaje=trabajador.orden(texto, es_local()))

    def _archivo(sid, campo):
        ruta = estado.leer(lambda e: (e["shorts"].get(sid) or {}).get(campo))
        if not ruta or not Path(ruta).exists():
            return None
        return ruta

    @app.get("/media/<sid>.mp4")
    def video(sid):
        ruta = _archivo(sid, "archivo")
        return send_file(ruta, mimetype="video/mp4", conditional=True) if ruta else ("", 404)

    @app.get("/media/<sid>.jpg")
    def miniatura(sid):
        ruta = _archivo(sid, "miniatura")
        return send_file(ruta, mimetype="image/jpeg", max_age=3600) if ruta else ("", 404)

    return app
