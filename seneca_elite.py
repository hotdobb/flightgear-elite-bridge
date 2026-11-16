"""Erzeugt die Flugzeug-Variante "Seneca II Elite": die Seneca II ohne die Bedienteile,
die es am Elite-Cockpit als echte Hardware gibt (Funkgeraete, Autopilot, Schalter,
Hebel, Horn, Pedale, Fahrwerkshebel und -lampen).

Die Original-Seneca bleibt unveraendert; neben ihre Dateien kommen nur neue:
  SenecaII-elite-set.xml, Models/SenecaII-Elite.xml, Instruments-3d/SwitchPanel-Elite.xml
Nach einem Update der Seneca einfach erneut ausfuehren. --entfernen loescht sie wieder.

Versteckte Teile lassen sich in FlightGear wieder einblenden:
  /sim/elite/zeige-hardware-teile = true

Beispiel:
  python seneca_elite.py
"""

import argparse
import os
import re
import subprocess

import elite_innen

# Ordner der Seneca II; wird von elite_einrichten gesucht (FlightGear-Logbuch, Download-
# Ordner) und hier per setze_seneca_ordner() eingetragen
SENECA = None


def setze_seneca_ordner(pfad):
    global SENECA
    SENECA = pfad
SCHALTER_PROPERTY = "/sim/elite/zeige-hardware-teile"

# Untermodelle (<name> in Models/SenecaII.xml), die ganz wegfallen
OHNE_MODELLE = {
    "kx165tso1", "kx165tso2",       # COM/NAV 1 und 2 -> AP-3000 Reihe 1/2
    "kr87",                         # ADF -> Reihe 3
    "dme",                          # DME -> Reihe 4
    "KT-76A transponder",           # Transponder -> Reihe 6
    "AltimaticIIIc", "AutopilotMode",  # Autopilot -> Reihe 7
    "NAVSourceSwitch",              # NAV/GPS -> GPS-Reihe
    # Ruderpedale bleiben sichtbar (Wunsch Nutzer 2026-11-12): am Monitor sieht man die
    # eigenen Fuesse nicht, die Pedale im Bild bewegen sich mit den Elite-Pedalen mit
    "GearIndicator", "GearTransitLight",  # Fahrwerkslampen -> Pro Panel
}
# Copilot-Instrumente, die es beim Pilot schon gibt: (Name, Pfad-Ende) -> fallen weg
OHNE_DOPPELT = {("AI2", "AI.xml"), ("Altimeter", "alt.xml", "rechts")}
# Neue Plaetze (y-m = seitlich, z-m = Hoehe), damit alles kompakt beim Pilot sitzt:
# Mittelspalte wo frueher die Funkgeraete waren: Audio, darunter GPS, EGT, Vakuum
NEUER_PLATZ = {
    "gps155 gps": (-0.05, 1.535),
    "EGT.L": (-0.085, 1.48),
    "EGT.R": (-0.015, 1.48),
    "Vacuum": (-0.05, 1.42),
    "FuelFlow": (-0.40, 1.287),      # neben Drehzahl/Ladedruck (frueher Autopilot)
    "hobbs.xml": (0.035, 1.42),      # Betriebsstundenzaehler neben Vakuum
}
# Teile von SenecaII.ac, die versteckt werden
OHNE_OBJEKTE = [
    "Yoke.L", "Yoke.R",                                     # Steuerhorn
    "ThrottleControl.L", "ThrottleControl.R",               # Hebel
    "PropellerControl.L", "PropellerControl.R",
    "MixtureControl.L", "MixtureControl.R", "FrictionLock",
    "GearLeverGroup", "GearLever", "GearLeverNut",          # Fahrwerkshebel
    "FlapControl",                                          # Klappen-Taster
    # Cowl-Flaps-Hebel bleiben sichtbar: sie zeigen die Stellung (Elite hat nur Wippen)
    "FuelSelectorControl.L", "FuelSelectorControl.R",       # Tankwahl
    "ParkingBrakeControl",                                  # Parkbremse
    "ElevatorTrimControl", "RudderTrimControl",             # Trimmung
]
# Schalterleiste: am Pro Panel vorhanden. Es bleiben Primer und Beacon-Licht.
# Taxi-Licht = Reserve-Schalter am Pro Panel (seit 2026-11-12)
OHNE_SCHALTER = [
    "Master", "Alternator.L", "Alternator.R", "TaxiLight",
    "Magneto.L.L", "Magneto.L.R", "Magneto.R.L", "Magneto.R.R",
    "Starter", "Starter.L", "Starter.R",
    "FuelPump.L", "FuelPump.R", "PitotHeat",
    "LandingLight", "NavLight", "AntiCollLight.Wing",       # Wing = Strobe
]

KOPF = "<!-- Erzeugt von C:\\ElitePrj\\seneca_elite.py - nicht von Hand aendern -->\n"


# --- Aussensicht fuer den Zwei-Monitor-Betrieb: Flugzeug mit Rumpf, Fluegeln, Motoren,
# aber ohne Armaturenbrett (Instrumente sind auf dem eigenen Monitor). Alle Untermodelle im
# Bereich des Armaturenbretts fallen weg, dazu diese Teile von SenecaII.ac:
# Blick in die Nase ist laut Nutzer in Ordnung (Ansicht stellt er per Maus ein).
OHNE_ARMATURENBRETT = [
    "Dashboard", "Dashboard-p1", "InstrumentCover", "RPMPlacard", "GearSpeedPlacard",
    "CenterConsole", "FlapTrimConsole", "CowlConsole", "PowerQuadrant", "Cowl.Chassis",
    "CowlFlapsControl.L", "CowlFlapsControl.R",
    "TrimwheelElevatorChassis", "TrimwheelRudderChassis", "FlapControlChassis",
    "RudderTrimIndicator", "ElevatorTrimIndicator", "Charts", "Chart1", "Chart2",
    "Compass", "DeviationTable", "Headset", "RadioLightsDimmer", "PanelLightsDimmer",
    "Label", "Label.Fuel", "Label.FuelOff", "Label.FuelX", "Label.FuelOn", "AltAirLabel",
    "AlternateAirControl.L", "AlternateAirControl.R",
    "EmergencyExtend", "GearEmergencyKnob", "GearEmergencySecure",
    "Chassis", "NosegearBox",          # dunkle Kaesten vorne (im Screenshot gesehen)
]


def im_armaturenbrett(block):
    """Untermodell sitzt vorne im Cockpit (Armaturenbrett, Konsole, Scheibenrahmen)?"""
    werte = [re.search(rf"<{k}>([^<]*)</{k}>", block) for k in ("x-m", "y-m", "z-m")]
    if not all(werte):
        return False
    x, y, z = (float(w.group(1)) for w in werte)
    return -2.0 < x < -1.3 and abs(y) < 0.7 and 1.1 < z < 2.0


def erzeuge_aussensicht(elite_modell):
    entfernt = []

    def ohne(treffer):
        if im_armaturenbrett(treffer.group(0)):
            entfernt.append(1)
            return ""
        return treffer.group(0)

    modell = re.sub(r"[ \t]*<model>.*?</model>[ \t]*\n?", ohne, elite_modell, flags=re.S)
    modell = vor_ende(modell, verstecken(OHNE_ARMATURENBRETT))
    schreibe(os.path.join(SENECA, "Models", "SenecaII-Aussen.xml"), mit_kopf(modell))
    print(f"Aussensicht: {len(entfernt)} Instrumente/Teile vorne entfernt.")


# --- Apollo-Display an der Stelle des Garmin GPS155: eine flache Flaeche "ApolloScreen"
# (16 x 5 cm wie die Garmin-Front, Vorderseite zeigt nach hinten zum Piloten). Das Add-on
# zeichnet darauf per Canvas den Inhalt des Elo-Displays (elite_gps.py).
APOLLO_B, APOLLO_H, APOLLO_X = 0.08, 0.0254, 0.0045   # halbe Breite/Hoehe, Abstand vorne


def leeres_png(pfad):
    """Schwarzes 4x4-PNG (die Flaeche braucht eine Textur, Canvas ersetzt sie)."""
    import struct
    import zlib

    def block(art, daten):
        return (struct.pack(">I", len(daten)) + art + daten
                + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF))
    roh = b"".join(b"\0" + b"\0\0\0" * 4 for _ in range(4))
    with open(pfad, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + block(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
                + block(b"IDAT", zlib.compress(roh)) + block(b"IEND", b""))


def erzeuge_apollo(ordner):
    # AC3D: x wie FlightGear, y = FG-Hoehe, z = -FG-seitlich; Reihenfolge gegen den
    # Uhrzeigersinn von hinten gesehen (unten links, unten rechts, oben rechts, oben links)
    b, h, x = APOLLO_B, APOLLO_H, APOLLO_X
    ecken = [(x, -h, b), (x, -h, -b), (x, h, -b), (x, h, b)]
    schreibe(os.path.join(ordner, "apollo-elite.ac"), "AC3Db\n"
             'MATERIAL "Bildschirm" rgb 1 1 1  amb 1 1 1  emis 0 0 0  spec 0 0 0  shi 0  trans 0\n'
             "OBJECT world\nkids 1\nOBJECT poly\nname \"ApolloScreen\"\n"
             'texture "apollo-leer.png"\nnumvert 4\n'
             + "".join(f"{e[0]} {e[1]} {e[2]}\n" for e in ecken)
             + "numsurf 1\nSURF 0x10\nmat 0\nrefs 4\n0 0 0\n1 1 0\n2 1 1\n3 0 1\nkids 0\n")
    leeres_png(os.path.join(ordner, "apollo-leer.png"))
    print("geschrieben:", os.path.join(ordner, "apollo-leer.png"))
    schreibe(os.path.join(ordner, "apollo-elite.xml"), f"""<?xml version="1.0"?>
{KOPF}<PropertyList>
  <path>apollo-elite.ac</path>
  <animation>
    <type>noshadow</type>
  </animation>
  <!-- leuchtet selbst (Display), unabhaengig vom Licht im Cockpit -->
  <animation>
    <type>material</type>
    <object-name>ApolloScreen</object-name>
    <emission><red>1</red><green>1</green><blue>1</blue></emission>
  </animation>
</PropertyList>
""")


def verstecken(objekte):
    namen = "".join(f"    <object-name>{o}</object-name>\n" for o in objekte)
    return ("  <!-- Elite: Teile, die es als Hardware gibt -->\n"
            "  <animation>\n    <type>select</type>\n" + namen +
            f"    <condition><property>{SCHALTER_PROPERTY}</property></condition>\n"
            "  </animation>\n")


def vor_ende(text, zusatz):
    pos = text.rindex("</PropertyList>")
    return text[:pos] + zusatz + text[pos:]


def lies(pfad):
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def mit_kopf(text):
    """Hinweis-Kommentar hinter die XML-Deklaration (sie muss ganz vorne stehen)."""
    if text.startswith("<?xml"):
        ende = text.index("?>") + 2
        return text[:ende] + "\n" + KOPF + text[ende:].lstrip("\r\n")
    return KOPF + text


def schreibe(pfad, text):
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(text)
    print("geschrieben:", pfad)


def erzeuge():
    modell = lies(os.path.join(SENECA, "Models", "SenecaII.xml"))
    entfernt, verschoben = [], []

    def ohne(treffer):
        block = treffer.group(0)
        name = re.search(r"<name>([^<]*)</name>", block)
        name = name.group(1).strip() if name else ""
        pfad = re.search(r"<path>([^<]*)</path>", block).group(1).split("/")[-1]
        y = re.search(r"<y-m>([^<]*)</y-m>", block)
        rechts = y is not None and float(y.group(1)) > 0
        if (name in OHNE_MODELLE or (name, pfad) in OHNE_DOPPELT
                or (name, pfad, "rechts" if rechts else "") in OHNE_DOPPELT):
            entfernt.append(name)
            return ""
        platz = NEUER_PLATZ.get(name) or NEUER_PLATZ.get(pfad)
        if platz:
            block = re.sub(r"<y-m>[^<]*</y-m>", f"<y-m>{platz[0]}</y-m>", block, count=1)
            block = re.sub(r"<z-m>[^<]*</z-m>", f"<z-m>{platz[1]}</z-m>", block, count=1)
            verschoben.append(name or pfad)
        return block

    modell = re.sub(r"[ \t]*<model>.*?</model>[ \t]*\n?", ohne, modell, flags=re.S)
    fehlt = (OHNE_MODELLE | {"AI2", "Altimeter"}) - set(entfernt)
    if fehlt:
        print("WARNUNG: nicht gefunden:", ", ".join(sorted(fehlt)))
    if len(verschoben) != len(NEUER_PLATZ):
        print("WARNUNG: verschoben nur:", ", ".join(verschoben))
    modell = modell.replace("Aircraft/SenecaII/Instruments-3d/SwitchPanel.xml",
                            "Aircraft/SenecaII/Instruments-3d/SwitchPanel-Elite.xml")
    # Garmin GPS155 (nur Bild ohne Funktion) -> Apollo-Display gleicher Groesse
    modell = modell.replace("Aircraft/SenecaII/Models/gps155.xml",
                            "Aircraft/SenecaII/Models/apollo-elite.xml")
    erzeuge_apollo(os.path.join(SENECA, "Models"))
    modell = vor_ende(modell, verstecken(OHNE_OBJEKTE))
    # Innenraum: Leder statt Karo-Stoff, Tuerverkleidungen (elite_innen.py)
    modell = elite_innen.modell_anpassen(modell)
    elite_innen.erzeuge_innenraum(os.path.join(SENECA, "Models"))
    schreibe(os.path.join(SENECA, "Models", "SenecaII-Elite.xml"), mit_kopf(modell))

    erzeuge_aussensicht(modell)

    schalter = lies(os.path.join(SENECA, "Instruments-3d", "SwitchPanel.xml"))
    schalter = vor_ende(schalter, verstecken(OHNE_SCHALTER))
    schreibe(os.path.join(SENECA, "Instruments-3d", "SwitchPanel-Elite.xml"), mit_kopf(schalter))

    schreibe(os.path.join(SENECA, "SenecaII-elite-set.xml"), f"""<?xml version="1.0"?>
{KOPF}<PropertyList include="SenecaII-set.xml">
  <sim>
    <description>PA34-200T Seneca II (Elite-Cockpit)</description>
    <variant-of>SenecaII</variant-of>
    <model>
      <path>Aircraft/SenecaII/Models/SenecaII-Elite.xml</path>
    </model>
  </sim>
</PropertyList>
""")
    print(f"Fertig: {len(entfernt)} Geraete entfernt, {len(OHNE_OBJEKTE)} Cockpit-Teile und "
          f"{len(OHNE_SCHALTER)} Schalter versteckt.")


# --- Flaches Instrumentenbrett fuer einen eigenen Monitor (16:10, z.B. Anmite 16 Zoll
# 1920x1200). Im eigenen Fenster zeichnet FlightGear 2D-Panels 1024 Einheiten breit, die
# Hoehe folgt dem Seitenverhaeltnis: 16:10 -> 1024 x 640 (per Bildschirmfoto gemessen).
# x/y = Mitte, y von unten.
PANEL_W, PANEL_H = 1024, 640
HINTERGRUND = "elite-hintergrund.png"
# Raster mit gleichmaessigen Abstaenden (Wunsch Nutzer 2026-11-11), von oben nach unten:
#   Reihe A / B: Uhr bzw. ADF (150), vier Fluginstrumente (168), Warnlampen, Cowl Flaps
#   darunter links die Motoren in 2 x 4 (110), rechts daneben das Navi-Display
#   ganz unten die Tank/Oel/Strom-Leisten nebeneinander (links | rechts)
RAND, SPALT = 8, 9
GROSS, KLEIN, LAMPE, ECKE = 168, 110, 22, 150
REIHE_A = PANEL_H - 6 - GROSS // 2                  # 550
REIHE_B = REIHE_A - GROSS - 6                       # 376; Unterkante 292
SPALTE = [SPALT + ECKE // 2] + [SPALT + ECKE + SPALT + GROSS // 2 + i * (GROSS + SPALT)
                                for i in range(4)]  # 84, 252, 429, 606, 783
MOTOR_X = [RAND + KLEIN // 2 + i * (KLEIN + 5) for i in range(4)]      # 63 ... 408
REIHE_MOTOR = (REIHE_B - GROSS // 2 - 6 - KLEIN // 2,)                  # 231
REIHE_MOTOR += (REIHE_MOTOR[0] - KLEIN - 5,)                            # 116; Unterkante 61
LEISTE_W, LEISTE_H, LEISTE_Y = 500, 39, 35          # zwei Leisten nebeneinander
LEISTE_X = (RAND + LEISTE_W // 2, PANEL_W - RAND - LEISTE_W // 2)
# Feld fuer das Navi-Display (Fenster der Bruecke, elite_gps): rechts neben den Motoren.
# Eine Anzeige, die MAP-Taste wechselt zwischen Text und Karte (wie Apollo GX50/60); das
# spart Breite, rechts daneben bleibt ein Feld fuer ein weiteres Geraet frei.
# Das Navi sitzt ganz rechts am Rand, weil das AP-3000 (mit den Apollo-Tasten) rechts neben
# dem Monitor steht (Wunsch Nutzer 2026-11-11); das freie Feld liegt zwischen Motoren und Navi.
NAVI_BREITE = 290
NAVI_FREI = (PANEL_W - RAND - NAVI_BREITE, REIHE_MOTOR[1] - KLEIN // 2,
             PANEL_W - RAND, REIHE_MOTOR[0] + KLEIN // 2)   # x1, y1, x2, y2 = 726, 61, 1016, 286
RESERVE_FREI = (MOTOR_X[3] + KLEIN // 2 + RAND, NAVI_FREI[1],
                NAVI_FREI[0] - RAND, NAVI_FREI[3])           # 471 ... 718
# Name im Seneca-IFR-Panel (bei Doppelten: Name#Nummer) -> (x, y, w, h)
PANEL_PLATZ = {
    "clock": (SPALTE[0], REIHE_A, ECKE, ECKE),
    "Airspeed Indicator": (SPALTE[1], REIHE_A, GROSS, GROSS),
    "Attitude Gyro": (SPALTE[2], REIHE_A, GROSS, GROSS),
    "Altimeter": (SPALTE[3], REIHE_A, GROSS, GROSS),
    "Radar Altimeter": (SPALTE[4], REIHE_A, GROSS, GROSS),
    "ADF Coordinator": (SPALTE[0], REIHE_B, ECKE, ECKE),
    "Turn Coordinator": (SPALTE[1], REIHE_B, GROSS, GROSS),
    "Bendix King HSI": (SPALTE[2], REIHE_B, GROSS, GROSS),
    "Vertical Velocity Indicator": (SPALTE[3], REIHE_B, GROSS, GROSS),
    "VOR 2 Gauge": (SPALTE[4], REIHE_B, GROSS, GROSS),
    "RPM Left Gauge": (MOTOR_X[0], REIHE_MOTOR[0], KLEIN, KLEIN),
    "MP Gauge": (MOTOR_X[1], REIHE_MOTOR[0], KLEIN, KLEIN),
    "RPM Right Gauge": (MOTOR_X[2], REIHE_MOTOR[0], KLEIN, KLEIN),
    "Fuel Flow Gauge": (MOTOR_X[3], REIHE_MOTOR[0], KLEIN, KLEIN),
    "EGT-L Gauge": (MOTOR_X[0], REIHE_MOTOR[1], KLEIN, KLEIN),
    "EGT-R Gauge": (MOTOR_X[1], REIHE_MOTOR[1], KLEIN, KLEIN),
    "Gyro PressureGauge": (MOTOR_X[2], REIHE_MOTOR[1], KLEIN, KLEIN),
    "FlapTrim": (MOTOR_X[3], REIHE_MOTOR[1], KLEIN, KLEIN),       # Klappen + Trimmung
    "FuelOilAmps#1": (LEISTE_X[0], LEISTE_Y, LEISTE_W, LEISTE_H),  # Tank/Oel/Strom links
    "FuelOilAmps#2": (LEISTE_X[1], LEISTE_Y, LEISTE_W, LEISTE_H),  # ... rechts
}
# Warnlampen unten links in einer Reihe, mit Beschriftung darunter
# Kurze Schilder in grosser Schrift (Wunsch Nutzer): Benzinpumpe, Ladedruck zu hoch, Oeldruck,
# Vakuum (Kreisel), Lichtmaschine
WARNLAMPEN = [("FuelPumpL", "PUMP L"), ("OverBoostL", "BOOST L"), ("Oil", "ÖL"),
              ("GyroAir", "VAK"), ("Alt", "LIMA"), ("OverBoostR", "BOOST R"),
              ("FuelPumpR", "PUMP R")]
# Warnlampen paarweise (links | rechts) untereinander zwischen Radar-Hoehenmesser/VOR 2 und
# Cowl-Flaps-Anzeige (Wunsch Nutzer 2026-11-11); je Lampe Schild darunter
LAMPEN_PLATZ = {"FuelPumpL": (0, 0), "FuelPumpR": (1, 0), "OverBoostL": (0, 1),
                "OverBoostR": (1, 1), "Oil": (0, 2), "GyroAir": (1, 2), "Alt": (0, 3)}
# Platz (1, 3) neben "Lichtm." bleibt frei als Reserve fuer eine achte Lampe
# Darueber, in derselben Spalte, der Magnetkompass (FlightGear-Standardinstrument, 4:1)
KOMPASS = (924, 616, 96, 24)                        # x, y, w, h
LAMPEN_SPALTE_X, LAMPEN_OBEN, LAMPEN_ABSTAND = (899, 949), 583, 76
LAMPEN_XY = {}
for name, (spalte, reihe) in LAMPEN_PLATZ.items():
    LAMPEN_XY[name] = (LAMPEN_SPALTE_X[spalte], LAMPEN_OBEN - reihe * LAMPEN_ABSTAND)
    PANEL_PLATZ[name] = (*LAMPEN_XY[name], LAMPE, LAMPE)
# Text-Layer zeichnet FlightGear 2024 in 2D-Panels nur als schwarze Balken (ausprobiert),
# deshalb sind die Beschriftungen kleine Bilder (PNG, mit Windows-Schrift erzeugt).
SCHILD_W, SCHILD_H = 46, 12
SCHILD_UNTER_LAMPE = 20     # Abstand Mitte Lampe -> Mitte Schild


def schild_datei(text):
    text = text.lower().replace("ö", "oe").replace("ä", "ae").replace("ü", "ue")
    return "elite-" + re.sub(r"[^a-z0-9]+", "-", text).strip("-") + ".png"


def erzeuge_schilder(texte):
    """Schreibt je Text ein PNG (128x32, transparent, schwarze Schrift) nach Panels/Textures."""
    ordner = os.path.join(SENECA, "Panels", "Textures")
    befehle = ["Add-Type -AssemblyName System.Drawing"]
    for text in texte:
        ziel = os.path.join(ordner, schild_datei(text))
        befehle.append(
            "$b = New-Object System.Drawing.Bitmap 128, 32; "
            "$g = [System.Drawing.Graphics]::FromImage($b); "
            "$g.TextRenderingHint = 'AntiAliasGridFit'; "
            "$f = New-Object System.Drawing.Font 'Arial', 24, ([System.Drawing.FontStyle]::Bold), "
            "([System.Drawing.GraphicsUnit]::Pixel); "
            "$s = New-Object System.Drawing.StringFormat; "
            "$s.Alignment = 'Center'; $s.LineAlignment = 'Center'; "
            f"$g.DrawString('{text}', $f, [System.Drawing.Brushes]::Black, "
            "(New-Object System.Drawing.RectangleF 0, 0, 128, 32), $s); "
            f"$b.Save('{ziel}', [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $b.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", "; ".join(befehle)], check=True)
    print(f"{len(texte)} Beschriftungen als Bild geschrieben.")


def powershell_bild(befehle):
    """Fuehrt System.Drawing-Befehle in PowerShell aus (Python hat hier kein PIL)."""
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Add-Type -AssemblyName System.Drawing; " + "; ".join(befehle)], check=True)


# Cowl-Flaps-Anzeige rechts neben Radar-Hoehenmesser/VOR2: zwei Schienen L/R, Marke
# wandert von ZU (unten) nach AUF (oben). Bild 64x384 Pixel = 50x300 Panel-Einheiten.
# Schmal am rechten Rand, damit links daneben die Warnlampen Platz haben.
# So hoch wie die beiden Instrumentenreihen zusammen.
COWL_X, COWL_Y, COWL_W, COWL_H = 998, 463, 36, 336
COWL_BILD, COWL_MARKE = "elite-cowl.png", "elite-cowl-marke.png"
COWL_SCHIENE_X = 12 * COWL_W / 64      # Schienen im Bild bei 20/44 von 64 Pixeln
COWL_MARKE_W, COWL_MARKE_H = COWL_W * 0.28, 7
COWL_ZU, COWL_AUF = round(-105 * COWL_H / 300), round(100 * COWL_H / 300)


def erzeuge_cowl_bilder():
    ordner = os.path.join(SENECA, "Panels", "Textures")
    schrift = ("$f = New-Object System.Drawing.Font 'Arial', 15, ([System.Drawing.FontStyle]::Bold), "
               "([System.Drawing.GraphicsUnit]::Pixel); "
               "$s = New-Object System.Drawing.StringFormat; $s.Alignment = 'Center'; "
               "$w = [System.Drawing.Brushes]::White")

    def text(t, y):
        return (f"$g.DrawString('{t}', $f, $w, (New-Object System.Drawing.RectangleF 0, {y}, "
                "64, 20), $s)")

    powershell_bild([
        "$b = New-Object System.Drawing.Bitmap 64, 384",
        "$g = [System.Drawing.Graphics]::FromImage($b)",
        "$g.TextRenderingHint = 'AntiAliasGridFit'",
        "$g.Clear([System.Drawing.Color]::FromArgb(255, 30, 30, 30))",
        "$g.DrawRectangle((New-Object System.Drawing.Pen ([System.Drawing.Color]::Gray), 2), "
        "1, 1, 61, 381)",
        schrift,
        text("COWL", 6), text("AUF", 36), text("ZU", 334), text("L    R", 356),
        "$g.FillRectangle((New-Object System.Drawing.SolidBrush "
        "([System.Drawing.Color]::FromArgb(255, 90, 90, 90))), 16, 60, 8, 270)",
        "$g.FillRectangle((New-Object System.Drawing.SolidBrush "
        "([System.Drawing.Color]::FromArgb(255, 90, 90, 90))), 40, 60, 8, 270)",
        f"$b.Save('{os.path.join(ordner, COWL_BILD)}', "
        "[System.Drawing.Imaging.ImageFormat]::Png)",
        "$m = New-Object System.Drawing.Bitmap 32, 16",
        "$h = [System.Drawing.Graphics]::FromImage($m)",
        "$h.Clear([System.Drawing.Color]::FromArgb(255, 255, 190, 0))",
        f"$m.Save('{os.path.join(ordner, COWL_MARKE)}', "
        "[System.Drawing.Imaging.ImageFormat]::Png)",
    ])


def cowl_anzeige():
    def marke(motor, x):
        return f"""
                <layer>
                    <name>Marke {motor}</name>
                    <w>{COWL_MARKE_W:.1f}</w>
                    <h>{COWL_MARKE_H}</h>
                    <texture>
                        <path>Aircraft/SenecaII/Panels/Textures/{COWL_MARKE}</path>
                        <x1>0</x1><x2>1</x2><y1>0</y1><y2>1</y2>
                    </texture>
                    <transformations>
                        <transformation>
                            <type>x-shift</type>
                            <offset>{x:.2f}</offset>
                        </transformation>
                        <transformation>
                            <type>y-shift</type>
                            <property>/controls/engines/engine[{motor}]/cowl-flaps-norm</property>
                            <scale>{COWL_AUF - COWL_ZU}</scale>
                            <offset>{COWL_ZU}</offset>
                        </transformation>
                    </transformations>
                </layer>"""

    return f"""
        <instrument>
            <name>Cowl Flaps</name>
            <x>{COWL_X}</x>
            <y>{COWL_Y}</y>
            <w>{COWL_W}</w>
            <h>{COWL_H}</h>
            <w-base>{COWL_W}</w-base>
            <h-base>{COWL_H}</h-base>
            <layers>
                <layer>
                    <name>Skala</name>
                    <w>{COWL_W}</w>
                    <h>{COWL_H}</h>
                    <texture>
                        <path>Aircraft/SenecaII/Panels/Textures/{COWL_BILD}</path>
                        <x1>0</x1><x2>1</x2><y1>0</y1><y2>1</y2>
                    </texture>
                </layer>{marke(0, -COWL_SCHIENE_X)}{marke(1, COWL_SCHIENE_X)}
            </layers>
        </instrument>
"""


def beschriftung(text, x, y):
    """2D-Panel-Instrument, das nur ein Beschriftungsbild zeigt."""
    return f"""
        <instrument>
            <name>Beschriftung {text}</name>
            <x>{x}</x>
            <y>{y}</y>
            <w>{SCHILD_W}</w>
            <h>{SCHILD_H}</h>
            <w-base>{SCHILD_W}</w-base>
            <h-base>{SCHILD_H}</h-base>
            <layers>
                <layer>
                    <name>Schild</name>
                    <w>{SCHILD_W}</w>
                    <h>{SCHILD_H}</h>
                    <texture>
                        <path>Aircraft/SenecaII/Panels/Textures/{schild_datei(text)}</path>
                        <x1>0</x1><x2>1</x2><y1>0</y1><y2>1</y2>
                    </texture>
                </layer>
            </layers>
        </instrument>
"""
# Namensschilder der Instrumente (zum Lernen; im Bedienfenster der Bruecke ein-/ausschaltbar
# ueber /elite/beschriftung). Sitzen dunkel hinterlegt auf der Oberkante des Instruments.
BESCHRIFTUNG_PROPERTY = "/elite/beschriftung"
INSTRUMENT_NAMEN = {
    "clock": "Uhr", "Airspeed Indicator": "Fahrtmesser", "Attitude Gyro": "Horizont",
    "Altimeter": "Höhenmesser", "Radar Altimeter": "Radar-Höhe",
    "ADF Coordinator": "ADF", "Turn Coordinator": "Wendezeiger",
    "Bendix King HSI": "HSI (NAV1/GPS)", "Vertical Velocity Indicator": "Variometer",
    "VOR 2 Gauge": "VOR 2 (NAV2)",
    "RPM Left Gauge": "Drehzahl L", "MP Gauge": "Ladedruck L/R",
    "RPM Right Gauge": "Drehzahl R", "Fuel Flow Gauge": "Kraftstofffluss",
    "EGT-L Gauge": "Abgastemp. L", "EGT-R Gauge": "Abgastemp. R",
    "Gyro PressureGauge": "Vakuum", "FlapTrim": "Klappen / Trimm",
}   # Tank/Oel/Strom-Leisten sind selbst beschriftet (Wunsch Nutzer)
NAME_W, NAME_H = 128, 18      # Panel-Einheiten; Bild 256x36 Pixel


def name_datei(schluessel):
    return "elite-name-" + re.sub(r"[^a-z0-9]+", "-", schluessel.lower()).strip("-") + ".png"


def erzeuge_namensschilder():
    """Je Instrument ein PNG: Text hell auf dunklem Feld, nur so breit wie der Text."""
    ordner = os.path.join(SENECA, "Panels", "Textures")
    befehle = ["$f = New-Object System.Drawing.Font 'Arial', 22, ([System.Drawing.FontStyle]::Bold), "
               "([System.Drawing.GraphicsUnit]::Pixel)"]
    for schluessel, text in INSTRUMENT_NAMEN.items():
        befehle.append(
            "$b = New-Object System.Drawing.Bitmap 256, 36; "
            "$g = [System.Drawing.Graphics]::FromImage($b); "
            "$g.TextRenderingHint = 'AntiAliasGridFit'; "
            f"$t = '{text}'; $m = $g.MeasureString($t, $f); $w = [Math]::Min(256, $m.Width + 12); "
            "$g.FillRectangle((New-Object System.Drawing.SolidBrush "
            "([System.Drawing.Color]::FromArgb(220, 20, 20, 20))), (256 - $w) / 2, 2, $w, 32); "
            "$g.DrawString($t, $f, (New-Object System.Drawing.SolidBrush "
            "([System.Drawing.Color]::FromArgb(255, 255, 210, 60))), (256 - $m.Width) / 2, "
            "(36 - $m.Height) / 2); "
            f"$b.Save('{os.path.join(ordner, name_datei(schluessel))}', "
            "[System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $b.Dispose()")
    powershell_bild(befehle)


def namensschild(schluessel):
    x, y, w, h = PANEL_PLATZ[schluessel]
    # bei kleinen Instrumenten Schild mitverkleinern (Seitenverhaeltnis bleibt)
    sw = min(NAME_W, w)
    sh = round(NAME_H * sw / NAME_W)
    return f"""
        <instrument>
            <name>Name {schluessel}</name>
            <x>{x}</x>
            <y>{y + h // 2 - sh // 2}</y>
            <w>{sw}</w>
            <h>{sh}</h>
            <w-base>{NAME_W}</w-base>
            <h-base>{NAME_H}</h-base>
            <layers>
                <layer>
                    <name>Schild</name>
                    <condition><property>{BESCHRIFTUNG_PROPERTY}</property></condition>
                    <w>{NAME_W}</w>
                    <h>{NAME_H}</h>
                    <texture>
                        <path>Aircraft/SenecaII/Panels/Textures/{name_datei(schluessel)}</path>
                        <x1>0</x1><x2>1</x2><y1>0</y1><y2>1</y2>
                    </texture>
                </layer>
            </layers>
        </instrument>
"""


# kommen nicht aufs Brett: FPS-Anzeige, Fahrwerkslampe (ist am Pro Panel)
PANEL_OHNE = {"frames per second", "GearUnsafeLight"}


def erzeuge_panel():
    text = lies(os.path.join(SENECA, "Panels", "ifr-panel.xml"))
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    gezaehlt = {}
    platziert = []

    def setze(treffer):
        block = treffer.group(0)
        name = re.search(r"<name>([^<]*)</name>", block).group(1)
        if name in PANEL_OHNE:
            return ""
        gezaehlt[name] = gezaehlt.get(name, 0) + 1
        schluessel = name if name in PANEL_PLATZ else f"{name}#{gezaehlt[name]}"
        if schluessel not in PANEL_PLATZ:
            print("WARNUNG: kein Platz fuer", schluessel)
            return block
        platziert.append(schluessel)
        x, y, w, h = PANEL_PLATZ[schluessel]
        block = re.sub(r"\s*<(x|y|w|h)(\s[^>]*)?(/>|>[^<]*</\1>)", "", block)
        return block.replace("</instrument>",
                             f"    <x>{x}</x>\n            <y>{y}</y>\n"
                             f"            <w>{w}</w>\n            <h>{h}</h>\n"
                             f"        </instrument>")

    text = re.sub(r"<instrument\b.*?</instrument>", setze, text, flags=re.S)
    erzeuge_schilder([titel for _, titel in WARNLAMPEN])
    erzeuge_cowl_bilder()
    erzeuge_namensschilder()
    schriften = "".join(beschriftung(titel, LAMPEN_XY[name][0],
                                     LAMPEN_XY[name][1] - SCHILD_UNTER_LAMPE)
                        for name, titel in WARNLAMPEN) + cowl_anzeige()
    schriften += """
        <instrument include="/Aircraft/Instruments/magcompass.xml">
            <name>Magnetkompass</name>
            <x>{}</x>
            <y>{}</y>
            <w>{}</w>
            <h>{}</h>
        </instrument>
""".format(*KOMPASS)
    # Namensschilder zuletzt, damit sie ueber den Instrumenten liegen
    schriften += "".join(namensschild(s) for s in INSTRUMENT_NAMEN if s in platziert)
    pos = text.rindex("</instruments>")
    text = text[:pos] + schriften + "    " + text[pos:]
    # Ohne <background> sucht FlightGear eine Textur "FOO" und meldet bei jedem Start einen
    # Fehler ("Panel texture: FOO"); also eine eigene einfarbige Flaeche im bisherigen Grau.
    powershell_bild([
        "$b = New-Object System.Drawing.Bitmap 16, 16",
        "$g = [System.Drawing.Graphics]::FromImage($b)",
        "$g.Clear([System.Drawing.Color]::FromArgb(255, 198, 194, 186))",
        f"$b.Save('{os.path.join(SENECA, 'Panels', 'Textures', HINTERGRUND)}', "
        "[System.Drawing.Imaging.ImageFormat]::Png)"])
    text = re.sub(r"<name>SenecaII IFR Panel</name>\s*<w>\d+</w>\s*<h>\d+</h>",
                  f"<name>SenecaII Elite Panel</name>\n"
                  f"    <background>Aircraft/SenecaII/Panels/Textures/{HINTERGRUND}</background>\n"
                  f"    <w>{PANEL_W}</w>\n    <h>{PANEL_H}</h>", text)
    fehlt = set(PANEL_PLATZ) - set(platziert)
    if fehlt:
        print("WARNUNG: nicht im Seneca-Panel gefunden:", ", ".join(sorted(fehlt)))
    schreibe(os.path.join(SENECA, "Panels", "elite-panel.xml"), mit_kopf(text))


MODELL_ORIGINAL = "<path>Aircraft/SenecaII/Models/SenecaII.xml</path>"
MODELL_ELITE = "<path>Aircraft/SenecaII/Models/SenecaII-Elite.xml</path>"


def original_set():
    return os.path.join(SENECA, "SenecaII-set.xml")


def sicherung():
    return original_set() + ".original"


def stelle_original_um():
    """Die Seneca ist ein Katalog-Paket; der Launcher zeigt eigene Varianten nicht an.
    Deshalb zeigt die normale Seneca auf das Elite-Modell (Sicherung bleibt liegen)."""
    print(setze_cockpit(True))


def setze_cockpit(elite):
    """Stellt die normale Seneca auf das Elite-Cockpit (True) oder das Original-Cockpit
    (False) um; wirkt beim naechsten FlightGear-Start. Rueckgabe = Meldung."""
    ORIGINAL_SET, SICHERUNG = original_set(), sicherung()
    text = lies(ORIGINAL_SET)
    alt, neu = (MODELL_ORIGINAL, MODELL_ELITE) if elite else (MODELL_ELITE, MODELL_ORIGINAL)
    name = "Elite-Cockpit" if elite else "Original-Cockpit"
    if neu in text:
        return f"Seneca: {name}"
    if alt not in text:
        return "WARNUNG: Modell-Pfad in SenecaII-set.xml nicht gefunden - Cockpit unveraendert"
    if not os.path.exists(SICHERUNG):
        schreibe(SICHERUNG, text)
    schreibe(ORIGINAL_SET, text.replace(alt, neu))
    return f"Seneca auf {name} umgestellt"


def entferne():
    ORIGINAL_SET, SICHERUNG = original_set(), sicherung()
    if os.path.exists(SICHERUNG):
        schreibe(ORIGINAL_SET, lies(SICHERUNG))
        os.remove(SICHERUNG)
        print("Normale Seneca wiederhergestellt.")
    for teil in (("SenecaII-elite-set.xml",), ("Models", "SenecaII-Elite.xml"),
                 ("Models", "SenecaII-Aussen.xml"),
                 ("Models", "apollo-elite.ac"), ("Models", "apollo-elite.xml"),
                 ("Models", "apollo-leer.png"),
                 ("Panels", "elite-panel.xml"),
                 *(("Panels", "Textures", schild_datei(t)) for _, t in WARNLAMPEN),
                 ("Panels", "Textures", COWL_BILD), ("Panels", "Textures", COWL_MARKE),
                 ("Panels", "Textures", HINTERGRUND),
                 *(("Panels", "Textures", name_datei(s)) for s in INSTRUMENT_NAMEN),
                 *(("Models", d) for d in elite_innen.DATEIEN),
                 ("Instruments-3d", "SwitchPanel-Elite.xml")):
        pfad = os.path.join(SENECA, *teil)
        if os.path.exists(pfad):
            os.remove(pfad)
            print("geloescht:", pfad)


def main():
    parser = argparse.ArgumentParser(description="Seneca II Elite erzeugen")
    parser.add_argument("--entfernen", action="store_true",
                        help="alles wieder loeschen, normale Seneca wiederherstellen")
    parser.add_argument("--nur-variante", action="store_true",
                        help="normale Seneca nicht umstellen (nur eigene Variante)")
    parser.add_argument("--seneca", help="Ordner der Seneca II (sonst automatisch gesucht)")
    args = parser.parse_args()
    import elite_einrichten   # hier, sonst gegenseitiger Import
    setze_seneca_ordner(args.seneca or elite_einrichten.finde_seneca())
    if not SENECA:
        raise SystemExit("Seneca II nicht gefunden - bitte im FlightGear-Launcher installieren "
                         "oder mit --seneca angeben.")
    print("Seneca:", SENECA)
    if args.entfernen:
        entferne()
    else:
        erzeuge()
        erzeuge_panel()
        if not args.nur_variante:
            stelle_original_um()


if __name__ == "__main__":
    main()
