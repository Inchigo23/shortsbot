"""Conexión con YouTube (API oficial de Google): login una vez, luego sube solo."""
import json
import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

BASE = Path(__file__).resolve().parent
SECRETO = BASE / "client_secret.json"  # lo descargas de Google Cloud (ver LEEME.md)
TOKEN = BASE / "datos" / "token_youtube.json"
# Solo YouTube (subir y gestionar tus vídeos). Para la voz de Google haría falta añadir
# "https://www.googleapis.com/auth/cloud-platform" y activar la facturación del proyecto.
PERMISOS = ["https://www.googleapis.com/auth/youtube"]
PERMISO_VOZ = "https://www.googleapis.com/auth/cloud-platform"
CATEGORIA_GAMING = "20"


class NecesitaConectar(Exception):
    pass


class SinCuota(Exception):
    pass


def _credenciales():
    en_la_nube = os.environ.get("YOUTUBE_TOKEN")  # secreto de GitHub Actions (mismo contenido que TOKEN)
    if en_la_nube:
        cred = Credentials.from_authorized_user_info(json.loads(en_la_nube), PERMISOS)
        if not cred.valid:
            try:
                cred.refresh(Request())
            except RefreshError as e:
                raise NecesitaConectar("El permiso de YouTube ha caducado, vuelve a conectar") from e
        return cred
    if not TOKEN.exists():
        raise NecesitaConectar("YouTube no está conectado")
    cred = Credentials.from_authorized_user_file(str(TOKEN), PERMISOS)
    if cred.valid:
        return cred
    if cred.expired and cred.refresh_token:
        try:
            cred.refresh(Request())
        except RefreshError as e:
            raise NecesitaConectar("El permiso de YouTube ha caducado, vuelve a conectar") from e
        TOKEN.write_text(cred.to_json(), encoding="utf-8")
        return cred
    raise NecesitaConectar("YouTube no está conectado")


def _servicio():
    return build("youtube", "v3", credentials=_credenciales(), cache_discovery=False)


def servicio_voz():
    """Cliente de Google Text-to-Speech con tu permiso; el gasto va a tu proyecto de Google Cloud."""
    cred = _credenciales()
    concedidos = json.loads(TOKEN.read_text(encoding="utf-8")).get("scopes") or []
    if PERMISO_VOZ not in concedidos:
        raise NecesitaConectar("Vuelve a conectar YouTube para dar permiso también a la voz de Google")
    proyecto = json.loads(SECRETO.read_text(encoding="utf-8"))["installed"].get("project_id")
    if proyecto:
        cred = cred.with_quota_project(proyecto)
    return build("texttospeech", "v1", credentials=cred, cache_discovery=False)


def conectar():
    """Abre el navegador del PC para que inicies sesión y des permiso. Solo hace falta una vez."""
    if not SECRETO.exists():
        raise FileNotFoundError("Falta client_secret.json en la carpeta ShortsBot (mira LEEME.md)")
    flujo = InstalledAppFlow.from_client_secrets_file(str(SECRETO), PERMISOS)
    cred = flujo.run_local_server(port=0, prompt="consent", access_type="offline",
                                  success_message="Listo. Ya puedes cerrar esta pestaña y volver al panel de ShortsBot.")
    TOKEN.write_text(cred.to_json(), encoding="utf-8")
    return nombre_canal()


def estadisticas_canal(max_videos=50):
    """Datos del canal y de sus últimos vídeos (también los privados, porque es tu cuenta)."""
    s = _servicio()
    try:
        canal = s.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()["items"][0]
        subidas = canal["contentDetails"]["relatedPlaylists"]["uploads"]
        items = s.playlistItems().list(part="contentDetails", playlistId=subidas, maxResults=max_videos).execute()
        ids = [i["contentDetails"]["videoId"] for i in items.get("items", [])]
        videos = s.videos().list(part="snippet,statistics,status,contentDetails", id=",".join(ids)).execute() if ids else {}
    except HttpError as e:
        raise _traducir(e) from e
    st = canal["statistics"]
    return {
        "titulo": canal["snippet"]["title"],
        "imagen": canal["snippet"]["thumbnails"].get("default", {}).get("url"),
        "suscriptores": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0)),
        "vistas": int(st.get("viewCount", 0)),
        "videos": int(st.get("videoCount", 0)),
    }, [{
        "id": v["id"], "titulo": v["snippet"]["title"], "publicado": v["snippet"]["publishedAt"],
        "privacidad": v["status"]["privacyStatus"], "imagen": v["snippet"]["thumbnails"].get("medium", {}).get("url"),
        "vistas": int(v["statistics"].get("viewCount", 0)), "likes": int(v["statistics"].get("likeCount", 0)),
        "comentarios": int(v["statistics"].get("commentCount", 0)),
    } for v in videos.get("items", [])]


def nombre_canal():
    r = _servicio().channels().list(part="snippet", mine=True).execute()
    items = r.get("items") or []
    return items[0]["snippet"]["title"] if items else "(sin canal)"


def _limpio(texto):
    return texto.replace("<", "").replace(">", "")


def _traducir(e: HttpError):
    razon = str(e)
    if e.resp.status == 401:
        return NecesitaConectar("YouTube ha rechazado el permiso, vuelve a conectar")
    if "quotaExceeded" in razon or "uploadLimitExceeded" in razon:
        return SinCuota("Se ha acabado la cuota diaria de YouTube, sigo mañana")
    return RuntimeError(f"YouTube respondió {e.resp.status}: {razon[-300:]}")


def subir(ruta, titulo, descripcion, etiquetas, privacidad, progreso=None, sintetico=False):
    cuerpo = {
        "snippet": {
            "title": _limpio(titulo)[:100],
            "description": _limpio(descripcion)[:4900],
            "tags": etiquetas,
            "categoryId": CATEGORIA_GAMING,
        },
        "status": {"privacyStatus": privacidad, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": sintetico},
    }
    medio = MediaFileUpload(str(ruta), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    peticion = _servicio().videos().insert(part="snippet,status", body=cuerpo, media_body=medio)
    respuesta = None
    try:
        while respuesta is None:
            estado_subida, respuesta = peticion.next_chunk(num_retries=5)
            if estado_subida and progreso:
                progreso(estado_subida.progress() * 100)
    except HttpError as e:
        raise _traducir(e) from e
    return respuesta["id"], respuesta.get("status", {}).get("privacyStatus", privacidad)


def estadisticas(ids):
    """{id: {"vistas": n, "likes": n}} de tus vídeos subidos (1 unidad de cuota por cada 50)."""
    res = {}
    try:
        for i in range(0, len(ids), 50):
            r = _servicio().videos().list(part="statistics", id=",".join(ids[i:i + 50])).execute()
            for v in r.get("items", []):
                st = v.get("statistics", {})
                res[v["id"]] = {"vistas": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0))}
    except HttpError as e:
        raise _traducir(e) from e
    return res


def cambiar_privacidad(video_id, privacidad):
    try:
        r = _servicio().videos().update(
            part="status",
            body={"id": video_id, "status": {"privacyStatus": privacidad, "selfDeclaredMadeForKids": False}},
        ).execute()
    except HttpError as e:
        raise _traducir(e) from e
    return r["status"]["privacyStatus"]
