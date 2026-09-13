# ShortsBot

Convierte tus clips de Minecraft (y otros juegos) en YouTube Shorts y los sube solo.

**Qué hace, sin que toques nada:**
1. Vigila `Videos\NVIDIA` (donde se guardan los clips de NVIDIA) y la carpeta `ShortsBot\entrada`.
2. Busca el momento con más acción de cada clip (el pico de sonido: explosiones, golpes, gritos…).
3. Lo convierte en vertical 1080×1920, con fondo desenfocado, texto gancho arriba y el volumen normalizado.
4. Le pone título, descripción y hashtags (con Claude si tienes una API key; si no, con plantillas).
5. Lo sube a YouTube: como mucho 2 al día, dejando 4 horas entre uno y otro y solo entre las 12:00 y las 22:00.
6. No hace nada mientras juegas, para no darte lag.

**Panel (centro de control):** http://localhost:8765 en el PC. En el móvil, escanea el QR que sale abajo del
panel (con la misma Wi-Fi).

- **Mapa de agentes:** el Núcleo en el centro y 8 agentes en órbita. Cada uno es un paso real del bot: 🔭 Rastreador
  (busca clips), 🎮 Vigía (detecta si juegas), 📈 Analista (elige el momento), ✍️ Guionista (título), 🎬 Montador
  (edita), 🗓️ Planificador (decide la hora), 🚀 Mensajero (sube) y 📊 Estadista (lee las visitas). El haz de luz
  apunta al que está trabajando. Toca un agente para ver qué ha hecho.
- **Parrilla de emisión:** a qué hora saldrá cada Short de la cola.
- **Rutinas:** búsqueda cada 2 min, emisión, telemetría cada 6 h e informe diario a las 22:00, con cuenta atrás.
- **Barra de órdenes:** escribe «¿qué haces?», «pausa», «sigue», «busca clips», «sube el siguiente», «parrilla»,
  «visitas» o «conecta YouTube». Entiende frases sencillas; no es un chat con IA.

**Nunca toca** las grabaciones del escritorio (`NVIDIA\Desktop`) ni el resto de tu carpeta `Videos`.

---

## Vídeos hechos desde cero (Estudio)

Además de tus clips, ShortsBot hace vídeos **sin que grabes nada**:

1. **Sala de guionistas** (tarea programada de Claude, todos los días a las 10:00): Claude escribe 2 guiones
   de curiosidades de Minecraft, **comprueba cada dato** en minecraft.wiki y los guarda en `guiones\pendientes`.
   Solo funciona si la app de Claude está abierta; si estaba cerrada, lo hace al abrirla. La primera vez,
   entra en **Programadas → ShortsBot · Sala de guionistas → Ejecutar ahora** y aprueba los permisos que pida
   (buscar en internet y escribir en la carpeta). Así las siguientes veces no se para a preguntar.
2. 🎙️ **Narrador:** pone la voz con una voz neural en español (Piper, sin internet, licencia CC0).
3. 🧱 **Animador:** genera con la gráfica un mundo de bloques **original** (texturas propias, no las del juego)
   y graba un parkour o un vuelo distinto en cada vídeo: bosque, llanura, desierto, nieve o montaña, de día,
   al atardecer o de noche.
4. 🎬 **Montador:** subtítulos grandes palabra a palabra (la que suena, en amarillo) y el gancho arriba.
5. Van a la misma parrilla que el resto y se suben con el mismo límite de 2 al día.

Los guiones ya usados van a `guiones\hechos`, y los que fallan a `guiones\errores` (junto a un `.txt` con el
motivo). También puedes escribir tus propios guiones con el mismo formato (mira el principio de `estudio.py`).

Para no hacer vídeos propios, pon `"hacer_videos_propios": false` en `config.json`.

---

## La app

- **En el PC:** icono **ShortsBot** del escritorio. Abre el centro de control en su propia ventana (si el bot
  estaba apagado, lo enciende). En Chrome también puedes instalarla desde el botón «⬇ Instalar app».
- **En el móvil (en casa):** tu Wi-Fi tiene que estar como red **privada** y el puerto 8765 abierto en el
  firewall (mira «Si algo va mal»). Luego escanea el QR del panel y usa **«Añadir a pantalla de inicio»**.
- **Encendido automático:** ShortsBot arranca solo en segundo plano al encender el PC. Para quitarlo, borra
  `ShortsBot.lnk` de la carpeta de inicio (Win+R → `shell:startup`).

## Voces

En `config.json`: `"voz": "kokoro"` con `"voz_kokoro": "em_alex"` (hombre) o `"ef_dora"` (mujer); o
`"voz": "piper"` con `"voz_piper": "es_ES-davefx-medium"` o `"es_ES-sharvard-medium"` + `"voz_piper_hablante": "M"`
o `"F"` (esta última añade sola el crédito CC BY en la descripción). Todas son gratis y funcionan sin internet.

## Encender y apagar

- **Encender:** doble clic en `ShortsBot.bat`. Se queda funcionando en segundo plano y abre el panel.
- **Apagar:** doble clic en `Apagar ShortsBot.bat`.
- La primera vez Windows puede preguntar si dejas que Python use la red: marca **Redes privadas** y
  pulsa **Permitir**. Si no, el panel no se abrirá desde el móvil.

---

## Paso 1 — Grabar clips con NVIDIA (Instant Replay)

1. Abre un juego y pulsa **Alt+Z** para abrir el menú de NVIDIA.
2. Activa **Repetición instantánea** (Instant Replay).
3. En su configuración pon la duración en **1 minuto**: los clips salen más centrados en la jugada.
4. Mientras juegas, cuando pase algo bueno pulsa **Alt+F10**. Se guarda el último minuto.

El bot lo encuentra solo cuando cierras el juego.

¿Tienes un vídeo que ya habías grabado? Mételo en la carpeta `ShortsBot\entrada`.

---

## Paso 2 — Conectar tu canal de YouTube (una sola vez, unos 10 minutos)

Google obliga a crear una "app" propia para subir vídeos automáticamente. Es gratis.

1. Entra en https://console.cloud.google.com con la cuenta de Google de tu canal y crea un proyecto
   llamado `ShortsBot`.
2. Ve a **APIs y servicios → Biblioteca**, busca **YouTube Data API v3** y pulsa **Habilitar**.
3. Ve a **Google Auth Platform** (pantalla de consentimiento OAuth) y pulsa **Empezar**:
   - Nombre de la app: `ShortsBot`. Correo de asistencia: el tuyo.
   - Público: **Externo**.
   - En **Público → Usuarios de prueba**, añade tu propio correo.
   - Después pulsa **Publicar app** (pasarla a "En producción"). **Importante:** si la dejas "En prueba",
     Google corta el permiso cada 7 días y tendrías que volver a conectar.
4. Ve a **Clientes → Crear cliente**. Tipo: **Aplicación de escritorio**. Crea y pulsa **Descargar JSON**.
5. Renombra ese archivo a `client_secret.json` y ponlo dentro de la carpeta `ShortsBot`.
6. En el panel pulsa **Conectar YouTube**. Se abre el navegador:
   - Elige tu cuenta.
   - Te saldrá "Google no ha verificado esta app". Es normal, porque la app es tuya. Pulsa
     **Configuración avanzada → Ir a ShortsBot** y luego **Continuar / Permitir**.

Listo. En el panel verás el nombre de tu canal en verde.

---

## Paso 3 — Publicar en público (verificación de Google)

Google deja **bloqueados en privado** los vídeos subidos por apps que aún no ha revisado. Hasta que
revise la tuya, los Shorts se suben en privado y **no puedes hacerlos públicos**, ni desde el panel ni
desde YouTube Studio.

Para quitar el bloqueo:

1. Rellena el formulario de auditoría de la API de YouTube:
   https://support.google.com/youtube/contact/yt_api_form
2. Explica que es una herramienta personal que sube Shorts de tus propias partidas a tu propio canal,
   como mucho 2 al día.
3. Cuando lo aprueben (suele tardar unas semanas), abre `config.json`, cambia `"privacidad": "private"`
   por `"privacidad": "public"` y reinicia el bot.

Mientras tanto, todos los Shorts terminados están en la carpeta `ShortsBot\shorts` por si quieres subir
alguno a mano. En el panel, el botón 📁 te lleva al archivo.

---

## Opcional — Títulos escritos por Claude

Sin API key el bot usa títulos de plantilla ("Momento épico en Minecraft 🔥"…). Con una API key de
Anthropic, Claude mira 3 fotogramas de cada clip y escribe un título, una descripción y unas etiquetas
que encajan con lo que pasa. También **descarta los clips en los que no pasa nada o en los que se ve
información personal**.

1. Crea una API key en https://platform.claude.com (se paga por uso: unos céntimos por Short).
2. Abre PowerShell y ejecuta (cambiando la clave):
   `setx ANTHROPIC_API_KEY "sk-ant-..."`
3. Apaga y vuelve a encender ShortsBot. En el panel pondrá **Títulos: Claude**.

Usa el modelo `claude-opus-5`. Si Claude rechaza un clip, pasa a otro modelo automáticamente
(*fallbacks* del servidor) y, si aun así falla, pone un título de plantilla.

---

## Ajustes (`config.json`)

| Ajuste | Qué hace | Por defecto |
|---|---|---|
| `carpetas_vigiladas` | Carpetas donde busca clips | `Videos\NVIDIA` y `entrada` |
| `max_shorts_por_dia` | Máximo de subidas al día | `2` |
| `horas_entre_subidas` | Horas mínimas entre dos subidas | `4` |
| `horario_subida` | Franja en la que puede subir | `[12, 22]` |
| `privacidad` | `private`, `unlisted` o `public` | `private` |
| `subir_a_youtube` | `false` = solo edita, no sube | `true` |
| `duracion_short` | Duración [mín, máx] en segundos | `[15, 45]` |
| `max_shorts_por_video` | Shorts por vídeo largo (más de 4 min) | `3` |
| `pausar_mientras_juegas` | No trabaja con el juego abierto | `true` |
| `procesos_juego` | Programas que cuentan como "jugando" | Minecraft Java y Bedrock |
| `usar_claude` / `modelo_claude` | Títulos con Claude | `true` / `claude-opus-5` |

Después de cambiar algo, apaga y vuelve a encender el bot.

---

## Si algo va mal

- **El panel dice "está apagado":** doble clic en `ShortsBot.bat`.
- **El móvil no abre el panel:** Configuración → Red e Internet → Wi-Fi → tu red → **Red privada**. Después,
  en PowerShell como administrador:
  `New-NetFirewallRule -DisplayName "ShortsBot panel" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private`
- **"YouTube sin conectar" después de unos días:** no pasaste la app a "En producción" (Paso 2.3).
  Hazlo y pulsa **Conectar YouTube** otra vez.
- **Un Short en "Error":** mira el mensaje en la tarjeta y pulsa **Reintentar**.
- **Registro detallado:** `ShortsBot\datos\bot.log`.

Archivos que **no debes compartir con nadie**: `client_secret.json` y la carpeta `datos` (ahí está el
permiso de tu canal).
