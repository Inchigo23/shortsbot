"""Animador: genera con la gráfica un recorrido por un mundo de bloques original (texturas propias).

Cada vídeo tiene un paisaje, una hora del día y un recorrido distintos:
  - "vuelo":      la cámara planea bajo sobre el paisaje, como un dron (por defecto).
  - "panoramica": vuelo alto y lento, mirando el paisaje desde arriba (por defecto).
  - "parkour":    saltos de bloque en bloque (solo si un guion lo pide expresamente).
"""
import math
import os
import subprocess

import moderngl
import numpy as np

import editor

ANCHO, ALTO, FPS = 1080, 1920, 30
# En la nube (sin gráfica) se renderiza más pequeño y sin antialiasing, y ffmpeg lo amplía a 1080x1920.
ESCALA = float(os.environ.get("ANIMACION_ESCALA", "1"))
MSAA = int(os.environ.get("ANIMACION_MSAA", "4"))
RENDER_ANCHO, RENDER_ALTO = int(ANCHO * ESCALA) // 2 * 2, int(ALTO * ESCALA) // 2 * 2
MUNDO_ANCHO, MUNDO_ALTO = 192, 84
NIEBLA = {"vuelo": (45.0, 92.0), "panoramica": (60.0, 118.0), "parkour": (38.0, 74.0)}
# Vuelos: (altura sobre el terreno, velocidad en bloques/s, inclinación de la cámara en grados)
VUELOS = {"vuelo": (10, 4.6, -13), "panoramica": (24, 3.6, -27)}

# Bloques
AIRE, CESPED, TIERRA, PIEDRA, ARENA, NIEVE, TRONCO, HOJAS, AGUA, P1, P2, P3, P4, GRAVA = range(14)
# Casillas del atlas de texturas (4x4 casillas de 16 px)
T_CESPED, T_CESPED_LADO, T_TIERRA, T_PIEDRA, T_ARENA, T_NIEVE, T_NIEVE_LADO, T_TRONCO, T_TRONCO_ARRIBA, \
    T_HOJAS, T_AGUA, T_P1, T_P2, T_P3, T_P4, T_GRAVA = range(16)
# (arriba, lados, abajo) de cada bloque
CARAS = {
    CESPED: (T_CESPED, T_CESPED_LADO, T_TIERRA), TIERRA: (T_TIERRA,) * 3, PIEDRA: (T_PIEDRA,) * 3,
    ARENA: (T_ARENA,) * 3, NIEVE: (T_NIEVE, T_NIEVE_LADO, T_TIERRA), TRONCO: (T_TRONCO_ARRIBA, T_TRONCO, T_TRONCO_ARRIBA),
    HOJAS: (T_HOJAS,) * 3, AGUA: (T_AGUA,) * 3, P1: (T_P1,) * 3, P2: (T_P2,) * 3, P3: (T_P3,) * 3, P4: (T_P4,) * 3,
    GRAVA: (T_GRAVA,) * 3,
}

BIOMAS = {
    #            base, amplitud, escala, bloque de arriba, árboles por casilla
    "llanura":  (21, 9, 44, CESPED, 0.004),
    "bosque":   (22, 13, 34, CESPED, 0.028),
    "desierto": (20, 8, 52, ARENA, 0.0),
    "nieve":    (22, 15, 38, NIEVE, 0.007),
    "montaña":  (18, 36, 46, CESPED, 0.005),
}
MAR = 20

HORAS = {
    #             cielo arriba,        horizonte,          luz,                sol/luna,          nubes
    "dia":       ((0.33, 0.58, 1.00), (0.72, 0.85, 1.00), (1.00, 1.00, 1.00), (1.0, 0.97, 0.78), (1.0, 1.0, 1.0)),
    "atardecer": ((0.20, 0.24, 0.55), (1.00, 0.60, 0.40), (1.00, 0.82, 0.70), (1.0, 0.72, 0.38), (1.0, 0.78, 0.68)),
    "noche":     ((0.02, 0.03, 0.09), (0.07, 0.09, 0.19), (0.34, 0.40, 0.62), (0.9, 0.93, 1.00), (0.24, 0.26, 0.36)),
}


# ------------------------------------------------------------------ texturas

def _casilla(rng, color, variacion=0.18, niveles=5):
    ruido = rng.random((16, 16))
    ruido = np.round(ruido * (niveles - 1)) / (niveles - 1)  # aspecto pixelado
    factor = 1 + variacion * (ruido - 0.5) * 2
    return np.clip(np.array(color)[None, None, :] * factor[..., None], 0, 1)


def _borde(img, luz=0.18):
    img = img.copy()
    img[0, :] *= 1 + luz
    img[:, 0] *= 1 + luz
    img[-1, :] *= 1 - luz
    img[:, -1] *= 1 - luz
    return np.clip(img, 0, 1)


def crear_atlas(rng):
    c = {}
    tierra = (0.52, 0.36, 0.24)
    c[T_TIERRA] = _casilla(rng, tierra, 0.22)
    c[T_CESPED] = _casilla(rng, (0.38, 0.66, 0.26), 0.16)
    lado = c[T_TIERRA].copy()
    for x in range(16):  # borde de hierba irregular
        lado[: rng.integers(2, 6), x] = _casilla(rng, (0.38, 0.66, 0.26), 0.16)[0, x]
    c[T_CESPED_LADO] = lado
    c[T_PIEDRA] = _casilla(rng, (0.55, 0.55, 0.57), 0.2)
    c[T_GRAVA] = _casilla(rng, (0.50, 0.47, 0.45), 0.35, 4)
    c[T_ARENA] = _casilla(rng, (0.90, 0.84, 0.60), 0.08)
    c[T_NIEVE] = _casilla(rng, (0.95, 0.97, 1.00), 0.05)
    nieve_lado = c[T_TIERRA].copy()
    for x in range(16):
        nieve_lado[: rng.integers(3, 7), x] = (0.95, 0.97, 1.0)
    c[T_NIEVE_LADO] = nieve_lado
    tronco = np.zeros((16, 16, 3))
    for x in range(16):
        tono = 0.8 + 0.25 * ((x * 7 + rng.integers(0, 3)) % 4) / 3
        tronco[:, x] = np.array((0.42, 0.30, 0.18)) * tono
    c[T_TRONCO] = np.clip(tronco * (1 + 0.1 * (rng.random((16, 16, 1)) - 0.5)), 0, 1)
    anillos = np.hypot(*np.meshgrid(np.arange(16) - 7.5, np.arange(16) - 7.5))
    c[T_TRONCO_ARRIBA] = np.where((anillos.astype(int) % 3 == 0)[..., None], (0.50, 0.37, 0.22), (0.66, 0.52, 0.32))
    hojas = _casilla(rng, (0.20, 0.50, 0.18), 0.25)
    hojas[rng.random((16, 16)) < 0.22] *= 0.55
    c[T_HOJAS] = hojas
    c[T_AGUA] = _casilla(rng, (0.20, 0.42, 0.85), 0.1)
    colores = [(0.10, 0.80, 0.90), (0.95, 0.30, 0.65), (0.55, 0.90, 0.20), (1.00, 0.60, 0.10),
               (0.60, 0.45, 1.00), (1.00, 0.85, 0.15)]
    rng.shuffle(colores)
    for i, t in enumerate((T_P1, T_P2, T_P3, T_P4)):
        c[t] = _borde(_casilla(rng, colores[i], 0.06, 3))
    atlas = np.zeros((64, 64, 3))
    for t, img in c.items():
        fy, fx = divmod(t, 4)
        atlas[fy * 16:(fy + 1) * 16, fx * 16:(fx + 1) * 16] = img
    return (atlas * 255).astype(np.uint8)


# ------------------------------------------------------------------ mundo

def _ruido(ancho, largo, escala, rng):
    gx, gz = int(ancho / escala) + 3, int(largo / escala) + 3
    rejilla = rng.random((gx, gz))
    x, z = np.arange(ancho) / escala, np.arange(largo) / escala
    x0, z0 = x.astype(int), z.astype(int)
    fx, fz = x - x0, z - z0
    sx, sz = (fx * fx * (3 - 2 * fx))[:, None], (fz * fz * (3 - 2 * fz))[None, :]
    v00, v10 = rejilla[np.ix_(x0, z0)], rejilla[np.ix_(x0 + 1, z0)]
    v01, v11 = rejilla[np.ix_(x0, z0 + 1)], rejilla[np.ix_(x0 + 1, z0 + 1)]
    return (v00 * (1 - sx) + v10 * sx) * (1 - sz) + (v01 * (1 - sx) + v11 * sx) * sz


def _fbm(ancho, largo, escala, rng, octavas=4):
    total, amp, norma = 0, 1.0, 0
    for i in range(octavas):
        total = total + amp * _ruido(ancho, largo, escala / 2 ** i, rng)
        norma += amp
        amp *= 0.5
    return total / norma


def crear_mundo(rng, bioma, largo):
    base, amp, escala, arriba, arboles = BIOMAS[bioma]
    W, H = MUNDO_ANCHO, MUNDO_ALTO
    alturas = (base + amp * (_fbm(W, largo, escala, rng) - 0.35) * 1.6).astype(int)
    alturas = np.clip(alturas, 4, H - 20)

    tapa = np.full((W, largo), arriba, np.uint8)
    if bioma == "montaña":
        tapa[alturas > 36] = PIEDRA
        tapa[alturas > 46] = NIEVE
    tapa[(alturas <= MAR + 1) & (tapa == CESPED)] = ARENA
    tapa[(alturas < MAR - 2) & (tapa == ARENA)] = GRAVA
    relleno = np.where(tapa == ARENA, ARENA, TIERRA).astype(np.uint8)

    y = np.arange(H)[None, :, None]
    h = alturas[:, None, :]
    vox = np.where(y < h - 4, PIEDRA, np.where(y < h - 1, relleno[:, None, :], np.where(y < h, tapa[:, None, :], AIRE)))
    vox = np.where((y >= h) & (y < MAR), AGUA, vox).astype(np.uint8)

    # Árboles
    candidatos = np.argwhere((rng.random((W, largo)) < arboles) & ((tapa == CESPED) | (tapa == NIEVE)) & (alturas > MAR + 1))
    for x, z in candidatos:
        if not (3 <= x < W - 3 and 3 <= z < largo - 3):
            continue
        suelo, alto = alturas[x, z], rng.integers(4, 7)
        if suelo + alto + 3 >= H:
            continue
        copa = vox[x - 2:x + 3, suelo + alto - 2:suelo + alto, z - 2:z + 3]
        copa[copa == AIRE] = HOJAS
        cima = vox[x - 1:x + 2, suelo + alto:suelo + alto + 2, z - 1:z + 2]
        cima[cima == AIRE] = HOJAS
        vox[x, suelo:suelo + alto, z] = TRONCO
    return vox, alturas


# ------------------------------------------------------------------ malla

# Esquinas (x,y,z) y coordenadas de textura de cada cara; sombra estilo "bloques"
_CARAS = [
    # dirección, esquinas, uv, sombra, índice de textura (0 arriba, 1 lado, 2 abajo)
    ((0, 1, 0), [(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)], [(0, 0), (1, 0), (1, 1), (0, 1)], 1.00, 0),
    ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], [(0, 0), (1, 0), (1, 1), (0, 1)], 0.50, 2),
    ((1, 0, 0), [(1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0)], [(0, 1), (1, 1), (1, 0), (0, 0)], 0.80, 1),
    ((-1, 0, 0), [(0, 0, 1), (0, 0, 0), (0, 1, 0), (0, 1, 1)], [(0, 1), (1, 1), (1, 0), (0, 0)], 0.80, 1),
    ((0, 0, 1), [(1, 0, 1), (0, 0, 1), (0, 1, 1), (1, 1, 1)], [(0, 1), (1, 1), (1, 0), (0, 0)], 0.64, 1),
    ((0, 0, -1), [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 1), (1, 1), (1, 0), (0, 0)], 0.64, 1),
]


def _vecino(solido, d):
    """solido desplazado: valor del vecino en la dirección d (fuera del mundo = sólido, así no se ven los bordes)."""
    v = np.ones_like(solido)
    dx, dy, dz = d
    sx = slice(max(dx, 0), solido.shape[0] + min(dx, 0))
    sy = slice(max(dy, 0), solido.shape[1] + min(dy, 0))
    sz = slice(max(dz, 0), solido.shape[2] + min(dz, 0))
    tx = slice(max(-dx, 0), solido.shape[0] + min(-dx, 0))
    ty = slice(max(-dy, 0), solido.shape[1] + min(-dy, 0))
    tz = slice(max(-dz, 0), solido.shape[2] + min(-dz, 0))
    v[tx, ty, tz] = solido[sx, sy, sz]
    if dy == 1:
        v[:, -1, :] = False  # por encima del mundo hay cielo
    return v


def _tabla_texturas():
    tabla = np.zeros((16, 3), np.int32)
    for b, t in CARAS.items():
        tabla[b] = t
    return tabla


def crear_malla(vox):
    tabla = _tabla_texturas()
    solido = (vox != AIRE) & (vox != AGUA)
    partes = []
    e = 0.002
    for d, esquinas, uvs, sombra, cual in _CARAS:
        visibles = solido & ~_vecino(solido, d)
        pos = np.argwhere(visibles).astype(np.float32)
        if not len(pos):
            continue
        casilla = tabla[vox[visibles], cual]
        cx, cy = (casilla % 4).astype(np.float32), (casilla // 4).astype(np.float32)
        quad = []
        for (ox, oy, oz), (lu, lv) in zip(esquinas, uvs):
            u = (cx + e + lu * (1 - 2 * e)) / 4
            v = (cy + e + lv * (1 - 2 * e)) / 4
            quad.append(np.column_stack([pos[:, 0] + ox, pos[:, 1] + oy, pos[:, 2] + oz, u, v,
                                         np.full(len(pos), sombra, np.float32)]))
        partes.append(np.stack([quad[i] for i in (0, 1, 2, 0, 2, 3)], axis=1).reshape(-1, 6))
    # Agua: solo la superficie, un poco por debajo del borde
    agua = (vox == AGUA) & ~_vecino(vox != AIRE, (0, 1, 0))
    pos = np.argwhere(agua).astype(np.float32)
    cx, cy = T_AGUA % 4, T_AGUA // 4
    quad = [np.column_stack([pos[:, 0] + ox, pos[:, 1] + 0.88, pos[:, 2] + oz,
                             np.full(len(pos), (cx + e + lu * (1 - 2 * e)) / 4, np.float32),
                             np.full(len(pos), (cy + e + lv * (1 - 2 * e)) / 4, np.float32),
                             np.ones(len(pos), np.float32)])
            for (ox, _, oz), (lu, lv) in zip(_CARAS[0][1], _CARAS[0][2])]
    malla_agua = np.stack([quad[i] for i in (0, 1, 2, 0, 2, 3)], axis=1).reshape(-1, 6) if len(pos) else None
    return np.concatenate(partes).astype(np.float32), malla_agua


# ------------------------------------------------------------------ recorridos

def _curso_parkour(rng, vox, alturas, duracion):
    W, H = MUNDO_ANCHO, MUNDO_ALTO
    centro = W // 2
    # El circuito va por encima de lo más alto del pasillo (árboles incluidos) para que nada tape la vista
    pasillo = ((vox != AIRE) & (vox != AGUA))[centro - 22:centro + 22]
    lo_mas_alto = int(np.flatnonzero(pasillo.any(axis=(0, 2))).max())
    y0 = int(min(H - 12, lo_mas_alto + 6))
    x, y, z = centro, y0, 6
    plataformas = [(x, y, z)]
    tiempo, color = 0.0, 0
    tipos = [P1, P2, P3, P4]
    while tiempo < duracion + 2:
        dz = int(rng.integers(2, 5))
        dx = int(rng.integers(-2, 3)) if dz < 4 else int(rng.integers(-1, 2))
        dy = int(rng.choice([-1, 0, 0, 1])) if dz <= 3 else int(rng.choice([-1, 0]))
        x = int(np.clip(x + dx, centro - 18, centro + 18))
        y = int(np.clip(y + dy, y0 - 5, H - 8))
        z += dz
        plataformas.append((x, y, z))
        tiempo += 0.42 + 0.09 * math.hypot(dx, dz) + 0.12
    for i, (px, py, pz) in enumerate(plataformas):
        bloque = tipos[(i // 7) % 4]
        if i % 9 == 0:  # descansillos de 3x3 de vez en cuando
            vox[px - 1:px + 2, py, pz - 1:pz + 2] = bloque
        else:
            vox[px, py, pz] = bloque
    return plataformas


def _camara_parkour(plataformas, n_frames):
    """Posición y dirección de la cámara en cada frame: saltos en parábola de bloque en bloque."""
    tramos, t = [], 0.0
    for a, b in zip(plataformas, plataformas[1:]):
        dist = math.hypot(b[0] - a[0], b[2] - a[2])
        salto = 0.42 + 0.09 * dist
        tramos.append((t, t + salto, a, b))
        t += salto + 0.12
    camaras, yaw_suave = [], None
    for f in range(n_frames):
        tf = f / FPS
        i = next((k for k, tr in enumerate(tramos) if tf < tr[1] + 0.12), len(tramos) - 1)
        t0, t1, a, b = tramos[i]
        s = float(np.clip((tf - t0) / (t1 - t0), 0, 1))
        pa = np.array([a[0] + 0.5, a[1] + 1.0, a[2] + 0.5])
        pb = np.array([b[0] + 0.5, b[1] + 1.0, b[2] + 0.5])
        pos = pa + (pb - pa) * s
        pos[1] = pa[1] + (pb[1] - pa[1]) * s + (1.25 + max(0.0, pb[1] - pa[1]) * 0.35) * 4 * s * (1 - s) + 1.62
        # mira hacia el bloque siguiente al de destino
        c = tramos[min(i + 1, len(tramos) - 1)][3]
        objetivo = np.array([c[0] + 0.5, c[1] + 1.0, c[2] + 0.5])
        yaw = math.atan2(objetivo[0] - pos[0], objetivo[2] - pos[2])
        yaw_suave = yaw if yaw_suave is None else yaw_suave + (yaw - yaw_suave) * 0.12
        camaras.append((pos, yaw_suave, math.radians(-30 + 3 * math.sin(tf * 2.1))))
    return camaras


def _camara_vuelo(rng, alturas, n_frames, modo):
    """Vuelo suave: curvas amplias, sin tirones, y la altura se adapta al terreno poco a poco."""
    W = MUNDO_ANCHO
    sobre_suelo, velocidad, inclinacion = VUELOS[modo]
    fase1, fase2 = rng.random() * 6, rng.random() * 6
    t = np.arange(n_frames) / FPS
    z = 8 + velocidad * t
    x = W / 2 + 14 * np.sin(t * 0.13 + fase1) + 3 * np.sin(t * 0.31 + fase2)
    delante = np.clip((z + 12).astype(int), 0, alturas.shape[1] - 1)
    xs = np.clip(x.astype(int), 8, W - 9)
    suelo = np.array([alturas[xx - 8:xx + 9, max(0, zz - 8):zz + 9].max() for xx, zz in zip(xs, delante)], float)
    suelo = np.maximum(suelo, MAR) + 7  # margen por los árboles
    k = FPS * 3
    y = np.convolve(np.pad(suelo, (k, k), mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), mode="valid") + sobre_suelo - 7
    yaw = np.arctan2(np.gradient(x) * FPS, velocidad)
    # la cámara sube y baja la mirada muy despacio, como un dron con piloto
    pitch = np.radians(inclinacion + 2.5 * np.sin(t * 0.21 + fase2))
    return [(np.array([x[i], y[i], z[i]]), float(yaw[i]), float(pitch[i])) for i in range(n_frames)]


# ------------------------------------------------------------------ render

VS_MUNDO = """
#version 330
uniform mat4 mvp;
in vec3 in_pos; in vec2 in_uv; in float in_sombra;
out vec2 uv; out float sombra; out vec3 wpos;
void main() { gl_Position = mvp * vec4(in_pos, 1.0); uv = in_uv; sombra = in_sombra; wpos = in_pos; }
"""
FS_MUNDO = """
#version 330
uniform sampler2D tex; uniform vec3 cam; uniform vec3 niebla_color; uniform vec2 niebla;
uniform vec3 luz; uniform float alfa;
in vec2 uv; in float sombra; in vec3 wpos; out vec4 color;
void main() {
    vec3 c = texture(tex, uv).rgb * sombra * luz;
    float f = clamp((length(wpos - cam) - niebla.x) / (niebla.y - niebla.x), 0.0, 1.0);
    color = vec4(mix(c, niebla_color, f), alfa);
}
"""
VS_CIELO = """
#version 330
in vec2 in_pos; out vec2 ndc;
void main() { ndc = in_pos; gl_Position = vec4(in_pos, 0.9999, 1.0); }
"""
FS_CIELO = """
#version 330
uniform mat4 inv_vp; uniform vec3 cam; uniform vec3 arriba_c; uniform vec3 horizonte_c;
uniform vec3 sol_dir; uniform vec3 sol_c; uniform vec3 nubes_c; uniform float noche; uniform float t;
in vec2 ndc; out vec4 color;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void main() {
    vec4 p = inv_vp * vec4(ndc, 1.0, 1.0);
    vec3 dir = normalize(p.xyz / p.w - cam);
    vec3 c = mix(horizonte_c, arriba_c, clamp(dir.y * 1.8 + 0.05, 0.0, 1.0));
    vec3 s = normalize(sol_dir);
    vec3 der = normalize(cross(vec3(0.0, 1.0, 0.0), s)); vec3 arr = cross(s, der);
    float ds = dot(dir, s);
    if (ds > 0.0) {
        vec2 q = vec2(dot(dir, der), dot(dir, arr)) / ds;
        float m = max(abs(q.x), abs(q.y));
        if (m < 0.06) c = sol_c; else if (m < 0.1) c = mix(c, sol_c, 0.3);
    }
    if (noche > 0.5 && dir.y > 0.03) {
        vec2 g = floor(dir.xz / (dir.y + 0.35) * 260.0);
        if (hash(g) > 0.995) c += vec3(0.75);
    }
    if (dir.y > 0.01) {
        float tt = (118.0 - cam.y) / dir.y;
        vec2 pc = cam.xz + dir.xz * tt + vec2(t * 1.2, 0.0);
        if (hash(floor(pc / 9.0)) > 0.7) c = mix(c, nubes_c, 0.88 * clamp(1.0 - tt / 520.0, 0.0, 1.0));
    }
    color = vec4(c, 1.0);
}
"""


def _perspectiva(fovy, aspecto, cerca, lejos):
    f = 1 / math.tan(math.radians(fovy) / 2)
    return np.array([[f / aspecto, 0, 0, 0], [0, f, 0, 0],
                     [0, 0, (lejos + cerca) / (cerca - lejos), 2 * lejos * cerca / (cerca - lejos)],
                     [0, 0, -1, 0]], np.float32)


def _mirar(ojo, yaw, pitch):
    delante = np.array([math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch)])
    der = np.cross(delante, (0, 1, 0))
    der /= np.linalg.norm(der)
    arr = np.cross(der, delante)
    m = np.eye(4, dtype=np.float32)
    m[0, :3], m[1, :3], m[2, :3] = der, arr, -delante
    m[:3, 3] = -m[:3, :3] @ ojo
    return m


def elegir_escena(rng, pedida=None):
    pedida = pedida or {}
    bioma = pedida.get("bioma") if pedida.get("bioma") in BIOMAS else rng.choice(list(BIOMAS))
    hora = pedida.get("hora") if pedida.get("hora") in HORAS else rng.choice(["dia", "dia", "atardecer", "noche"])
    modo = pedida.get("modo") if pedida.get("modo") in ("parkour", "vuelo", "panoramica") else rng.choice(["vuelo", "panoramica"])
    return {"bioma": str(bioma), "hora": str(hora), "modo": str(modo)}


def renderizar(duracion, salida, escena, semilla, encoder="libx264", progreso=None):
    """Graba un vídeo vertical sin sonido de `duracion` segundos con la escena pedida."""
    rng = np.random.default_rng(semilla)
    n_frames = int(math.ceil(duracion * FPS))
    modo = escena["modo"]
    niebla = NIEBLA[modo]
    velocidad_z = 5.5 if modo == "parkour" else VUELOS[modo][1]
    largo = int(duracion * velocidad_z + niebla[1] + 40)
    vox, alturas = crear_mundo(rng, escena["bioma"], largo)
    if modo == "parkour":
        camaras = _camara_parkour(_curso_parkour(rng, vox, alturas, duracion), n_frames)
    else:
        camaras = _camara_vuelo(rng, alturas, n_frames, modo)
    malla, malla_agua = crear_malla(vox)
    arriba_c, horizonte_c, luz, sol_c, nubes_c = HORAS[escena["hora"]]

    ctx = moderngl.create_standalone_context(require=330)
    try:
        atlas = ctx.texture((64, 64), 3, crear_atlas(rng).tobytes())
        atlas.filter = (moderngl.NEAREST, moderngl.NEAREST)
        prog = ctx.program(vertex_shader=VS_MUNDO, fragment_shader=FS_MUNDO)
        cielo = ctx.program(vertex_shader=VS_CIELO, fragment_shader=FS_CIELO)
        vao = ctx.vertex_array(prog, [(ctx.buffer(malla.tobytes()), "3f 2f 1f", "in_pos", "in_uv", "in_sombra")])
        vao_agua = (ctx.vertex_array(prog, [(ctx.buffer(malla_agua.tobytes()), "3f 2f 1f", "in_pos", "in_uv", "in_sombra")])
                    if malla_agua is not None else None)
        tri = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], np.float32).tobytes())
        vao_cielo = ctx.vertex_array(cielo, [(tri, "2f", "in_pos")])

        tam = (RENDER_ANCHO, RENDER_ALTO)
        muestras = MSAA if ctx.max_samples >= MSAA else 0
        fbo_ms = ctx.framebuffer(color_attachments=[ctx.renderbuffer(tam, samples=muestras)],
                                 depth_attachment=ctx.depth_renderbuffer(tam, samples=muestras))
        fbo = ctx.simple_framebuffer(tam)

        prog["niebla_color"].value = horizonte_c
        prog["niebla"].value = niebla
        prog["luz"].value = luz
        cielo["arriba_c"].value = arriba_c
        cielo["horizonte_c"].value = horizonte_c
        cielo["sol_c"].value = sol_c
        cielo["nubes_c"].value = nubes_c
        cielo["noche"].value = 1.0 if escena["hora"] == "noche" else 0.0
        altura_sol = {"dia": 0.55, "atardecer": 0.12, "noche": 0.45}[escena["hora"]]
        cielo["sol_dir"].value = (0.45, altura_sol, 1.0)
        proy = _perspectiva(78, ANCHO / ALTO, 0.08, 400)

        if encoder == "h264_nvenc":
            codec = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "19", "-b:v", "0"]
        else:
            codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
        ffmpeg = subprocess.Popen(
            [editor.FFMPEG, "-hide_banner", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{RENDER_ANCHO}x{RENDER_ALTO}", "-r", str(FPS), "-i", "-",
             "-vf", "vflip" if ESCALA == 1 else f"vflip,scale={ANCHO}:{ALTO}:flags=lanczos", *codec, "-pix_fmt", "yuv420p",
             str(salida)],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=editor.SIN_VENTANA)

        for f, (pos, yaw, pitch) in enumerate(camaras):
            vista = _mirar(pos, yaw, pitch)
            vp = proy @ vista
            fbo_ms.use()
            ctx.clear(*horizonte_c)
            ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
            cielo["inv_vp"].write(np.linalg.inv(vp).T.astype(np.float32).tobytes())
            cielo["cam"].value = tuple(pos)
            cielo["t"].value = f / FPS
            vao_cielo.render(moderngl.TRIANGLES)
            ctx.enable(moderngl.DEPTH_TEST)
            prog["mvp"].write(vp.T.astype(np.float32).tobytes())
            prog["cam"].value = tuple(pos)
            prog["alfa"].value = 1.0
            atlas.use(0)
            vao.render(moderngl.TRIANGLES)
            if vao_agua:
                ctx.enable(moderngl.BLEND)
                ctx.depth_mask = False
                prog["alfa"].value = 0.72
                vao_agua.render(moderngl.TRIANGLES)
                ctx.depth_mask = True
                ctx.disable(moderngl.BLEND)
            ctx.copy_framebuffer(fbo, fbo_ms)
            ffmpeg.stdin.write(fbo.read(components=3, alignment=1))
            if progreso and f % 15 == 0:
                progreso(f / n_frames * 100)
        ffmpeg.stdin.close()
        error = ffmpeg.stderr.read().decode("utf-8", "replace")
        if ffmpeg.wait() != 0:
            raise RuntimeError(f"ffmpeg falló al grabar la animación: {error[-300:]}")
    finally:
        ctx.release()
