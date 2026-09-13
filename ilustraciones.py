"""Ilustraciones propias en pixel art para acompañar cada frase del guion.

Todas son diseños originales dibujados aquí (objetos genéricos: un ojo, una calabaza, una gota...). No se dibuja
ningún personaje ni textura de Minecraft. Cada icono se pinta en una cuadrícula de 32x32 sin suavizado y se
amplía con «vecino más cercano», que es lo que le da el aspecto pixelado.
"""
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

LADO = 32
ESCALA = 14                       # 32 px -> 448 px en el vídeo
BORDE = (14, 16, 30, 255)

# Paleta
BLANCO, NEGRO, GRIS, GRIS_O = (245, 247, 255), (22, 22, 30), (150, 156, 170), (95, 100, 115)
ROJO, ROJO_O = (235, 64, 64), (160, 30, 40)
NARANJA, NARANJA_O, AMARILLO, ORO = (244, 140, 36), (190, 90, 20), (255, 214, 60), (230, 170, 30)
VERDE, VERDE_O, CIAN, AZUL, AZUL_O = (80, 200, 90), (40, 130, 60), (90, 230, 240), (60, 140, 240), (30, 80, 180)
MORADO, MORADO_C, ROSA, ROSA_O = (140, 70, 220), (200, 150, 255), (250, 160, 185), (215, 105, 140)
MARRON, MARRON_O, CREMA = (150, 95, 50), (100, 60, 30), (250, 235, 200)


def _lienzo():
    img = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


# ---------------------------------------------------------------- iconos

def ojo(d):
    d.ellipse([3, 9, 28, 23], fill=BLANCO)
    d.ellipse([11, 10, 21, 22], fill=VERDE)
    d.ellipse([13, 12, 19, 20], fill=NEGRO)
    d.rectangle([14, 13, 15, 14], fill=BLANCO)


def _tachar(d):
    d.ellipse([2, 2, 29, 29], outline=ROJO, width=3)
    d.line([7, 7, 24, 24], fill=ROJO, width=3)


def ojo_prohibido(d):
    ojo(d)
    _tachar(d)


def calabaza(d):
    d.ellipse([4, 8, 27, 29], fill=NARANJA)
    for x in (10, 15, 20):
        d.line([x, 10, x, 27], fill=NARANJA_O)
    d.rectangle([14, 3, 17, 8], fill=VERDE_O)
    d.polygon([(17, 4), (24, 2), (21, 7)], fill=VERDE)
    d.polygon([(8, 14), (13, 14), (10, 18)], fill=AMARILLO)         # cara tallada original
    d.polygon([(18, 14), (23, 14), (21, 18)], fill=AMARILLO)
    d.polygon([(8, 21), (11, 24), (14, 21), (17, 24), (20, 21), (23, 24), (21, 26), (10, 26)], fill=AMARILLO)


def agua(d):
    d.polygon([(16, 3), (25, 17), (7, 17)], fill=AZUL)
    d.ellipse([7, 11, 25, 29], fill=AZUL)
    d.ellipse([10, 15, 14, 21], fill=CIAN)


def olas(d):
    for y, c in ((8, CIAN), (15, AZUL), (22, AZUL_O)):
        for x in range(2, 30, 8):
            d.arc([x, y, x + 8, y + 8], 180, 360, fill=c, width=3)


def flecha(d):
    d.line([7, 25, 23, 9], fill=MARRON, width=2)
    d.polygon([(19, 6), (27, 5), (26, 13)], fill=GRIS)
    d.polygon([(4, 23), (9, 23), (9, 28)], fill=BLANCO)
    d.polygon([(8, 27), (8, 22), (3, 22)], fill=BLANCO)


def escudo(d):
    d.polygon([(6, 5), (26, 5), (26, 16), (16, 28), (6, 16)], fill=GRIS)
    d.polygon([(9, 8), (23, 8), (23, 16), (16, 24), (9, 16)], fill=MARRON)
    d.line([16, 8, 16, 24], fill=MARRON_O, width=2)


def espada(d):
    d.polygon([(24, 3), (28, 4), (13, 20), (11, 18)], fill=GRIS)
    d.line([25, 5, 13, 17], fill=BLANCO)
    d.line([8, 16, 15, 23], fill=ORO, width=3)
    d.line([11, 21, 5, 27], fill=MARRON, width=3)


def pico(d):
    d.arc([4, 3, 28, 21], 200, 340, fill=GRIS, width=4)
    d.line([16, 7, 16, 29], fill=MARRON, width=3)


def diamante(d):
    d.polygon([(9, 6), (23, 6), (29, 13), (16, 29), (3, 13)], fill=CIAN)
    d.polygon([(9, 6), (23, 6), (29, 13), (3, 13)], fill=(170, 250, 255))
    d.line([3, 13, 29, 13], fill=AZUL)
    d.line([16, 13, 16, 28], fill=AZUL)


def gema_verde(d):
    d.polygon([(16, 3), (26, 10), (26, 22), (16, 29), (6, 22), (6, 10)], fill=VERDE)
    d.polygon([(16, 7), (22, 11), (22, 21), (16, 25), (10, 21), (10, 11)], fill=(150, 240, 150))


def oro(d):
    d.polygon([(4, 22), (9, 12), (27, 12), (28, 22)], fill=ORO)
    d.polygon([(9, 12), (27, 12), (25, 16), (11, 16)], fill=AMARILLO)


def cofre(d):
    d.rectangle([4, 9, 27, 27], fill=MARRON)
    d.rectangle([4, 9, 27, 15], fill=MARRON_O)
    d.rectangle([4, 15, 27, 16], fill=NEGRO)
    d.rectangle([14, 13, 17, 19], fill=ORO)


def reloj(d):
    d.ellipse([3, 3, 28, 28], fill=ORO)
    d.ellipse([6, 6, 25, 25], fill=CREMA)
    d.line([16, 16, 16, 9], fill=NEGRO, width=2)
    d.line([16, 16, 21, 19], fill=NEGRO, width=2)


def sol(d):
    for i in range(8):
        x = (0, 1, 1, 1, 0, -1, -1, -1)[i]
        y = (-1, -1, 0, 1, 1, 1, 0, -1)[i]
        d.line([16 + x * 9, 16 + y * 9, 16 + x * 14, 16 + y * 14], fill=AMARILLO, width=3)
    d.ellipse([8, 8, 24, 24], fill=AMARILLO)
    d.ellipse([11, 11, 21, 21], fill=(255, 240, 150))


def luna(d):
    d.ellipse([5, 4, 27, 26], fill=CREMA)
    d.ellipse([11, 1, 31, 22], fill=(0, 0, 0, 0))
    for x, y in ((24, 22), (27, 8), (19, 28)):
        d.rectangle([x, y, x + 1, y + 1], fill=AMARILLO)


def rayo(d):
    d.polygon([(19, 2), (7, 18), (15, 18), (11, 30), (25, 12), (17, 12), (22, 2)], fill=AMARILLO)
    d.line([19, 3, 10, 16], fill=(255, 250, 200))


def explosion(d):
    puntas = [(16, 1), (19, 10), (29, 7), (22, 15), (31, 20), (21, 20), (23, 30), (16, 22), (9, 30), (11, 20),
              (1, 20), (10, 15), (3, 7), (13, 10)]
    d.polygon(puntas, fill=NARANJA)
    d.polygon([(16, 7), (18, 12), (24, 12), (19, 16), (21, 23), (16, 19), (11, 23), (13, 16), (8, 12), (14, 12)],
              fill=AMARILLO)


def fuego(d):
    d.polygon([(16, 2), (26, 16), (25, 26), (16, 30), (7, 26), (6, 16), (11, 10), (13, 16)], fill=NARANJA)
    d.polygon([(16, 12), (21, 20), (20, 26), (16, 28), (12, 26), (11, 20)], fill=AMARILLO)


def corazon(d):
    d.ellipse([3, 6, 17, 19], fill=ROJO)
    d.ellipse([15, 6, 29, 19], fill=ROJO)
    d.polygon([(4, 15), (28, 15), (16, 29)], fill=ROJO)
    d.rectangle([7, 9, 9, 11], fill=(255, 170, 170))


def calavera(d):
    d.ellipse([5, 3, 27, 23], fill=BLANCO)
    d.rectangle([10, 20, 22, 28], fill=BLANCO)
    d.ellipse([9, 10, 14, 16], fill=NEGRO)
    d.ellipse([18, 10, 23, 16], fill=NEGRO)
    d.polygon([(16, 17), (14, 20), (18, 20)], fill=NEGRO)
    for x in (12, 16, 20):
        d.line([x, 24, x, 28], fill=GRIS)


def cerdo(d):
    d.polygon([(6, 6), (11, 8), (8, 12)], fill=ROSA_O)
    d.polygon([(26, 6), (21, 8), (24, 12)], fill=ROSA_O)
    d.ellipse([4, 7, 28, 29], fill=ROSA)
    d.ellipse([10, 17, 22, 26], fill=ROSA_O)
    d.rectangle([13, 20, 14, 22], fill=MARRON_O)
    d.rectangle([18, 20, 19, 22], fill=MARRON_O)
    d.rectangle([10, 13, 11, 14], fill=NEGRO)
    d.rectangle([21, 13, 22, 14], fill=NEGRO)


def oveja(d, lana=BLANCO):
    for x, y in ((6, 6), (14, 3), (22, 6), (4, 14), (24, 14), (8, 20), (20, 20)):
        d.ellipse([x - 2, y, x + 8, y + 10], fill=lana)
    d.ellipse([9, 10, 23, 26], fill=(235, 215, 200))
    d.rectangle([12, 15, 13, 16], fill=NEGRO)
    d.rectangle([19, 15, 20, 16], fill=NEGRO)
    d.rectangle([15, 21, 17, 22], fill=ROSA_O)


def oveja_arcoiris(d):
    for i, c in enumerate((ROJO, NARANJA, AMARILLO, VERDE, AZUL, MORADO, ROSA)):
        x, y = ((6, 6), (14, 3), (22, 6), (4, 14), (24, 14), (8, 20), (20, 20))[i]
        d.ellipse([x - 2, y, x + 8, y + 10], fill=c)
    d.ellipse([9, 10, 23, 26], fill=(235, 215, 200))
    d.rectangle([12, 15, 13, 16], fill=NEGRO)
    d.rectangle([19, 15, 20, 16], fill=NEGRO)


def conejo(d):
    d.ellipse([9, 1, 14, 15], fill=CREMA)
    d.ellipse([18, 1, 23, 15], fill=CREMA)
    d.ellipse([10, 3, 12, 12], fill=ROSA)
    d.ellipse([20, 3, 22, 12], fill=ROSA)
    d.ellipse([6, 11, 26, 29], fill=CREMA)
    d.rectangle([11, 17, 12, 18], fill=NEGRO)
    d.rectangle([20, 17, 21, 18], fill=NEGRO)
    d.polygon([(15, 21), (17, 21), (16, 23)], fill=ROSA_O)


def etiqueta(d):
    d.polygon([(4, 16), (11, 7), (28, 7), (28, 25), (11, 25)], fill=CREMA)
    d.ellipse([9, 14, 13, 18], fill=MARRON_O)
    d.line([14, 12, 25, 12], fill=GRIS_O)
    d.line([14, 16, 25, 16], fill=GRIS_O)
    d.line([14, 20, 22, 20], fill=GRIS_O)
    d.line([1, 10, 10, 16], fill=MARRON)


def libro(d):
    d.rectangle([6, 4, 26, 28], fill=MORADO)
    d.rectangle([8, 26, 26, 28], fill=CREMA)
    d.rectangle([6, 4, 9, 28], fill=(90, 40, 160))
    d.rectangle([13, 9, 22, 12], fill=ORO)


def mapa(d):
    d.polygon([(3, 7), (12, 4), (20, 7), (29, 4), (29, 25), (20, 28), (12, 25), (3, 28)], fill=CREMA)
    d.line([12, 4, 12, 25], fill=(210, 190, 150))
    d.line([20, 7, 20, 28], fill=(210, 190, 150))
    d.line([6, 20, 11, 15, 16, 18, 22, 11], fill=ROJO)
    d.line([22, 9, 26, 13], fill=ROJO, width=2)
    d.line([26, 9, 22, 13], fill=ROJO, width=2)


def brujula(d):
    d.ellipse([3, 3, 28, 28], fill=GRIS)
    d.ellipse([6, 6, 25, 25], fill=CREMA)
    d.polygon([(16, 7), (19, 16), (13, 16)], fill=ROJO)
    d.polygon([(16, 25), (19, 16), (13, 16)], fill=GRIS_O)


def casa(d):
    d.polygon([(2, 15), (16, 3), (30, 15)], fill=ROJO_O)
    d.rectangle([6, 15, 26, 29], fill=CREMA)
    d.rectangle([13, 20, 19, 29], fill=MARRON)
    d.rectangle([8, 18, 11, 21], fill=CIAN)


def arbol(d):
    d.rectangle([14, 18, 18, 30], fill=MARRON)
    d.ellipse([4, 3, 28, 22], fill=VERDE)
    d.ellipse([8, 5, 16, 13], fill=(130, 225, 130))


def bloque(d):
    d.polygon([(16, 3), (29, 10), (16, 17), (3, 10)], fill=VERDE)
    d.polygon([(3, 10), (16, 17), (16, 30), (3, 23)], fill=MARRON)
    d.polygon([(29, 10), (16, 17), (16, 30), (29, 23)], fill=MARRON_O)


def portal(d):
    for r, c in ((14, MORADO), (10, MORADO_C), (6, MORADO), (2, (255, 255, 255))):
        d.ellipse([16 - r, 16 - r, 16 + r, 16 + r], outline=c, width=2)


def teletransporte(d):
    for x, y, t in ((6, 8, 3), (24, 6, 2), (14, 14, 4), (26, 20, 3), (8, 24, 2), (18, 26, 3), (4, 16, 2)):
        d.rectangle([x, y, x + t, y + t], fill=MORADO_C if t > 2 else MORADO)


def estrella(d):
    d.polygon([(16, 2), (20, 12), (30, 12), (22, 19), (25, 29), (16, 23), (7, 29), (10, 19), (2, 12), (12, 12)],
              fill=AMARILLO)


def cama(d):
    d.rectangle([3, 16, 29, 24], fill=ROJO)
    d.rectangle([3, 13, 11, 19], fill=BLANCO)
    d.rectangle([3, 24, 5, 28], fill=MARRON)
    d.rectangle([27, 24, 29, 28], fill=MARRON)


def manzana(d):
    d.ellipse([5, 8, 27, 29], fill=ROJO)
    d.line([16, 9, 17, 3], fill=MARRON, width=2)
    d.polygon([(17, 5), (24, 3), (21, 8)], fill=VERDE)
    d.ellipse([9, 12, 12, 16], fill=(255, 150, 150))


def huevo(d):
    d.ellipse([8, 4, 24, 29], fill=CREMA)
    d.ellipse([11, 8, 14, 13], fill=BLANCO)


def dinamita(d):
    for x in (6, 13, 20):
        d.rectangle([x, 10, x + 6, 28], fill=ROJO)
        d.rectangle([x, 10, x + 1, 28], fill=ROJO_O)
    d.rectangle([5, 17, 27, 20], fill=MARRON_O)
    d.line([16, 10, 19, 3], fill=GRIS_O, width=2)
    d.rectangle([19, 1, 21, 3], fill=AMARILLO)


def check(d):
    d.line([5, 17, 13, 25, 27, 7], fill=VERDE, width=5)


def cruz(d):
    d.line([6, 6, 26, 26], fill=ROJO, width=5)
    d.line([26, 6, 6, 26], fill=ROJO, width=5)


def _signo(d, texto, color):
    fuente = ImageFont.truetype(str(Path(__file__).resolve().parent / "fuentes" / "Anton-Regular.ttf"), 28)
    d.fontmode = "1"
    d.text((16, 16), texto, font=fuente, fill=color, anchor="mm")


def interrogacion(d):
    _signo(d, "?", AMARILLO)


def exclamacion(d):
    _signo(d, "!", ROJO)


def _numero(d, n):
    d.ellipse([2, 2, 29, 29], fill=AZUL)
    d.ellipse([4, 4, 27, 27], fill=AZUL_O)
    _signo(d, str(n), BLANCO)


def uno(d):
    _numero(d, 1)


def dos(d):
    _numero(d, 2)


def tres(d):
    _numero(d, 3)


def cuatro(d):
    _numero(d, 4)


def cinco(d):
    _numero(d, 5)


ICONOS = {f.__name__: f for f in (
    ojo, ojo_prohibido, calabaza, agua, olas, flecha, escudo, espada, pico, diamante, gema_verde, oro, cofre, reloj,
    sol, luna, rayo, explosion, fuego, corazon, calavera, cerdo, oveja, oveja_arcoiris, conejo, etiqueta, libro,
    mapa, brujula, casa, arbol, bloque, portal, teletransporte, estrella, cama, manzana, huevo, dinamita, check,
    cruz, interrogacion, exclamacion, uno, dos, tres, cuatro, cinco)}


# ---------------------------------------------------------------- elegir icono por frase

_PALABRAS = [  # (expresión, icono) — la primera que coincide gana; lo que describe la frase va antes que el número
    (r"no (le |lo )?mir|no mires", "ojo_prohibido"), (r"\bmir|\bojo\b", "ojo"),
    (r"calabaza", "calabaza"), (r"\bagua|lluvia|mojad|nadar|\bmar\b|\brio\b", "agua"), (r"\bola", "olas"),
    (r"flecha|arco\b|disparo", "flecha"), (r"escudo|protege", "escudo"), (r"espada|atac|pelea|luch", "espada"),
    (r"pico\b|picar|minar|mina\b", "pico"), (r"diamante", "diamante"), (r"esmeralda|aldean|comerci", "gema_verde"),
    (r"\boro\b|lingote", "oro"), (r"cofre|tesoro|botin", "cofre"), (r"\breloj|minuto|segundo|tiempo|dura\b", "reloj"),
    (r"\bdia\b|\bsol\b|amanecer", "sol"), (r"noche|luna|oscur", "luna"), (r"rayo|tormenta|electric|cargad", "rayo"),
    (r"explot|explosi|estall|bomba", "explosion"), (r"dinamita|\btnt\b", "dinamita"), (r"fuego|lava|quema|arde", "fuego"),
    (r"vida|corazon|salud|curar", "corazon"), (r"muer|morir|mata|esqueleto|calavera|cabeza", "calavera"),
    (r"cerdo", "cerdo"), (r"arcoiris|colores", "oveja_arcoiris"), (r"oveja|lana", "oveja"), (r"conejo", "conejo"),
    (r"etiqueta|nombre|llama[rd]?\b", "etiqueta"), (r"libro|encantamiento|encantad", "libro"), (r"mapa", "mapa"),
    (r"brujula|norte", "brujula"), (r"casa|construi|refugio", "casa"), (r"arbol|madera|bosque", "arbol"),
    (r"portal|dimension", "portal"), (r"teletransport|desaparec", "teletransporte"), (r"cama|dormir", "cama"),
    (r"comida|comer|manzana|hambre", "manzana"), (r"huevo|gallina", "huevo"), (r"bloque", "bloque"),
    (r"sigue|siguenos|sigueme|suscrib", "estrella"),
    (r"^\s*(uno|primer[oa]?)\b", "uno"), (r"^\s*dos\b", "dos"), (r"^\s*(y )?tres\b", "tres"),
    (r"^\s*(y )?cuatro\b", "cuatro"), (r"^\s*(y )?cinco\b", "cinco"),
    (r"secreto|sabias|\?", "interrogacion"), (r"cuidado|ojo,|peligr", "exclamacion"),
]


def _plano(texto):
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def adivinar(frase):
    t = _plano(frase)
    return next((icono for patron, icono in _PALABRAS if re.search(patron, t)), None)


def para_guion(g):
    """Un icono (o None) por cada frase: los que eligió Claude y, si falta alguno, deducido de la frase."""
    pedidos = g.get("visuales") or []
    return [(pedidos[i] if i < len(pedidos) and pedidos[i] in ICONOS else None) or adivinar(f)
            for i, f in enumerate(g["narracion"])]


# ---------------------------------------------------------------- dibujar

def dibujar(nombre, salida):
    """PNG con el icono en pixel art: borde oscuro, ampliado x14 y una sombra suave."""
    img, d = _lienzo()
    ICONOS[nombre](d)
    alfa = img.getchannel("A")
    borde = alfa.point(lambda a: 255 if a > 0 else 0).filter(ImageFilter.MaxFilter(3))
    fondo = Image.new("RGBA", img.size, BORDE)
    fondo.putalpha(borde)
    fondo.alpha_composite(img)
    grande = fondo.resize((LADO * ESCALA, LADO * ESCALA), Image.NEAREST)
    lienzo = Image.new("RGBA", (grande.width + 80, grande.height + 80), (0, 0, 0, 0))
    sombra = Image.new("RGBA", grande.size, (0, 0, 0, 170))
    sombra.putalpha(grande.getchannel("A").point(lambda a: 170 if a else 0))
    lienzo.alpha_composite(sombra, (40, 52))
    lienzo = lienzo.filter(ImageFilter.GaussianBlur(10))
    lienzo.alpha_composite(grande, (40, 40))
    lienzo.save(salida)
    return salida


def muestrario(salida, columnas=8):
    """Hoja con todos los iconos, para revisarlos."""
    nombres = list(ICONOS)
    celda = 150
    filas = (len(nombres) + columnas - 1) // columnas
    hoja = Image.new("RGB", (columnas * celda, filas * (celda + 22)), (11, 18, 48))
    d = ImageDraw.Draw(hoja)
    for i, n in enumerate(nombres):
        img, dd = _lienzo()
        ICONOS[n](dd)
        x, y = (i % columnas) * celda, (i // columnas) * (celda + 22)
        hoja.paste(img.resize((128, 128), Image.NEAREST), (x + 11, y + 6), img.resize((128, 128), Image.NEAREST))
        d.text((x + celda // 2, y + celda + 6), n, fill=(200, 210, 240), anchor="mm")
    hoja.save(salida)
