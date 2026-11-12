"""Innenraum der Seneca II (Elite-Variante) glaubwuerdiger machen.

- Leder-Texturen (selbst erzeugt, kachelbar) fuer Kabinenwaende, Armaturenbrett und Sitze
  statt des grauen Karo-Stoffs (velour.png der Lackierung)
- Tuerverkleidungen links und rechts als eigenes 3D-Modell (elite-innen.ac): Grundplatte,
  Polster, Armlehne, Fensterleiste, Kartentasche, Tuergriff

Wird von seneca_elite.py aufgerufen (erzeuge_innenraum) und liefert die XML-Zeilen fuer
SenecaII-Elite.xml. Die Original-Dateien der Seneca bleiben unveraendert.

Koordinaten wie in SenecaII.ac (Untermodell ohne Versatz liegt genauso):
  x = laengs (minus = vorne), y = Hoehe, z = quer (plus = links / Pilotenseite)
"""

import math
import os
import random
import struct
import zlib

# --- Texturen -----------------------------------------------------------------------------
GROESSE = 256           # Pixel, kachelbar
ZELLEN = 48             # Narben pro Bildbreite (Kachel 25 cm -> Narbe ~5 mm)
# Name -> Grundfarbe (RGB); die Narbung dunkelt ab
LEDER = {
    "elite-leder-wand.png": (196, 178, 150),    # helles Beige: Waende und Decke
    "elite-leder-brett.png": (58, 54, 52),      # fast schwarz: Armaturenbrett
    "elite-leder-sitz.png": (128, 86, 54),      # Cognac-Braun: Sitze
    "elite-leder-hell.png": (235, 235, 235),    # neutral hell: Tuerteile (Farbe aus Material)
}


def png(pfad, breite, hoehe, pixel):
    """Schreibt ein RGB-PNG (pixel = bytes, Zeile fuer Zeile)."""
    roh = b"".join(b"\x00" + pixel[y * breite * 3:(y + 1) * breite * 3] for y in range(hoehe))

    def block(art, daten):
        return (struct.pack(">I", len(daten)) + art + daten
                + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF))

    with open(pfad, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n"
                + block(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0))
                + block(b"IDAT", zlib.compress(roh, 9)) + block(b"IEND", b""))


def narbung():
    """Helligkeit 0..1 je Pixel: Leder-Narben (Zellmuster mit Falten) + leichte Wolken."""
    zufall = random.Random(34)       # fester Startwert: jedes Mal dieselbe Textur
    n = ZELLEN
    punkte = [[(i + zufall.random(), j + zufall.random()) for j in range(n)] for i in range(n)]
    wolke = [[zufall.random() for _ in range(8)] for _ in range(8)]
    zelle = GROESSE / n
    werte = []
    for py in range(GROESSE):
        for px in range(GROESSE):
            fx, fy = px / zelle, py / zelle
            ix, iy = int(fx), int(fy)
            d = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cx, cy = ix + dx, iy + dy
                    sx, sy = punkte[cx % n][cy % n]
                    sx += cx - cx % n
                    sy += cy - cy % n
                    d.append((fx - sx) ** 2 + (fy - sy) ** 2)
            d.sort()
            falte = min(1.0, (math.sqrt(d[1]) - math.sqrt(d[0])) * 2.0)   # 0 = auf der Falte
            falte = falte * falte * (3 - 2 * falte)                          # weicher Rand
            # weiche Wolken (kachelbar, 8x8 Gitter, Kosinus-Interpolation)
            gx, gy = px / GROESSE * 8, py / GROESSE * 8
            ax, ay = int(gx), int(gy)
            tx = (1 - math.cos((gx - ax) * math.pi)) / 2
            ty = (1 - math.cos((gy - ay) * math.pi)) / 2
            w00, w10 = wolke[ax % 8][ay % 8], wolke[(ax + 1) % 8][ay % 8]
            w01, w11 = wolke[ax % 8][(ay + 1) % 8], wolke[(ax + 1) % 8][(ay + 1) % 8]
            w = (w00 * (1 - tx) + w10 * tx) * (1 - ty) + (w01 * (1 - tx) + w11 * tx) * ty
            kuppe = 1 - math.sqrt(d[0]) * 0.25           # Narbe leicht gewoelbt
            werte.append((0.90 + 0.10 * falte) * (0.86 + 0.14 * w) * (0.96 + 0.04 * kuppe))
    return werte


def erzeuge_texturen(ordner):
    hell = narbung()
    for name, (r, g, b) in LEDER.items():
        pixel = bytearray()
        for h in hell:
            pixel += bytes((min(255, int(r * h)), min(255, int(g * h)), min(255, int(b * h))))
        png(os.path.join(ordner, name), GROESSE, GROESSE, bytes(pixel))
    print(f"{len(LEDER)} Leder-Texturen geschrieben.")


# --- Tuerverkleidungen (3D) -------------------------------------------------------------
# Innenwand der Kabine: Abstand zur Mitte (|z|) je Hoehe y, aus SenecaII.ac vermessen
# (im Cockpitbereich x -1.8 ... -0.8 ueberall gleich)
WAND = [(0.70, 0.600), (0.80, 0.620), (0.90, 0.625), (1.00, 0.630), (1.10, 0.640),
        (1.20, 0.642), (1.30, 0.650), (1.40, 0.640), (1.50, 0.620)]
TEX_PRO_M = 4.0          # Textur-Wiederholungen pro Meter (eine Kachel = 25 cm)
# Materialfarben (multipliziert mit der hellen Ledertextur)
FARBEN = {
    "platte": (0.55, 0.40, 0.27),     # Grundplatte: mittleres Braun
    "polster": (0.80, 0.71, 0.58),    # Polster: Beige, hebt sich ab
    "armlehne": (0.42, 0.29, 0.19),   # Armlehne: dunkles Braun
    "leiste": (0.24, 0.21, 0.19),     # Fensterleiste, Kartentasche: fast schwarz
    "griff": (0.75, 0.75, 0.78),      # Tuergriff: Chrom (ohne Textur)
}
# Teile: (Name, Material, x vorn, x hinten, y unten, y oben, Abstand zur Wand, Fase, Seiten)
# Seiten: "lr" beide, "r" nur rechts (dort ist die Tuer)
TEILE = [
    ("Verkleidung", "platte", -1.72, -0.92, 0.78, 1.34, 0.018, 0.012, "lr"),
    ("Polster", "polster", -1.60, -1.04, 0.90, 1.08, 0.032, 0.014, "lr"),
    ("Armlehne", "armlehne", -1.56, -1.10, 1.12, 1.19, 0.060, 0.018, "lr"),
    ("Fensterleiste", "leiste", -1.76, -0.88, 1.34, 1.40, 0.040, 0.012, "lr"),
    ("Kartentasche", "leiste", -1.66, -1.32, 0.80, 0.88, 0.030, 0.008, "lr"),
    ("Tuergriff", "griff", -1.04, -0.96, 1.22, 1.25, 0.038, 0.008, "r"),
]
Y_SCHRITT = 0.04         # die Teile folgen der Wandkruemmung in diesen Hoehenschritten


def wand(y):
    for (y1, z1), (y2, z2) in zip(WAND, WAND[1:]):
        if y1 <= y <= y2:
            return z1 + (z2 - z1) * (y - y1) / (y2 - y1)
    return WAND[0][1] if y < WAND[0][0] else WAND[-1][1]


def teil_flaechen(x1, x2, y1, y2, abstand, fase):
    """Gewoelbte Platte mit Fase: Rueckseite an der Wand, Vorderseite um 'abstand' davor,
    Kanten schraeg. Rueckgabe: Liste von Vierecken/Dreiecken aus (x, y, tiefe) mit
    tiefe = Abstand von der Wand nach innen (0 = Wand)."""
    f = min(fase, (x2 - x1) / 3, (y2 - y1) / 3)
    schritte = max(1, round((y2 - y1) / Y_SCHRITT))
    ys = [y1 + (y2 - y1) * k / schritte for k in range(schritte + 1)]
    # Vorderseite (eingerueckt um die Fase), Ring aussen an der Wand
    vorne_ys = [max(y1 + f, min(y2 - f, y)) for y in ys]
    flaechen = []
    for k in range(schritte):
        ya, yb = vorne_ys[k], vorne_ys[k + 1]
        if yb > ya:
            flaechen.append([(x1 + f, ya, abstand), (x2 - f, ya, abstand),
                             (x2 - f, yb, abstand), (x1 + f, yb, abstand)])
        # Fasen links/rechts (vorne/hinten in Laengsrichtung)
        flaechen.append([(x1, ys[k], 0.002), (x1 + f, ya, abstand),
                         (x1 + f, yb, abstand), (x1, ys[k + 1], 0.002)])
        flaechen.append([(x2 - f, ya, abstand), (x2, ys[k], 0.002),
                         (x2, ys[k + 1], 0.002), (x2 - f, yb, abstand)])
    # Fasen oben/unten
    flaechen.append([(x1, y1, 0.002), (x2, y1, 0.002), (x2 - f, y1 + f, abstand),
                     (x1 + f, y1 + f, abstand)])
    flaechen.append([(x1 + f, y2 - f, abstand), (x2 - f, y2 - f, abstand),
                     (x2, y2, 0.002), (x1, y2, 0.002)])
    return flaechen


def ac_objekt(name, flaechen, seite, material, textur):
    """Ein AC3D-Objekt; seite +1 = links (z positiv), -1 = rechts."""
    punkte, index, surf = [], {}, []
    for flaeche in flaechen:
        refs = []
        for x, y, tiefe in flaeche:
            z = seite * (wand(y) - tiefe)
            schluessel = (round(x, 5), round(y, 5), round(z, 5))
            if schluessel not in index:
                index[schluessel] = len(punkte)
                punkte.append(schluessel)
            # Textur: laengs = x, hoch = y (die Fase verzerrt kaum)
            refs.append((index[schluessel], x * TEX_PRO_M, y * TEX_PRO_M))
        if seite > 0:
            refs.reverse()      # Vorderseite zeigt in die Kabine (links = nach -z)
        surf.append(refs)
    zeilen = ["OBJECT poly", f'name "{name}"']
    if textur:
        zeilen += [f'texture "{textur}"', "texrep 1 1"]
    zeilen += ["crease 40.0", f"numvert {len(punkte)}"]
    zeilen += [f"{x:.5f} {y:.5f} {z:.5f}" for x, y, z in punkte]
    zeilen.append(f"numsurf {len(surf)}")
    for refs in surf:
        zeilen += ["SURF 0x20", f"mat {material}", f"refs {len(refs)}"]
        zeilen += [f"{i} {u:.4f} {v:.4f}" for i, u, v in refs]
    zeilen.append("kids 0")
    return zeilen


def erzeuge_ac(pfad):
    materialien = list(FARBEN)
    kopf = ["AC3Db"]
    for name in materialien:
        r, g, b = FARBEN[name]
        glanz = "spec 0.6 0.6 0.6  shi 64" if name == "griff" else "spec 0.08 0.08 0.08  shi 8"
        kopf.append(f'MATERIAL "{name}" rgb {r} {g} {b}  amb {r} {g} {b}  emis 0 0 0  '
                    f"{glanz}  trans 0")
    objekte = []
    for name, mat, x1, x2, y1, y2, abstand, fase, seiten in TEILE:
        flaechen = teil_flaechen(x1, x2, y1, y2, abstand, fase)
        for seite, kurz in ((1, "l"), (-1, "r")):
            if kurz in seiten:
                textur = None if mat == "griff" else "elite-leder-hell.png"
                objekte.append(ac_objekt(f"Elite{name}.{kurz.upper()}", flaechen, seite,
                                         materialien.index(mat), textur))
    zeilen = kopf + ["OBJECT world", f"kids {len(objekte)}"]
    for objekt in objekte:
        zeilen += objekt
    with open(pfad, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(zeilen) + "\n")
    print(f"Tuerverkleidungen: {len(objekte)} Teile geschrieben.")


# --- Einbau ins Modell --------------------------------------------------------------------
VELOUR_ALT = """      <texture-prop>texture[1]</texture-prop>
      <texture>velour.png</texture>"""


def modell_anpassen(modell):
    """SenecaII-Elite.xml: Leder statt Karo-Stoff, Sitze in Leder, Tuerverkleidungen dazu."""
    if VELOUR_ALT not in modell:
        print("WARNUNG: Stoff-Textur (velour) im Modell nicht gefunden - Waende bleiben grau.")
    # Kabine (Waende/Decke) hell; die Lackierungs-Wahl aendert den Innenraum dann nicht mehr
    modell = modell.replace(
        """      <object-name>Dashboard</object-name>
      <object-name>Cabin</object-name>
      <object-name>box</object-name>""",
        """      <object-name>Cabin</object-name>""").replace(
        VELOUR_ALT, "      <texture>elite-leder-wand.png</texture>")
    zusatz = """  <!-- Elite: Innenraum in Leder, Tuerverkleidungen (elite_innen.py) -->
  <animation>
    <type>material</type>
    <object-name>Dashboard</object-name>
    <object-name>box</object-name>
    <texture>elite-leder-brett.png</texture>
  </animation>
  <animation>
    <type>material</type>
    <object-name>Seat-</object-name>
    <object-name>Seat-56</object-name>
    <object-name>Seat-12</object-name>
    <texture>elite-leder-sitz.png</texture>
  </animation>
  <model>
    <name>EliteInnenraum</name>
    <path>elite-innen.ac</path>
  </model>
"""
    pos = modell.rindex("</PropertyList>")
    return modell[:pos] + zusatz + modell[pos:]


def erzeuge_innenraum(modell_ordner):
    erzeuge_texturen(modell_ordner)
    erzeuge_ac(os.path.join(modell_ordner, "elite-innen.ac"))


DATEIEN = ["elite-innen.ac", *LEDER]
