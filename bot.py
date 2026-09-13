"""ShortsBot: busca clips de tus juegos, los convierte en Shorts y los sube a YouTube.

Arranque:  .venv\\Scripts\\pythonw.exe bot.py --abrir
Panel:     http://localhost:8765
"""
import hashlib
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(BASE)
if sys.stdout is None or sys.stderr is None:  # pythonw no tiene consola
    (BASE / "datos").mkdir(exist_ok=True)
    salida = open(BASE / "datos" / "consola.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or salida
    sys.stderr = sys.stderr or salida

import config  # noqa: E402
import editor  # noqa: E402
import estado  # noqa: E402
import estudio  # noqa: E402
import titulos  # noqa: E402
import youtube  # noqa: E402

EXTENSIONES = {".mp4", ".mkv", ".mov"}
CARPETAS_PRIVADAS = {"desktop", "escritorio"}  # grabaciones del escritorio: nunca
SHORTS = BASE / "shorts"
MINIS = estado.DATOS / "miniaturas"
TMP = estado.DATOS / "tmp"
for _c in (SHORTS, MINIS, TMP):
    _c.mkdir(parents=True, exist_ok=True)


def _hora(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")


class Trabajador:
    def __init__(self, cfg):
        self.cfg = cfg
        self.despertar = threading.Event()
        self.encoder = "libx264"
        self.sin_cuota_hasta = 0.0
        self.proxima_busqueda = time.time()
        self.ignorar_juego_hasta = 0.0

    # ------------------------------------------------------------------ bucle
    def bucle(self):
        estado.fase("arrancando", "Comprobando la gráfica y YouTube")
        estado.log("ShortsBot se ha puesto a trabajar")
        self.encoder = editor.detectar_encoder()
        estado.bot(encoder=self.encoder, titulos=titulos.modo() if self.cfg["usar_claude"] else "plantilla")
        self._comprobar_youtube()
        while True:
            try:
                sigue = self._ciclo()
            except Exception as e:
                estado.log(f"Error inesperado: {e}", "error")
                estado.log_archivo.error(traceback.format_exc())
                estado.fase("error", str(e))
                sigue = False
            if not sigue:
                self._esperar(self.cfg["minutos_entre_busquedas"] * 60)

    def _esperar(self, segundos):
        fin = time.time() + segundos
        self.proxima_busqueda = fin
        estado.agente(None)
        self.despertar.clear()
        while time.time() < fin:
            estado.bot()  # latido: el panel sabe que sigo vivo
            if self.despertar.wait(5):
                return

    def _ciclo(self):
        if estado.leer(lambda e: e["bot"]["pausado"]):
            estado.fase("pausado", "Lo has pausado desde el panel")
            return False
        self._buscar()
        juego = self._jugando()
        if juego:
            estado.agente("vigia", f"Estás jugando ({juego}): todos quietos")
            estado.fase("jugando", f"Estás jugando ({juego}). Espero a que cierres el juego para no darte lag.")
            self.proxima_busqueda = time.time() + self.cfg["minutos_entre_busquedas"] * 60
            self.despertar.clear()
            while time.time() < self.proxima_busqueda and not self.despertar.wait(5):
                estado.bot()
            return True
        self._informe_diario()
        pendiente = estado.leer(lambda e: min(
            (f for f in e["fuentes"].values() if f["estado"] == "pendiente"),
            key=lambda f: f["visto"], default=None))
        if pendiente:
            self._procesar(pendiente)
            return True
        guiones = estudio.pendientes() if self.cfg["hacer_videos_propios"] else []
        if guiones:
            self._producir(guiones[0])
            return True
        if self._subir_si_toca():
            return True
        self._telemetria()
        self._limpiar()
        estado.fase("esperando", self._resumen_espera())
        return False

    # ------------------------------------------------------------ buscar clips
    def _buscar(self):
        estado.agente("rastreador", "Revisando tus carpetas de clips")
        ahora = time.time()
        conocidas = estado.leer(lambda e: set(e["fuentes"]))
        nuevas = []
        for carpeta in self.cfg["carpetas"]:
            if not carpeta.exists():
                continue
            for ruta in carpeta.rglob("*"):
                if ruta.suffix.lower() not in EXTENSIONES:
                    continue
                if CARPETAS_PRIVADAS & {p.lower() for p in ruta.relative_to(carpeta).parts[:-1]}:
                    continue
                try:
                    st = ruta.stat()
                except OSError:
                    continue
                if ahora - st.st_mtime < 30 or st.st_size < 300_000:
                    continue  # todavía se está guardando
                fid = hashlib.sha1(f"{ruta}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:10]
                if fid in conocidas:
                    continue
                if ruta.parent != carpeta:
                    pista = ruta.parent.name
                else:
                    pista = "Minecraft" if "minecraft" in ruta.name.lower() else ""
                nuevas.append({"id": fid, "ruta": str(ruta), "nombre": ruta.name, "juego": pista,
                               "estado": "pendiente", "visto": ahora, "shorts": [], "error": None})
        if nuevas:
            with estado.editar() as e:
                for f in nuevas:
                    e["fuentes"][f["id"]] = f
            estado.log(f"Rastreador: {len(nuevas)} clip(s) nuevo(s)")
        estado.agente("rastreador", f"{len(nuevas)} clip(s) nuevo(s)" if nuevas else "Nada nuevo en las carpetas")

    def _jugando(self):
        if not self.cfg["pausar_mientras_juegas"] or time.time() < self.ignorar_juego_hasta:
            return None
        r = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                           errors="replace", creationflags=editor.SIN_VENTANA)
        activos = {l.split('","')[0].strip('"').lower() for l in r.stdout.splitlines() if l}
        return next((p for p in self.cfg["procesos_juego"] if p.lower() in activos), None)

    # ------------------------------------------------------------------ editar
    def _procesar(self, fuente):
        fid, ruta, nombre = fuente["id"], Path(fuente["ruta"]), fuente["nombre"]
        with estado.editar() as e:
            e["fuentes"][fid]["estado"] = "procesando"
        estado.agente("analista", f"Buscando el momento con más acción de {nombre}")
        estado.fase("editando", f"Analizando {nombre}", 0)
        try:
            inf = editor.info(ruta)
            momentos = editor.elegir_momentos(ruta, inf, self.cfg["duracion_short"], self.cfg["max_shorts_por_video"])
            if not momentos:
                raise ValueError("el clip es demasiado corto")
            hechos = []
            for n, (ini, fin) in enumerate(momentos, 1):
                hechos.append(self._crear_short(fuente, inf, n, len(momentos), ini, fin))
            with estado.editar() as e:
                e["fuentes"][fid].update(estado="hecho", shorts=hechos)
        except Exception as ex:
            with estado.editar() as e:
                e["fuentes"][fid].update(estado="error", error=str(ex))
            estado.log(f"No he podido editar {nombre}: {ex}", "error")
            estado.log_archivo.error(traceback.format_exc())

    def _crear_short(self, fuente, inf, n, total, ini, fin):
        sid = f"{fuente['id']}-{n}"
        cual = fuente["nombre"] + (f" (parte {n}/{total})" if total > 1 else "")
        ruta = Path(fuente["ruta"])
        dur = fin - ini

        estado.agente("guionista", f"Escribiendo el título de {cual}")
        estado.fase("editando", f"Mirando {cual} para ponerle título", 3)
        fotos = [TMP / f"{sid}-{k}.jpg" for k in range(3)]
        fotos = [f for f, frac in zip(fotos, (0.2, 0.55, 0.85)) if editor.fotograma(ruta, ini + dur * frac, f)]
        ideas = titulos.generar(fotos, fuente["juego"], dur, self.cfg)
        estado.bot(titulos=titulos.modo())

        rotulo = TMP / f"{sid}-rotulo.png"
        editor.crear_rotulo(ideas["texto_en_pantalla"], rotulo)
        salida = SHORTS / f"{sid}.mp4"
        estado.agente("montador", f"Montando «{ideas['texto_en_pantalla']}» en vertical")
        estado.fase("editando", f"Montando {cual} ({dur:.0f} s, vertical)", 10)
        editor.renderizar(ruta, ini, fin, rotulo, salida, inf, self.encoder,
                          progreso=lambda p: estado.bot(progreso=round(10 + p * 0.88)))
        mini = MINIS / f"{sid}.jpg"
        editor.fotograma(salida, dur * 0.6, mini, ancho=360)
        for f in [*fotos, rotulo]:
            f.unlink(missing_ok=True)

        publicable = ideas["publicable"]
        with estado.editar() as e:
            e["shorts"][sid] = {
                "id": sid, "fuente": fuente["id"], "origen": fuente["ruta"], "juego": ideas["juego"],
                "inicio": round(ini, 1), "fin": round(fin, 1), "duracion": round(dur, 1),
                "archivo": str(salida), "miniatura": str(mini),
                "titulo": ideas["titulo"], "texto_en_pantalla": ideas["texto_en_pantalla"],
                "descripcion": ideas["descripcion"], "etiquetas": ideas["etiquetas"],
                "autor": ideas["autor"], "motivo": ideas["motivo"],
                "estado": "listo" if publicable else "descartado",
                "creado": time.time(), "subido_en": None, "youtube_id": None, "privacidad": None,
                "error": None, "forzar": False, "progreso": None,
            }
        if publicable:
            estado.log(f"Short listo: «{ideas['titulo']}»")
        else:
            estado.log(f"He descartado un trozo de {fuente['nombre']}: {ideas['motivo']}", "aviso")
        return sid

    # ------------------------------------------------------------------ estudio
    def _producir(self, ruta):
        """Hace un Short desde cero a partir de un guion de Claude (voz + animación + subtítulos)."""
        try:
            info = estudio.producir(ruta, self.encoder, self.cfg)
        except Exception as ex:
            estudio.archivar(ruta, ok=False, error=ex)
            estado.log(f"No he podido producir el guion {ruta.name}: {ex}", "error")
            estado.log_archivo.error(traceback.format_exc())
            return
        estudio.archivar(ruta, ok=True)
        with estado.editar() as e:
            e["shorts"][info["id"]] = {
                **info, "fuente": "guion", "origen": str(ruta), "juego": "Minecraft", "inicio": 0,
                "fin": info["duracion"], "autor": "claude", "motivo": "Guion escrito por Claude",
                "tipo": "estudio", "estado": "listo", "creado": time.time(), "subido_en": None,
                "youtube_id": None, "privacidad": None, "error": None, "forzar": False, "progreso": None,
            }
        estado.log(f"Estudio: Short hecho desde cero «{info['titulo']}» ({info['escena']['modo']}, "
                   f"{info['escena']['bioma']}, {info['escena']['hora']})")

    # ------------------------------------------------------------------- subir
    def _siguiente_hueco(self, desde, subidas):
        """Primer momento >= desde en el que las reglas dejan subir, contando las subidas hechas o previstas."""
        a, b = self.cfg["horario_subida"]
        maximo, separacion = self.cfg["max_shorts_por_dia"], self.cfg["horas_entre_subidas"] * 3600
        t = max(desde, self.sin_cuota_hasta)
        for _ in range(200):
            d = datetime.fromtimestamp(t)
            medianoche = datetime.combine(d.date(), datetime.min.time())
            manana = (medianoche + timedelta(days=1, hours=a)).timestamp()
            if sum(datetime.fromtimestamp(s).date() == d.date() for s in subidas) >= maximo or d.hour >= b:
                t = manana
            elif d.hour < a:
                t = (medianoche + timedelta(hours=a)).timestamp()
            elif subidas and max(subidas) + separacion > t:
                t = max(subidas) + separacion
            else:
                break
        return t

    def _subidas_hechas(self):
        return estado.leer(lambda e: [s["subido_en"] for s in e["shorts"].values() if s["subido_en"]])

    def _cola(self):
        return estado.leer(lambda e: sorted(
            (s for s in e["shorts"].values() if s["estado"] == "listo"),
            key=lambda s: (not s["forzar"], s["creado"])))

    def _puede_subir(self):
        """(se puede, explicación, momento de la próxima subida)"""
        ahora = time.time()
        subidas = self._subidas_hechas()
        cuando = self._siguiente_hueco(ahora, subidas)
        if cuando <= ahora + 1:
            return True, "", ahora
        a, b = self.cfg["horario_subida"]
        n_hoy = sum(datetime.fromtimestamp(t).date() == datetime.now().date() for t in subidas)
        if ahora < self.sin_cuota_hasta:
            motivo = "YouTube no deja subir más por hoy (cuota agotada)"
        elif n_hoy >= self.cfg["max_shorts_por_dia"]:
            motivo = f"Ya he subido {n_hoy} hoy, que es el máximo"
        elif not a <= datetime.now().hour < b:
            motivo = f"Solo subo entre las {a}:00 y las {b}:00"
        else:
            motivo = "Dejo unas horas entre Short y Short"
        return False, motivo, cuando

    def parrilla(self):
        """Parrilla de emisión: a qué hora saldrá cada Short de la cola si todo sigue igual."""
        subidas = self._subidas_hechas()
        t, res = time.time(), []
        for s in self._cola():
            cuando = t if s["forzar"] else self._siguiente_hueco(t, subidas)
            subidas.append(cuando)
            res.append({"id": s["id"], "titulo": s["titulo"], "juego": s["juego"], "cuando": cuando,
                        "forzar": s["forzar"]})
            t = cuando
        return res

    def _subir_si_toca(self):
        cola = self._cola()
        if not cola or not self.cfg["subir_a_youtube"]:
            return False
        s = cola[0]
        ok, motivo, cuando = self._puede_subir()
        if not s["forzar"] and not ok:
            estado.agente("planificador", f"{len(cola)} en parrilla · siguiente a las {_hora(cuando)}")
            return False
        if not estado.leer(lambda e: e["bot"]["youtube"]):
            estado.agente("planificador", "Esperando a que conectes YouTube")
            return False
        estado.agente("planificador", "¡Toca subir!")
        self._subir(s)
        return True

    def _subir(self, s):
        sid = s["id"]
        with estado.editar() as e:
            e["shorts"][sid].update(estado="subiendo", progreso=0)
        estado.agente("mensajero", f"Subiendo «{s['titulo']}»")
        estado.fase("subiendo", f"Subiendo «{s['titulo']}» a YouTube", 0)

        def progreso(p):
            estado.bot(progreso=round(p))
            with estado._lock:
                estado._estado["shorts"][sid]["progreso"] = round(p)

        try:
            vid, privacidad = youtube.subir(s["archivo"], s["titulo"], s["descripcion"], s["etiquetas"],
                                            self.cfg["privacidad"], progreso,
                                            sintetico=self.cfg["marcar_sintetico"] and s.get("tipo") == "estudio")
        except youtube.NecesitaConectar as ex:
            estado.bot(youtube=None)
            self._volver_a_cola(sid)
            estado.log(f"{ex}. Pulsa «Conectar YouTube» en el panel.", "error")
            return
        except youtube.SinCuota as ex:
            self.sin_cuota_hasta = time.time() + 12 * 3600
            self._volver_a_cola(sid)
            estado.log(str(ex), "aviso")
            return
        except Exception as ex:
            with estado.editar() as e:
                e["shorts"][sid].update(estado="error", error=str(ex), progreso=None)
            estado.log(f"Fallo al subir «{s['titulo']}»: {ex}", "error")
            return
        with estado.editar() as e:
            e["shorts"][sid].update(estado="subido", youtube_id=vid, privacidad=privacidad,
                                    subido_en=time.time(), progreso=None, forzar=False, error=None)
        estado.log(f"Subido a YouTube ({privacidad}): «{s['titulo']}»")

    def _volver_a_cola(self, sid):
        with estado.editar() as e:
            e["shorts"][sid].update(estado="listo", progreso=None)

    def _resumen_espera(self):
        cola = estado.leer(lambda e: sum(s["estado"] == "listo" for s in e["shorts"].values()))
        if not cola:
            return "Todo al día. Busco clips nuevos cada pocos minutos."
        if not self.cfg["subir_a_youtube"]:
            return f"{cola} Short(s) listos. La subida a YouTube está desactivada en config.json."
        if not estado.leer(lambda e: e["bot"]["youtube"]):
            return f"{cola} Short(s) listos, pero falta conectar YouTube."
        ok, motivo, cuando = self._puede_subir()
        return f"{cola} Short(s) en cola. {motivo}. Próxima subida hacia las {_hora(cuando)}."

    def proxima_subida(self):
        ok, motivo, cuando = self._puede_subir()
        return {"ya": ok, "motivo": motivo, "hora": _hora(cuando)}

    # ---------------------------------------------------------------- rutinas
    HORAS_TELEMETRIA = 6
    HORA_INFORME = 22

    def _telemetria(self, forzar=False):
        """El Estadista lee las visitas de tus Shorts cada pocas horas."""
        ultima = estado.leer(lambda e: e["rutinas"]["telemetria"])
        if not forzar and time.time() - ultima < self.HORAS_TELEMETRIA * 3600:
            return
        ids = estado.leer(lambda e: [s["youtube_id"] for s in e["shorts"].values() if s["youtube_id"]])
        if not ids or not estado.leer(lambda e: e["bot"]["youtube"]):
            return
        estado.agente("estadista", f"Leyendo las visitas de {len(ids)} Short(s)")
        try:
            datos = youtube.estadisticas(ids)
        except Exception as ex:
            estado.log(f"Estadista: no he podido leer las visitas ({ex})", "aviso")
            datos = None
        with estado.editar() as e:
            e["rutinas"]["telemetria"] = time.time()
            for s in e["shorts"].values():
                if datos and s["youtube_id"] in datos:
                    s.update(datos[s["youtube_id"]])
        if datos is not None:
            total = sum(d["vistas"] for d in datos.values())
            estado.agente("estadista", f"{total} visitas en total")

    def _limpiar(self):
        """Borra solo los Shorts generados por el bot que ya están en YouTube (o descartados), no tus grabaciones."""
        ahora = time.time()
        plazo_subido = self.cfg["borrar_subidos_tras_dias"] * 86400
        plazo_descartado = self.cfg["borrar_descartados_tras_dias"] * 86400
        borrados, liberado = 0, 0
        with estado.editar() as e:
            for s in e["shorts"].values():
                archivo = Path(s.get("archivo") or "")
                if s.get("borrado") or not archivo.name or SHORTS not in archivo.parents:
                    continue
                subido_hace = ahora - (s["subido_en"] or ahora)
                descartado_hace = ahora - s["creado"]
                if (s["estado"] == "subido" and s["youtube_id"] and subido_hace > plazo_subido) or \
                        (s["estado"] == "descartado" and descartado_hace > plazo_descartado):
                    if archivo.exists():
                        liberado += archivo.stat().st_size
                        archivo.unlink()
                        borrados += 1
                    s["borrado"] = True
        if borrados:
            estado.log(f"Limpieza: he borrado {borrados} vídeo(s) de tu PC que ya están en YouTube o descartados "
                       f"({liberado / 1e6:.0f} MB libres)")

    def _informe_diario(self):
        """A las 22:00 el Núcleo deja un resumen del día en la actividad."""
        hoy = datetime.now().date()
        if datetime.now().hour < self.HORA_INFORME or estado.leer(lambda e: e["rutinas"]["informe"]) == str(hoy):
            return
        e = estado.foto()
        del_dia = lambda t: t and datetime.fromtimestamp(t).date() == hoy  # noqa: E731
        clips = sum(del_dia(f["visto"]) for f in e["fuentes"].values())
        hechos = sum(del_dia(s["creado"]) for s in e["shorts"].values())
        subidos = sum(del_dia(s["subido_en"]) for s in e["shorts"].values())
        cola = sum(s["estado"] == "listo" for s in e["shorts"].values())
        vistas = sum(s.get("vistas", 0) for s in e["shorts"].values())
        with estado.editar() as ed:
            ed["rutinas"]["informe"] = str(hoy)
        estado.log(f"📋 Informe del día: {clips} clip(s) nuevo(s), {hechos} Short(s) montado(s), "
                   f"{subidos} subido(s), {cola} en parrilla y {vistas} visitas en total.")

    def rutinas(self):
        ahora = datetime.now()
        informe = datetime.combine(ahora.date(), datetime.min.time()) + timedelta(hours=self.HORA_INFORME)
        if estado.leer(lambda e: e["rutinas"]["informe"]) == str(ahora.date()):
            informe += timedelta(days=1)
        parrilla = self.parrilla()
        ultima_tel = estado.leer(lambda e: e["rutinas"]["telemetria"])
        guionistas = datetime.combine(ahora.date(), datetime.min.time()) + timedelta(hours=self.cfg["hora_guionistas"])
        if guionistas < ahora:
            guionistas += timedelta(days=1)
        return [
            {"id": "guionistas", "nombre": "Sala de guionistas", "agentes": "Claude → Guionista",
             "texto": f"Escribe {self.cfg['guiones_por_dia']} guiones de curiosidades al día",
             "proxima": guionistas.timestamp() if self.cfg["hacer_videos_propios"] else None},
            {"id": "busqueda", "nombre": "Ronda de búsqueda", "agentes": "Rastreador",
             "texto": f"Revisa tus carpetas cada {self.cfg['minutos_entre_busquedas']} min",
             "proxima": self.proxima_busqueda},
            {"id": "emision", "nombre": "Emisión", "agentes": "Planificador → Mensajero",
             "texto": f"Máx. {self.cfg['max_shorts_por_dia']} al día, {self.cfg['horario_subida'][0]}–"
                      f"{self.cfg['horario_subida'][1]} h",
             "proxima": parrilla[0]["cuando"] if parrilla else None},
            {"id": "telemetria", "nombre": "Telemetría", "agentes": "Estadista",
             "texto": f"Lee las visitas de YouTube cada {self.HORAS_TELEMETRIA} h",
             "proxima": max(time.time(), ultima_tel + self.HORAS_TELEMETRIA * 3600)},
            {"id": "informe", "nombre": "Informe diario", "agentes": "Núcleo",
             "texto": "Resumen del día en la actividad", "proxima": informe.timestamp()},
        ]

    def orden(self, texto, local):
        """Barra de órdenes del centro de control (sin IA: entiende frases sencillas)."""
        t = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
        tiene = lambda *palabras: any(p in t for p in palabras)  # noqa: E731
        if tiene("aunque", "hazlo ya", "trabaja ya", "ahora mismo", "no esperes"):
            return self.accion("ignorar_juego")
        if tiene("reanuda", "sigue", "continua", "vuelve", "arranca", "despierta"):
            return self.accion("reanudar")
        if tiene("pausa", "para", "deten", "descansa", "stop"):
            return self.accion("pausar")
        if tiene("conecta") and tiene("youtube", "canal"):
            return self.accion("conectar_youtube") if local else "Eso solo se puede hacer desde el PC."
        if tiene("sube", "publica", "lanza"):
            cola = self._cola()
            if not cola:
                return "No hay ningún Short en la parrilla ahora mismo."
            return self.accion("subir_ahora", cola[0]["id"])
        if tiene("busca", "rastrea", "clips nuevos"):
            return self.accion("buscar")
        if tiene("visita", "estadistic", "telemetr"):
            threading.Thread(target=self._telemetria, kwargs={"forzar": True}, daemon=True).start()
            vistas = estado.leer(lambda e: sum(s.get("vistas", 0) for s in e["shorts"].values()))
            return f"Llevas {vistas} visitas. Le he pedido al Estadista que las actualice."
        if tiene("parrilla", "cuando", "proxim", "agenda"):
            p = self.parrilla()
            if not p:
                return "La parrilla está vacía."
            return " · ".join(f"{_hora(x['cuando'])} «{x['titulo'][:40]}»" for x in p[:3])
        if tiene("que haces", "estado", "trabaj", "como vas", "que tal"):
            b = estado.leer(lambda e: e["bot"])
            return b["detalle"] or "Aquí estoy, todo en orden."
        if tiene("video de", "haz un video", "crea un video"):
            return ("Todavía no invento vídeos desde cero: monto Shorts con tus clips. Guarda uno con Alt+F10 "
                    "o mételo en la carpeta «entrada» y me pongo.")
        return ("Puedo: «pausa», «sigue», «busca clips», «sube el siguiente», «¿qué haces?», "
                "«parrilla», «visitas» o «conecta YouTube».")

    def _comprobar_youtube(self):
        try:
            canal = youtube.nombre_canal()
            estado.bot(youtube=canal)
            estado.log(f"Conectado al canal de YouTube «{canal}»")
        except youtube.NecesitaConectar:
            estado.bot(youtube=None)
        except Exception as ex:
            estado.bot(youtube=None)
            estado.log(f"No he podido comprobar YouTube: {ex}", "aviso")

    # ------------------------------------------------------ acciones del panel
    def accion(self, nombre, sid=None):
        """Devuelve un mensaje para mostrar en el panel."""
        if nombre == "pausar":
            with estado.editar() as e:
                e["bot"]["pausado"] = True
            estado.fase("pausado", "Lo has pausado desde el panel")
            estado.log("Pausado desde el panel")
            return "Pausado. Terminaré lo que estoy haciendo y pararé."
        if nombre == "reanudar":
            with estado.editar() as e:
                e["bot"]["pausado"] = False
            estado.log("Reanudado desde el panel")
            self.despertar.set()
            return "¡Vuelvo al trabajo!"
        if nombre == "buscar":
            self.despertar.set()
            return "Buscando clips nuevos…"
        if nombre == "ignorar_juego":
            self.ignorar_juego_hasta = time.time() + 3600
            estado.agente("vigia", f"Me has dicho que trabaje aunque juegues, hasta las {_hora(self.ignorar_juego_hasta)}")
            estado.log("Vigía: trabajo aunque estés jugando durante 1 hora")
            self.despertar.set()
            return "Vale, trabajo aunque estés jugando durante 1 hora. Si notas lag, dime «pausa»."
        if nombre == "conectar_youtube":
            threading.Thread(target=self._conectar_youtube, daemon=True).start()
            return "Se ha abierto el navegador en el PC: inicia sesión con tu cuenta de YouTube y pulsa Permitir."

        with estado.editar() as e:
            s = e["shorts"].get(sid)
            if not s:
                return "Ese Short ya no existe."
            if nombre == "subir_ahora":
                if s["estado"] in ("subido", "subiendo"):
                    return "Ese Short ya está subido."
                s.update(estado="listo", forzar=True, error=None)
                self.despertar.set()
                return "Lo subo en cuanto termine lo que estoy haciendo."
            if nombre == "descartar":
                if s["estado"] in ("subido", "subiendo"):
                    return "Ya está en YouTube: bórralo desde YouTube Studio si no lo quieres."
                s.update(estado="descartado", motivo="Descartado por ti", forzar=False)
                return "Descartado. No lo subiré."
            if nombre == "recuperar":
                s.update(estado="listo", forzar=False, error=None)
                return "Vuelve a estar en la cola."
            vid = s["youtube_id"]
        if nombre == "publicar":
            try:
                nueva = youtube.cambiar_privacidad(vid, "public")
            except Exception as ex:
                return f"YouTube no ha dejado publicarlo: {ex}"
            with estado.editar() as e:
                e["shorts"][sid]["privacidad"] = nueva
            if nueva != "public":
                return ("YouTube lo mantiene en privado: tu app todavía no está verificada por Google "
                        "(mira LEEME.md, apartado «Publicar en público»).")
            estado.log(f"Publicado: {vid}")
            return "¡Publicado!"
        if nombre == "mostrar":
            archivo = estado.leer(lambda e: e["shorts"][sid]["archivo"])
            subprocess.Popen(["explorer", f"/select,{archivo}"])
            return "Abierto en el Explorador."
        return "Acción desconocida."

    def _conectar_youtube(self):
        try:
            canal = youtube.conectar()
            estado.bot(youtube=canal)
            estado.log(f"YouTube conectado: canal «{canal}»")
            self.despertar.set()
        except Exception as ex:
            estado.log(f"No se ha podido conectar YouTube: {ex}", "error")


def abrir_app(url):
    """Abre el panel en su propia ventana (modo app de Chrome/Edge); si no hay, en el navegador normal."""
    import shutil
    import winreg
    for exe in ("chrome.exe", "msedge.exe"):
        for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                ruta = winreg.QueryValue(raiz, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}")
            except OSError:
                continue
            if ruta and Path(ruta.strip('"')).exists():
                subprocess.Popen([ruta.strip('"'), f"--app={url}", "--window-size=460,900"])
                return
        if shutil.which(exe):
            subprocess.Popen([exe, f"--app={url}"])
            return
    webbrowser.open(url)


def _puerto_ocupado(puerto):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def main():
    cfg = config.cargar()
    url = f"http://localhost:{cfg['puerto_panel']}"
    if _puerto_ocupado(cfg["puerto_panel"]):
        if "--abrir" in sys.argv:
            abrir_app(url)  # ya estaba funcionando: solo abrimos el panel
        return
    estado.cargar()
    trabajador = Trabajador(cfg)
    threading.Thread(target=trabajador.bucle, daemon=True, name="trabajador").start()

    import panel
    app = panel.crear_app(trabajador, cfg)
    if "--abrir" in sys.argv:
        threading.Timer(1.5, abrir_app, [url]).start()
    app.run(host="0.0.0.0", port=cfg["puerto_panel"], threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
