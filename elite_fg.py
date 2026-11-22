"""Bruecke Elite-Hardware -> FlightGear (generic protocol ueber UDP).

Liest Pro Panel II und Ruderpedale gleichzeitig. Ein Geraet, das fehlt oder
vom USB faellt, wird jede Sekunde neu gesucht; bis dahin gehen Neutralwerte raus.

Schreibt ausserdem die COM/NAV-Frequenzen aus FlightGear auf das AP-3000.

FlightGear starten mit:
  --generic=socket,in,30,127.0.0.1,5010,udp,elite
  --generic=socket,out,10,127.0.0.1,5011,udp,elite_aus
(elite.xml muss in $FG_ROOT/Protocol liegen.)

Beispiele:
  python elite_fg.py
  python elite_fg.py --zeigen          # gesendete Werte mit ausgeben
"""

import argparse
import collections
import copy
import json
import math
import os
import socket
import sys
import time
import urllib.request

import elite_avionik as avionik
from elite_rohdaten import Dekoder, d2xx, lies_verfuegbar, oeffne

PRO_PANEL = "BR200000"
PEDALE = "BR800000"
AP3000 = "BR000000"

# Reihenfolge = Reihenfolge der <chunk>s in elite.xml.
# hebel: (Geraet, Code, Name, "hebel", Rohwert fuer 0.0, Rohwert fuer 1.0, Neutralwert)
#        vertauschte Grenzen drehen die Richtung um. Hebel vorn = kleiner Rohwert.
# ruder: (Geraet, Code, Name, "ruder", Rohwert fuer -1, Mitte, Rohwert fuer +1, Neutralwert)
ACHSEN = [
    (PRO_PANEL, 3, "Gas links", "hebel", 124, 0, 0.0),
    (PRO_PANEL, 8, "Gas rechts", "hebel", 125, 0, 0.0),
    (PRO_PANEL, 9, "Propeller links", "hebel", 116, 8, 1.0),
    (PRO_PANEL, 10, "Propeller rechts", "hebel", 127, 7, 1.0),
    (PRO_PANEL, 11, "Gemisch links", "hebel", 120, 3, 1.0),
    (PRO_PANEL, 12, "Gemisch rechts", "hebel", 127, 0, 1.0),
    (PRO_PANEL, 11, "Gemisch C172P", "hebel", 120, 3, 1.0),
    (PEDALE, 2, "Seitenruder", "ruder", 6, 70, 127, 0.0),
    (PEDALE, 13, "Bremse links", "hebel", 127, 10, 0.0),
    (PEDALE, 14, "Bremse rechts", "hebel", 127, 13, 0.0),
    (PRO_PANEL, 46, "Rudertrimmung", "ruder", 0, 60, 110, 0.0),
    # Steuerhorn: links ~15 / rechts ~116; vorn ~8 / gezogen ~120 (Ende noch geschaetzt)
    (PRO_PANEL, 0, "Querruder", "ruder", 15, 64, 116, 0.0),
    (PRO_PANEL, 1, "Hoehenruder", "ruder", 120, 61, 8, 0.0),
]

ACHS_CODES = {(a[0], a[1]) for a in ACHSEN}
# Totzone in Prozent: ruder = um die Mitte, hebel = an beiden Enden
TOTZONE_STANDARD = {"ruder": 4, "hebel": 0}
# Die sechs Hebel des Pro Panels haben eine Markierung (Raste) fuer Umkehrschub; liegt
# eine Raste im Profil, zaehlt der Bereich dahinter als Umkehr (Schub vorwaerts = 0).
RASTE_ACHSEN = ["Gas links", "Gas rechts", "Propeller links", "Propeller rechts",
                "Gemisch links", "Gemisch rechts"]
RASTE_SPIEL = 2  # Rohwerte hinter der Raste, ab denen Umkehrschub beginnt
# Gas-Hebel -> Triebwerk, das hinter der Raste Umkehrschub bekommt
UMKEHRSCHUB = {"Gas links": 0, "Gas rechts": 1}
ENTPRELLZEIT = 0.08  # Sekunden, die ein Schalterwert stabil sein muss


def aktiv_niedrig(code):
    return lambda s: int(s.get(code) == 0)


def bit(code, maske):
    return lambda s: int(bool((s.get(code) or 0) & maske))


def tabelle(code, werte):
    return lambda s: werte.get(s.get(code), 0)


# Reihenfolge = Reihenfolge der /elite/input-<chunk>s in elite.xml;
# das Add-on fg-addon/addon-main.nas setzt sie aufs Flugzeug um.
# Ohne Wert (Geraet fehlt, Taster nie gedrueckt) gilt 0 = aus.
SCHALTER = [
    ("batterie", aktiv_niedrig(60)),
    ("radio", aktiv_niedrig(61)),
    ("pitot", aktiv_niedrig(18)),
    ("parkbremse", aktiv_niedrig(42)),
    # 127 = Hebel unten; solange das Pro Panel nie gemeldet hat: unten (sonst hupt am Boden
    # die Fahrwerkswarnung bzw. das Fahrwerk faehrt ein)
    ("fahrwerk", lambda s: int(s.get(6, 127) == 127)),
    ("lima-l", bit(62, 1)),
    ("lima-r", bit(62, 2)),
    ("pumpe-l", bit(16, 1)),
    ("pumpe-r", bit(16, 2)),
    ("mag-0-l", bit(25, 8)),
    ("mag-0-r", bit(25, 32)),
    ("mag-1-l", bit(25, 4)),
    ("mag-1-r", bit(25, 16)),
    ("anlasser-0", lambda s: int(s.get(24) == 2)),
    ("anlasser-1", lambda s: int(s.get(24) == 1)),
    ("nav", bit(41, 2)),
    ("strobe", bit(41, 4)),
    ("landing", bit(41, 1)),
    ("tankwahl", tabelle(17, {3: 0, 7: 1, 11: 2, 15: 3})),  # OFF LEFT BOTH RIGHT
    ("klappen", tabelle(7, {40: 1, 0: -1})),  # +1 = Stufe runter
    # -1 = zu, +1 = auf; Wippe nach oben = auf (Wunsch Nutzer 2026-10-29)
    ("cowl-0", tabelle(43, {4: 1, 6: -1})),
    ("cowl-1", tabelle(43, {10: -1, 8: 1})),
    # +1 = Nase runter (FlightGear: Trimmung positiv); Schalter nach vorne meldet Code 4
    ("hoehentrimm", lambda s: (s.get(4) == 0) - (s.get(5) == 0)),
    ("alt-static", aktiv_niedrig(63)),
    ("reserve", aktiv_niedrig(73)),
    # Druckknoepfe an den Hoernern (Elite: Code 20 "Radio But.", 21 "CWS")
    ("sprechtaste", aktiv_niedrig(20)),
    ("cws", aktiv_niedrig(21)),
]
SCHALTER_CODES = {60, 61, 18, 42, 6, 62, 16, 25, 24, 41, 17, 7, 43, 4, 5, 63, 73, 20, 21}
# Hebel, deren letzte Stellung gilt, wenn das Pro Panel ausgeschaltet wird (Fahrwerk)
BEHALTEN = {6}
# Namen fuer den Schalter-Test im Bedienfenster
GERAETE_NAMEN = {PRO_PANEL: "Pro Panel", PEDALE: "Pedale", AP3000: "AP-3000"}
CODE_NAMEN = {
    (PRO_PANEL, 60): "Batterie", (PRO_PANEL, 61): "Radio-Master", (PRO_PANEL, 18): "Pitot",
    (PRO_PANEL, 42): "Parkbremse", (PRO_PANEL, 6): "Fahrwerkshebel",
    (PRO_PANEL, 62): "Lichtmaschinen", (PRO_PANEL, 16): "Benzinpumpen",
    (PRO_PANEL, 25): "Magnete", (PRO_PANEL, 24): "Anlasser", (PRO_PANEL, 41): "Licht",
    (PRO_PANEL, 17): "Tankwahl", (PRO_PANEL, 7): "Klappen-Taster",
    (PRO_PANEL, 43): "Cowl-Flaps-Wippen", (PRO_PANEL, 4): "Hoehentrimm (Horn)",
    (PRO_PANEL, 5): "Hoehentrimm (Horn)", (PRO_PANEL, 63): "Alt. Static",
    (PRO_PANEL, 73): "Reserve-Schalter: Rollscheinwerfer (Taxi)", (PRO_PANEL, 20): "Sprechtaste (Horn): AP aus",
    (PRO_PANEL, 21): "CWS (Horn)",
    (AP3000, 30): "Drehknopf COM/NAV/ADF/DME", (AP3000, 31): "Taster / DME-Wahl",
    (AP3000, 32): "DME-Schalter", (AP3000, 33): "HDG/MDI-Knopf", (AP3000, 34): "CRS-Knopf",
    (AP3000, 38): "Autopilot-Taste", (AP3000, 39): "Trimm-Wippe AP", (AP3000, 57): "TEST-Taste",
    (AP3000, 35): "QNH-Knopf", (AP3000, 36): "NAV2-Knopf", (AP3000, 121): "FREEZE",
    (AP3000, 55): "SET-Knopf: AP-Nickrad", (AP3000, 56): "Hoehenvorwahl ENG/ARM, V/S",
    (AP3000, 122): "INSTR/MAP", (AP3000, 22): "Transponder-Knopf", (AP3000, 23): "Transponder-Modus/IDENT",
    (AP3000, 51): "GPS", (AP3000, 52): "GPS", (AP3000, 53): "GPS",
}
# Apollo-GPS-Tasten am AP-3000 (Code -> Bit bzw. Wert -> Taste)
GPS_TASTEN = {
    51: {1: "nav", 2: "nrst", 4: "onoff", 8: "info", 16: "soft5"},
    52: {1: "soft4", 2: "soft3", 4: "soft2", 8: "soft1", 16: "navgps", 32: "sel"},
    53: {9: "enter", 17: "direct", 33: "map", 65: "seq"},
}
# AP-3000-Codes, bei denen jede Meldung zaehlt (Drehgeber: eine Meldung pro Raste)
DREHGEBER = {22, 30, 33, 34, 35, 36, 53, 55}
# Wippen/Taster mit Richtung (-1/+1), deren Richtung sich per Einstellung umdrehen laesst
UMKEHRBAR = {"klappen": "Klappen-Taster", "cowl-0": "Cowl Flaps links",
             "cowl-1": "Cowl Flaps rechts", "hoehentrimm": "Hoehentrimm (Horn)"}

# --- Einstellungen (Kalibrierung, Richtungen) je Flugzeug-Profil --------------------
# Profilname = FlightGear-Flugzeug (/sim/aircraft, z.B. "SenecaII", "c172p");
# "standard" gilt fuer alle Flugzeuge ohne eigenes Profil.
EINSTELLUNGEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "einstellungen.json")


def standard_profil():
    achsen = {}
    for geraet, code, name, art, *grenzen, neutral in ACHSEN:
        achsen[name] = {"grenzen": list(grenzen), "umkehren": False,
                        "totzone": TOTZONE_STANDARD[art], "kurve": 0, "raste": None}
    # trimm_tempo: Hoehentrimm-Tempo, 1 = FlightGear-Standard (C172P); die Seneca braucht ~3
    return {"achsen": achsen, "umkehren": dict.fromkeys(UMKEHRBAR, False), "trimm_tempo": 1.0}


def lade_einstellungen():
    daten = {"profile": {}, "start": {}}
    try:
        with open(EINSTELLUNGEN, encoding="utf-8") as f:
            daten.update(json.load(f))
    except (OSError, ValueError):
        pass
    vorlage = standard_profil()
    daten["profile"].setdefault("standard", copy.deepcopy(vorlage))
    for profil in daten["profile"].values():
        # neue Achsen/Wippen aus spaeteren Versionen ergaenzen
        for name, werte in vorlage["achsen"].items():
            eintrag = profil.setdefault("achsen", {}).setdefault(name, copy.deepcopy(werte))
            for schluessel, wert in werte.items():
                eintrag.setdefault(schluessel, copy.deepcopy(wert))
        for name in UMKEHRBAR:
            profil.setdefault("umkehren", {}).setdefault(name, False)
        profil.setdefault("trimm_tempo", 1.0)
    return daten


def speichere_einstellungen(daten):
    with open(EINSTELLUNGEN, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)


# Zustaende von Tastern, die sich die Hardware nicht selbst merkt (z. B. OFF-Taster der
# Funkgeraete am AP-3000); ueberstehen Neustarts von Bruecke und FlightGear
ZUSTAND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zustand.json")


def lade_zustand():
    try:
        with open(ZUSTAND, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def speichere_zustand(**werte):
    daten = lade_zustand()
    daten.update(werte)
    try:
        with open(ZUSTAND, "w", encoding="utf-8") as f:
            json.dump(daten, f)
    except OSError as fehler:
        print("Zustand nicht gespeichert:", fehler, flush=True)


class Entpreller:
    """Uebernimmt einen Schalterwert erst, wenn er ENTPRELLZEIT lang stabil anliegt."""

    def __init__(self):
        self.stabil = {}
        self.kandidat = {}

    def aktualisiere(self, roh, jetzt):
        for code in SCHALTER_CODES:
            wert = roh.get((PRO_PANEL, code))
            if wert is None:
                # Pro Panel aus (Schluessel) oder getrennt: Schalter gelten als aus, der
                # Fahrwerkshebel bleibt aber stehen, wo er war
                if code not in BEHALTEN:
                    self.stabil.pop(code, None)
                self.kandidat.pop(code, None)
                continue
            alt, seit = self.kandidat.get(code, (None, jetzt))
            if wert != alt:
                self.kandidat[code] = (wert, jetzt)
            elif jetzt - seit >= ENTPRELLZEIT:
                self.stabil[code] = wert


def normiere(roh, unten, oben):
    anteil = (roh - unten) / (oben - unten)
    return min(1.0, max(0.0, anteil))


def normiere_ruder(roh, minus, mitte, plus):
    ende = plus if (roh - mitte) * (plus - mitte) > 0 else minus
    anteil = (roh - mitte) / (ende - mitte)
    return min(1.0, anteil) * (1 if ende == plus else -1)


class Geraet:
    """Ein Elite-Geraet, das sich nach USB-Aussetzern selbst neu verbindet."""

    def __init__(self, seriennr, name):
        self.seriennr = seriennr
        self.name = name
        self.handle = None
        self.dekoder = Dekoder()
        self.naechster_versuch = 0.0
        self.gemeldet_fehlt = False
        self.protokoll = None  # deque: (Zeit, Geraet, Code, Wert) bei Schalter-Aenderungen

    def lies(self, roh):
        if self.handle is None:
            if time.monotonic() < self.naechster_versuch:
                return
            try:
                self.handle, _ = oeffne(self.seriennr, 38400)
                self.dekoder = Dekoder()
                self.gemeldet_fehlt = False
                print(f"{self.name} ({self.seriennr}) verbunden.", flush=True)
            except RuntimeError:
                if not self.gemeldet_fehlt:
                    print(f"{self.name} ({self.seriennr}) nicht gefunden, suche weiter ...",
                          flush=True)
                    self.gemeldet_fehlt = True
                self.naechster_versuch = time.monotonic() + 1
                return
        try:
            daten = lies_verfuegbar(self.handle)
        except RuntimeError as fehler:
            print(f"{self.name}: {fehler} - verbinde neu ...", flush=True)
            self.schliesse()
            for schluessel in [s for s in roh if s[0] == self.seriennr]:
                del roh[schluessel]
            return
        for code, wert in self.dekoder.fuettere(daten):
            schluessel = (self.seriennr, code)
            alt = roh.get(schluessel)
            if (self.protokoll is not None and alt is not None and alt != wert
                    and schluessel not in ACHS_CODES):
                self.protokoll.append((time.time(), self.seriennr, code, wert))
            roh[schluessel] = wert

    def sende(self, daten):
        if self.handle is None:
            return
        try:
            avionik.schreibe(self.handle, daten)
        except RuntimeError as fehler:
            print(f"{self.name}: {fehler} - verbinde neu ...", flush=True)
            self.schliesse()

    def schliesse(self):
        if self.handle is not None:
            d2xx.FT_Close(self.handle)
            self.handle = None


# Frequenzen aus FlightGear (elite_aus.xml, gleiche Reihenfolge) -> AP-3000-Datensatz-Typ
# Reihe 1: L COM1 aktiv, M COM1 standby, A NAV1 aktiv, B NAV1 standby;
# Reihe 2: N, O, D, E entsprechend.
AUSGABE = ["L", "M", "N", "O", "A", "B", "D", "E"]

# Bedienelemente des AP-3000 als Zaehler; Reihenfolge = /elite/input-Chunks in elite.xml.
# Jede Raste/jeder Druck aendert einen Zaehler, das Add-on wendet die Differenz an.
ZAEHLER = ["com1-grob", "com1-fein", "com2-grob", "com2-fein",
           "nav1-grob", "nav1-fein", "nav2-grob", "nav2-fein",
           "adf-grob", "adf-fein",
           "com1-tausch", "com2-tausch", "nav1-tausch", "nav2-tausch", "adf-tausch",
           "xpdr-0", "xpdr-1", "xpdr-2", "xpdr-3",  # Transponder-Ziffer 0 = Einer
           "ap-eng", "ap-hdg", "ap-nav", "ap-apr", "ap-bc", "ap-alt", "ap-fd",
           "hdg", "crs",  # Drehknoepfe unterste Reihe: Heading Bug, Kurs NAV1
           "dme-grob", "dme-fein",  # eigene DME-Frequenz
           "mdi", "obs2", "qnh",  # ADF-Rose, Kurs NAV2, Hoehenmesser (hPa)
           "freeze",  # FREEZE-Taste: Pause ein/aus
           "nick",  # SET-Knopf: Nickrad des Century III
           # ADF-Reihe (KR87): ADF/ANT, BFO, FLT/ET, SET (Zeit zuruecksetzen), IDENT
           "adf-modus", "adf-bfo", "adf-flt", "adf-set", "adf-ident"]
# Autopilot-Tasten (Code 38, Wert beim Druecken) -> Zaehler
AP_TASTEN = {1: "ap-eng", 2: "ap-bc", 4: "ap-apr", 8: "ap-nav", 16: "ap-hdg",
             32: "ap-alt", 64: "ap-fd"}
# Lampen im Datensatz T (Lampenwort, am Geraet zugeordnet)
AP_LAMPE = {"ap": 1, "trim": 2, "bc": 4, "apr": 8, "nav": 16, "gs": 32, "hdg": 64,
            "alt": 128, "fd": 256}
# Transponder-Modusschalter (Code 23 = 4 + 8 * Stellung: OFF 4, SBY 12, ON 20, ALT 28,
# TEST 36) -> FlightGear knob-mode (OFF 0, SBY 1, ON 4, ALT 5, TST 2)
XPDR_MODUS = {0: 0, 1: 1, 2: 4, 3: 5, 4: 2}
# Code 31 (Taster): Wert beim Druecken -> Zaehler (Geraet in Bits 0-1, siehe Lernliste)
TASTEN = {20: "com1-tausch", 21: "com2-tausch", 16: "nav1-tausch", 17: "nav2-tausch",
          18: "adf-tausch", 10: "adf-bfo", 34: "adf-ident"}
# ADF-Reihe, angelernt 2026-11-11 (alle Tasten federn zurueck): ADF = Code 32 Wert 66
# (losgelassen 2), FLT / SET = Code 54 Wert 2 / 1 (losgelassen 0)
ADF_TASTE_32 = 66
ADF_TIMER_TASTEN = {2: "adf-flt", 1: "adf-set"}
# Schriftzuege der ADF-Anzeige im Datensatz 'F' (2. Byte), am Geraet zugeordnet
ADF_SCHRIFT = {"adf": 1, "ant": 2, "bfo": 4, "frq": 8, "flt": 16, "et": 32, "block2": 64}
# DME (Reihe 4): Wahlschalter = Ruhewert von Code 31, Schalter R1/R2/OFF = einer der
# zwei abwechselnden Werte von Code 32
DME_WAHL = {70: "rmt", 38: "freq", 22: "gs/t"}
DME_SCHALTER = {19: "r1", 35: "r2", 67: "off"}
# Beschriftungen im Datensatz I (2. Byte), am Geraet zugeordnet; 4. Byte 1 = DME an
DME_LAMPE = {"nm": 1, "rmt": 2, "kt": 8, "mhz": 16, "min": 32}


# Licht-Schalter am Pro Panel (Code 41, ein Bit je Schalter) -> FlightGear
LICHT_SCHALTER = [(1, "LANDING (Landescheinwerfer)"), (2, "NAV (Positionslichter + Instrumente, nur mit Strom)"),
                  (4, "STROBE (Blitzlicht)")]


def pro_panel_klartext(code, wert):
    """Genaue Bezeichnung einer Pro-Panel-Meldung fuer den Schalter-Test."""
    if code == 41:
        an = [name for maske, name in LICHT_SCHALTER if wert & maske]
        return "Licht an: " + ", ".join(an) if an else "Licht: alle aus"
    return None


def ap3000_klartext(code, wert):
    """Genaue Bezeichnung einer AP-3000-Meldung fuer den Schalter-Test (welche Taste,
    welche Richtung); None, wenn der Code nicht naeher bekannt ist."""
    dreh = "rechts" if wert & 8 else "links"
    if code == 30:
        geraet = wert & 3
        name = ("ADF" if geraet == 2 else "DME" if geraet == 3
                else ("COM" if wert & 4 else "NAV") + str(geraet + 1))
        return f"Frequenzknopf {name} {'innen (fein)' if wert & 16 else 'aussen (grob)'} {dreh}"
    if code == 31:
        if wert in (10, 34):
            return {10: "ADF-Reihe: BFO-Taste", 34: "ADF-Reihe: IDENT-Taste"}[wert]
        if wert == 2:
            return "ADF-Reihe: Taste losgelassen"
        if wert in TASTEN:
            return "Tauschtaste " + TASTEN[wert].split("-")[0].upper()
        if wert in (64, 65):
            return f"OFF-Taste COM/NAV {wert - 63}"
        if wert in DME_WAHL:
            return "losgelassen, DME-Wahl " + DME_WAHL[wert].upper()
        return None
    if code == 32:
        if wert == ADF_TASTE_32:
            return "ADF-Reihe: ADF-Taste (ADF/ANT)"
        return "DME-Schalter " + DME_SCHALTER[wert].upper() if wert in DME_SCHALTER else None
    if code == 54:
        return {2: "ADF-Reihe: FLT-Taste (FLT/ET)", 1: "ADF-Reihe: SET-Taste"}.get(
            wert, "ADF-Reihe: FLT/SET losgelassen")
    if code == 33:
        return ("MDI-Knopf (ADF-Rose) " if wert & 64 else "HDG-Knopf (Heading Bug) ") + dreh
    if code == 34:
        return f"CRS-Knopf (Kurs NAV1) {dreh}, Kippschalter auf {'OBS' if wert & 64 else 'CRS'}"
    if code in (35, 36, 55):
        return {35: "QNH-Knopf", 36: "NAV2-Knopf (Kurs NAV2)",
                55: "SET-Knopf (AP-Nickrad)"}[code] + " " + dreh
    if code == 38:
        if wert in AP_TASTEN:
            return "AP-Taste " + AP_TASTEN[wert][3:].upper()
        return "AP-Taste losgelassen"
    if code == 39:
        return {40: "AP-Trimmwippe unten", 0: "AP-Trimmwippe oben"}.get(wert, "AP-Trimmwippe Ruhe")
    if code in (51, 52):
        tasten = [name for maske, name in GPS_TASTEN[code].items() if wert & maske]
        return "GPS-Taste " + ", ".join(t.upper() for t in tasten) if tasten else "GPS-Taste losgelassen"
    if code == 53:
        if wert & 1:
            name = GPS_TASTEN[53].get(wert)
            return "GPS-Taste " + name.upper() if name else "GPS-Taste losgelassen"
        return f"GPS-Knopf {'aussen' if wert & 16 else 'innen'} {dreh}"
    if code == 56:
        taste = {1: "ENG", 2: "ARM"}.get(wert & 3)
        return (f"Hoehenvorwahl {taste}, " if taste else "") + \
            ("Kippschalter V/S" if wert & 4 else "Kippschalter ALT")
    if code == 57:
        return "TEST-Taste gedrueckt" if wert == 0 else "TEST-Taste losgelassen"
    if code == 121:
        return "FREEZE gedrueckt" if wert == 0 else "FREEZE losgelassen"
    if code == 122:
        return {1: "INSTR-Taste (Bordcomputer/Checkliste)",
                2: "MAP-Taste (Navi Text/Karte)"}.get(wert, "INSTR/MAP losgelassen")
    if code == 22:
        return f"Transponder-Knopf Stelle {4 - (wert & 3)} (von links) {dreh}"
    if code == 23:
        if wert & 1:
            return "Transponder IDENT"
        stellung = ["OFF", "SBY", "ON", "ALT", "TEST"]
        return "Transponder-Schalter " + (stellung[wert >> 3] if wert >> 3 < 5 else "?")
    return None


class Avionik:
    """Schreibt Frequenzen schonend auf das AP-3000: nur Aenderungen, ein Datensatz
    pro Paket, mit Pause; alle paar Sekunden wird alles einmal aufgefrischt."""

    def __init__(self, seriennr, name):
        self.seriennr = seriennr
        self.name = name
        self.handle = None
        self.naechster_versuch = 0.0
        self.gemeldet_fehlt = False
        # ' ' = Strom-Zustand; '@' / 'C' = Zustand Funkgeraet 1 / 2, letztes Bit = an.
        # Ohne sie bleiben Reihe 1 und 2 dunkel.
        self.soll = {                # Typ -> Datensatz (bytes)
            " ": avionik.satz(" ", 3, 3, 0, 3),
            "@": avionik.satz("@", 0, 0, 0, 1),
            "C": avionik.satz("C", 0, 0, 0, 1),
            # ADF-Reihe an; 2. Byte: Bit 1 = ADF statt ANT (setzt der Elite-Treiber immer),
            # Bit 8 = FRQ-Schriftzug, Bit 64 = Block 2 an
            "F": avionik.satz("F", 0, 73, 0, 1),
        }
        self.gesendet = {}
        self.offen = []             # Typen, die noch gesendet werden muessen
        self.naechstes_paket = 0.0
        self.letzte_auffrischung = 0.0
        self.dekoder = Dekoder()
        self.zaehler = dict.fromkeys(ZAEHLER, 0)
        self.letzte_taste = None
        self.strom = True            # Batterie und Radio-Master am Pro Panel
        # COM/NAV 1 und 2, umgeschaltet per OFF-Taster; bleibt ueber Neustarts gespeichert
        # (wie im echten Flugzeug: ausgeschaltet bleibt aus, bis man wieder einschaltet)
        self.geraet_an = lade_zustand().get("funk_an", [True, True])
        self.xpdr_modus = None       # FlightGear knob-mode laut Schalter (None = unbekannt)
        self.xpdr_ident = 0
        self.xpdr_an = True          # Transponder laut FlightGear nicht auf OFF
        self.ap_lampen = 0           # Lampenwort aus dem Zustand des Century III
        self.ap_trimm = 0            # weisse Wippe: -1 rauf, 0 Ruhe, +1 runter
        self.letzte_ap_taste = 0
        self.lampentest = False      # TEST-Taste: alle AP-Lampen an
        self.dme_wahl = None         # "rmt" / "freq" / "gs/t" (None = noch unbekannt)
        self.dme_schalter = None     # "r1" / "r2" / "off"
        self.dme_werte = None        # aus FlightGear: eigene MHz, NM, kt, min, in Reichweite
        self.fahrwerk = None         # aus FlightGear: Stellung Bug, links, rechts (0..1)
        self.adf_taste = False       # ADF-Taste gerade gedrueckt
        self.letzte_adf_zeit = None
        self.adf_schrift = None      # aus FlightGear: Schriftzuege der ADF-Anzeige (Bits)
        self.marker = (0, 0, 0)      # aus FlightGear: Marker aussen, Mitte, innen
        self.ap_trimmt = False       # aus FlightGear: Trimm-Servo des Autopiloten laeuft
        # Tasten INSTR / MAP der untersten Reihe fuer das Bedienfenster ("instr" / "map")
        self.anzeige_ereignisse = collections.deque(maxlen=20)
        self.letzte_anzeige_taste = None
        self.protokoll = None        # wie Geraet.protokoll
        self.letzte_werte = {}       # Code -> letzter Wert (fuer das Protokoll)
        self.letzter_freeze = None
        # Apollo-Tasten und -Knopf fuer den GPS-Bildschirm (elite_gps.py holt sie ab):
        # Taste "nrst" ... oder ("fein"/"grob", +1/-1)
        self.gps_ereignisse = collections.deque(maxlen=50)
        self.gps_alt = {51: 0, 52: 0, 53: 1}

    def merke(self, code, wert):
        """Fuers Protokoll: Drehgeber jede Meldung, sonst nur Aenderungen."""
        if code == 32 and wert not in DME_SCHALTER and wert != ADF_TASTE_32:
            return  # der DME-Schalter meldet sich staendig abwechselnd mit 8
        alt = self.letzte_werte.get(code)
        if code == 32 and wert == ADF_TASTE_32:
            alt = -1    # jeder Druck der ADF-Taste zaehlt (dazwischen kommt nichts Neues)
        self.letzte_werte[code] = wert
        if self.protokoll is not None and (code in DREHGEBER or (alt is not None
                                                                 and alt != wert)):
            self.protokoll.append((time.time(), self.seriennr, code, wert))

    def dme_quelle(self):
        """Seneca KI266 switch-position: 1 NAV1, 2 eigene Frequenz (HLD), 3 NAV2;
        0 = DME aus, -1 = Schalter noch unbekannt. Wie beim KN62A: RMT nimmt die
        Frequenz von NAV1/NAV2 (R1/R2), FREQ und GS/T die eigene."""
        if self.dme_schalter is None or self.dme_wahl is None:
            return -1
        if self.dme_schalter == "off":
            return 0
        if self.dme_wahl == "rmt":
            return 1 if self.dme_schalter == "r1" else 3
        return 2

    def setze_dme(self):
        """'I' = DME an + Beschriftungen, 'J' = Entfernung (Zehntel NM, 16 Bit) und
        rechts entweder Frequenz (MHz, Hundertstel) oder kt / min."""
        quelle = self.dme_quelle()
        if not self.strom or quelle == 0:
            self.soll["I"] = avionik.satz("I", 0, 0, 0, 0)
            return
        freq = self.dme_wahl == "freq"
        if freq:
            lampen = DME_LAMPE["nm"] | DME_LAMPE["mhz"]
        else:
            lampen = DME_LAMPE["nm"] | DME_LAMPE["kt"] | DME_LAMPE["min"]
            if self.dme_wahl == "rmt":
                lampen |= DME_LAMPE["rmt"]
        self.soll["I"] = avionik.satz("I", 0, lampen, 0, 1)
        mhz, nm, kt, minuten, in_reichweite = self.dme_werte or (0, 0, 0, 0, 0)
        if not in_reichweite:
            nm = kt = minuten = 0
        zehntel = max(0, min(9999, round(nm * 10)))
        if freq:
            ganz = int(mhz)
            rechts = (ganz & 0xFF, int((mhz - ganz) * 100 + 1e-6))
        else:
            rechts = (max(0, min(255, round(kt))), max(0, min(99, round(minuten))))
        self.soll["J"] = avionik.satz("J", zehntel >> 8, zehntel & 0xFF, *rechts)

    def setze_zustand(self):
        """'@' / 'C' / 'F' = Funkgeraet 1 / 2 / ADF an oder aus (0 0 0 0 = dunkel)."""
        self.soll["R"] = avionik.satz(
            "R", 0, 2 if self.strom and self.xpdr_an else 0, 4, 0)
        lampen = 0
        if self.strom:
            lampen = self.ap_lampen | (AP_LAMPE["trim"] if self.ap_trimmt else 0)
        if self.lampentest:
            lampen = 0x1FF
        self.soll["T"] = avionik.satz("T", lampen >> 8, lampen & 0xFF, 255, 255)
        # Marker-Lampen A / O / M am Apollo (Datensatz '!': Bytes 2-4; Reihenfolge der
        # Lampen angenommen, am Geraet noch zu pruefen): A = inneres, O = aeusseres,
        # M = mittleres Zeichen; die TEST-Taste schaltet alle drei ein
        aussen, mitte, innen = (1, 1, 1) if self.lampentest else \
            (self.marker if self.strom else (0, 0, 0))
        self.soll["!"] = avionik.satz("!", 0, int(bool(innen)), int(bool(aussen)),
                                      int(bool(mitte)))
        zustand = (self.strom, *self.geraet_an)
        if zustand != getattr(self, "_letzter_zustand", None):
            print(f"Avionik: Strom {'an' if self.strom else 'aus'}, "
                  f"Geraet 1 {'an' if self.geraet_an[0] else 'aus'}, "
                  f"Geraet 2 {'an' if self.geraet_an[1] else 'aus'}", flush=True)
            self._letzter_zustand = zustand
            # nach Ein/Aus braucht das Geraet alle Anzeigen neu -> sofort alles senden
            self.gesendet.clear()
            self.offen = []
        # ADF-Reihe: Block 2 an + Schriftzuege laut FlightGear (ohne Angabe: ADF und FRQ)
        schrift = self.adf_schrift or (ADF_SCHRIFT["adf"] | ADF_SCHRIFT["frq"])
        for typ, an, wert in (("@", self.strom and self.geraet_an[0], (0, 0, 0, 1)),
                              ("C", self.strom and self.geraet_an[1], (0, 0, 0, 1)),
                              ("F", self.strom, (0, ADF_SCHRIFT["block2"] | schrift, 0, 1))):
            self.soll[typ] = avionik.satz(typ, *(wert if an else (0, 0, 0, 0)))
        self.setze_dme()

    def verarbeite(self, code, wert):
        """Uebersetzt Meldungen des AP-3000 in Zaehler-Aenderungen."""
        if code == 30:
            # Drehgeber, eine Meldung pro Raste: Bits 0-1 Geraet, Bit 2 COM (sonst NAV),
            # Bit 3 rechts, Bit 4 fein
            geraet = wert & 3
            if geraet == 2:
                name = "adf"
            elif geraet < 2:
                name = ("com" if wert & 4 else "nav") + str(geraet + 1)
            else:
                name = "dme"
            schluessel = name + ("-fein" if wert & 16 else "-grob")
            self.zaehler[schluessel] += 1 if wert & 8 else -1
        elif code == 38:
            # Autopilot-Tasten: nur der Wechsel auf einen Druck-Wert zaehlt
            if wert != self.letzte_ap_taste and wert in AP_TASTEN:
                self.zaehler[AP_TASTEN[wert]] += 1
            self.letzte_ap_taste = wert
        elif code == 39:
            # weisse Wippe (Trimmung): unten 40, oben 0, Ruhe 127
            self.ap_trimm = {40: 1, 0: -1}.get(wert, 0)
        elif (code, wert & 64) == (33, 0) or code == 34:
            # unterste Reihe: Code 33 ohne Bit 6 = HDG (mit = MDI), Code 34 = CRS-Knopf;
            # Bit 3 rechts. Bit 6 von Code 34 ist nur die Stellung des CRS/OBS-Kippschalters
            # (CRS = ohne, andere Stellung = mit; angelernt 2026-11-11) - der Schalter selbst
            # meldet nichts. Die Seneca hat nur einen Kurs fuer NAV1, also beide gleich.
            self.zaehler["hdg" if code == 33 else "crs"] += 1 if wert & 8 else -1
        elif code in (33, 35, 36, 55):
            # MDI-Knopf (33 mit Bit 6), QNH-Knopf oben rechts (35), NAV2-Knopf (36),
            # SET-Knopf der Hoehenvorwahl (55) als Nickrad
            name = {33: "mdi", 35: "qnh", 36: "obs2", 55: "nick"}[code]
            self.zaehler[name] += 1 if wert & 8 else -1
        elif code == 121:
            # FREEZE: 0 gedrueckt, 127 Ruhe; nur der Druck zaehlt
            if wert == 0 and self.letzter_freeze != 0:
                self.zaehler["freeze"] += 1
            self.letzter_freeze = wert
        elif code in (51, 52):
            # Apollo-Tasten: je Bit eine Taste, Ruhe 0; neu gesetzte Bits = gedrueckt
            neu = wert & ~self.gps_alt[code]
            for maske, name in GPS_TASTEN[code].items():
                if neu & maske:
                    self.gps_ereignisse.append(name)
            self.gps_alt[code] = wert
        elif code == 53:
            if wert & 1:
                # Tasten mit Bit 0 (Ruhe 1)
                if wert != self.gps_alt[53] and wert in GPS_TASTEN[53]:
                    self.gps_ereignisse.append(GPS_TASTEN[53][wert])
                self.gps_alt[53] = wert
            else:
                # grosser Knopf: Bit 4 grob (aussen), Bit 3 rechts
                self.gps_ereignisse.append(("grob" if wert & 16 else "fein",
                                            1 if wert & 8 else -1))
        elif code == 57:
            # TEST-Taste: 0 gedrueckt, 127 losgelassen
            self.lampentest = wert == 0
        elif code == 122:
            # INSTR 1, MAP 2, Ruhe 127: nur der Druck zaehlt. Das Bedienfenster schaltet
            # damit Bordcomputer/Checkliste bzw. Navi-Text/Karte um.
            if wert != self.letzte_anzeige_taste and wert in (1, 2):
                self.anzeige_ereignisse.append("instr" if wert == 1 else "map")
            self.letzte_anzeige_taste = wert
        elif code == 22:
            # Transponder-Ziffernknopf: Bits 0-1 Stelle (0 = Einer), Bit 3 rechts
            self.zaehler[f"xpdr-{wert & 3}"] += 1 if wert & 8 else -1
        elif code == 23:
            # Transponder-Modusschalter (Zustand). Bit 0 = IDENT gedrueckt; dann sind die
            # Stellungs-Bits unzuverlaessig (13, 5 ...) -> Modus beibehalten
            self.xpdr_ident = wert & 1
            if not self.xpdr_ident:
                self.xpdr_modus = XPDR_MODUS.get(wert >> 3, self.xpdr_modus)
        elif code == 32 and wert in DME_SCHALTER:
            self.dme_schalter = DME_SCHALTER[wert]
        elif code == 32 and wert in (ADF_TASTE_32, 2):
            # ADF-Taste (schaltet ADF <-> ANT): 66 gedrueckt, 2 losgelassen
            if wert == ADF_TASTE_32 and not self.adf_taste:
                self.zaehler["adf-modus"] += 1
            self.adf_taste = wert == ADF_TASTE_32
        elif code == 54:
            # ADF-Zeitmesser: FLT 2, SET 1, losgelassen 0; nur der Druck zaehlt
            if wert != self.letzte_adf_zeit and wert in ADF_TIMER_TASTEN:
                self.zaehler[ADF_TIMER_TASTEN[wert]] += 1
            self.letzte_adf_zeit = wert
        elif code == 31:
            # Taster: nur der Wechsel auf einen Druck-Wert zaehlt (Ruhewert wird
            # im Komplettabzug immer wieder gemeldet; er ist die DME-Wahl)
            if wert in DME_WAHL:
                self.dme_wahl = DME_WAHL[wert]
            if wert != self.letzte_taste:
                if wert in TASTEN:
                    self.zaehler[TASTEN[wert]] += 1
                elif wert in (64, 65):  # OFF-Taster COM/NAV 1 bzw. 2
                    self.geraet_an[wert - 64] = not self.geraet_an[wert - 64]
                    speichere_zustand(funk_an=self.geraet_an)
            self.letzte_taste = wert

    def setze(self, typ, mhz):
        self.soll[typ] = avionik.frequenz(typ, mhz)

    def arbeite(self):
        jetzt = time.monotonic()
        if self.handle is None:
            if jetzt < self.naechster_versuch:
                return
            try:
                self.handle, _ = oeffne(self.seriennr, 38400)
                self.gesendet.clear()
                self.dekoder = Dekoder()
                self.gemeldet_fehlt = False
                print(f"{self.name} ({self.seriennr}) verbunden.", flush=True)
            except RuntimeError:
                if not self.gemeldet_fehlt:
                    print(f"{self.name} ({self.seriennr}) nicht gefunden, suche weiter ...",
                          flush=True)
                    self.gemeldet_fehlt = True
                self.naechster_versuch = jetzt + 1
                return
        try:
            for code, wert in self.dekoder.fuettere(lies_verfuegbar(self.handle)):
                self.merke(code, wert)
                self.verarbeite(code, wert)
        except RuntimeError as fehler:
            print(f"{self.name}: {fehler} - verbinde neu ...", flush=True)
            self.schliesse()
            return
        self.setze_zustand()
        if jetzt < self.naechstes_paket:
            return
        # Aenderungen haben Vorrang; aufgefrischt wird nur, wenn nichts Neues ansteht
        geaendert = [t for t, s in self.soll.items() if self.gesendet.get(t) != s]
        if geaendert:
            typ = geaendert[0]
        else:
            if not self.offen:
                if jetzt - self.letzte_auffrischung < avionik.AUFFRISCHEN:
                    return
                self.offen = list(self.soll)
                self.letzte_auffrischung = jetzt
            typ = self.offen.pop(0)
        try:
            avionik.schreibe(self.handle, avionik.paket([self.soll[typ]]))
        except RuntimeError as fehler:
            print(f"{self.name}: {fehler} - verbinde neu ...", flush=True)
            self.schliesse()
            return
        self.gesendet[typ] = self.soll[typ]
        self.naechstes_paket = jetzt + avionik.PAKET_PAUSE

    def schliesse(self):
        if self.handle is not None:
            d2xx.FT_Close(self.handle)
            self.handle = None


def lies_fg_ausgabe(sock_in, avionik_geraet):
    """Holt die neueste Zeile aus FlightGear (elite_aus.xml) und uebernimmt die Frequenzen.
    Gibt True zurueck, wenn FlightGear etwas geschickt hat."""
    zeile = None
    while True:
        try:
            zeile = sock_in.recv(512)
        except (BlockingIOError, ConnectionResetError):
            break
    if zeile is None:
        return False
    try:
        werte = [float(x) for x in zeile.decode().strip().split(",")]
    except ValueError:
        return True
    for typ, mhz in zip(AUSGABE, werte):
        if typ is not None and 100 <= mhz < 140:
            avionik_geraet.setze(typ, mhz)
    # ADF (kHz) als zwei Ziffernpaare: Block 1 = 'G' (Bytes 3/4), Block 2 = 'H' (Bytes 1/2)
    adf = werte[len(AUSGABE):len(AUSGABE) + 2]
    if len(adf) == 2 and all(100 <= khz < 10000 for khz in adf):
        aktiv, standby = (int(khz) for khz in adf)
        avionik_geraet.soll["G"] = avionik.satz("G", 0, 0, aktiv // 100, aktiv % 100)
        avionik_geraet.soll["H"] = avionik.satz("H", standby // 100, standby % 100, 0, 0)
    # Transponder: 'S' = Ziffern Einer..Tausender, 'R' = an (2) / aus (0)
    xpdr = werte[len(AUSGABE) + 2:len(AUSGABE) + 4]
    if len(xpdr) == 2:
        code, modus = int(xpdr[0]), int(xpdr[1])
        avionik_geraet.soll["S"] = avionik.satz(
            "S", code % 10, code // 10 % 10, code // 100 % 10, code // 1000 % 10)
        avionik_geraet.xpdr_an = modus != 0
    # Autopilot Century III: roll, pitch, alt (0/1), Modus (0 NAV 1 OMNI 2 HDG 3 LOC 4 BC),
    # Gleitpfad erfasst, HDG-Schalter (Kurssteuerung) -> Lampenwort fuer 'T'
    ap = werte[len(AUSGABE) + 4:len(AUSGABE) + 10]
    if len(ap) == 6:
        roll, pitch, alt, modus, gs, hdg = (int(x) for x in ap)
        lampen = 0
        if roll:
            lampen |= AP_LAMPE["ap"]
        if pitch:
            lampen |= AP_LAMPE["fd"]
        if alt:
            lampen |= AP_LAMPE["alt"]
        if roll and hdg:
            # Modus- und GS-Lampen nur, wenn die Kurssteuerung des Century III aktiv ist
            # (sonst haelt er nur die Flaechen waagerecht)
            if gs:
                lampen |= AP_LAMPE["gs"]
            lampen |= {0: AP_LAMPE["nav"], 1: AP_LAMPE["nav"], 2: AP_LAMPE["hdg"],
                       3: AP_LAMPE["apr"], 4: AP_LAMPE["bc"]}.get(modus, 0)
        avionik_geraet.ap_lampen = lampen
    # DME: eigene Frequenz (MHz), Entfernung (NM), Geschwindigkeit (kt), Zeit (min),
    # Station in Reichweite
    dme = werte[len(AUSGABE) + 10:len(AUSGABE) + 15]
    if len(dme) == 5:
        avionik_geraet.dme_werte = tuple(dme)
    # Fahrwerk: Stellung Bug, links, rechts (0 = eingefahren, 1 = ausgefahren)
    fahrwerk = werte[len(AUSGABE) + 15:len(AUSGABE) + 18]
    if len(fahrwerk) == 3:
        avionik_geraet.fahrwerk = tuple(fahrwerk)
    # Marker-Lampen (aussen, Mitte, innen; FlightGear laesst sie schon blinken) und
    # "Trimm-Servo des Autopiloten laeuft" fuer die TRIM-Lampe
    marker = werte[len(AUSGABE) + 18:len(AUSGABE) + 21]
    if len(marker) == 3:
        avionik_geraet.marker = tuple(int(x) for x in marker)
    trimmt = werte[len(AUSGABE) + 21:len(AUSGABE) + 22]
    if trimmt:
        avionik_geraet.ap_trimmt = bool(trimmt[0])
    # ADF-Anzeige: Schriftzuege (Bits wie ADF_SCHRIFT) und Zahl im rechten Block; mit FLT
    # oder ET steht dort die Zeit (mmss) statt der Standby-Frequenz
    adf_anzeige = werte[len(AUSGABE) + 22:len(AUSGABE) + 24]
    if len(adf_anzeige) == 2 and adf_anzeige[0] > 0:
        avionik_geraet.adf_schrift = int(adf_anzeige[0]) & 63
        rechts = max(0, min(9999, int(adf_anzeige[1])))
        avionik_geraet.soll["H"] = avionik.satz("H", rechts // 100, rechts % 100, 0, 0)
    return True


def fahrwerk_lampen(fahrwerk, batterie):
    """Pro Panel Datensatz ' ': Bytes 0 / 1 / 3 = Bug / links / rechts,
    2 = gruen (ausgefahren), 3 = rot (unterwegs), 0 = aus (am Geraet ermittelt)."""
    if not batterie or fahrwerk is None:
        return avionik.satz(" ", 0, 0, 0, 0)
    farbe = [2 if s >= 0.99 else 3 if s > 0.01 else 0 for s in fahrwerk]
    return avionik.satz(" ", farbe[0], farbe[1], 0, farbe[2])


def achs_eintrag(achse, profil=None):
    """Einstellungen einer Achse: Werte aus ACHSEN, ueberschrieben vom Profil."""
    geraet, code, name, art, *grenzen, neutral = achse
    eintrag = {"grenzen": grenzen, "umkehren": False, "totzone": TOTZONE_STANDARD[art],
               "kurve": 0, "raste": None}
    if profil is not None:
        eintrag.update(profil["achsen"].get(name) or {})
    return eintrag


def biege(anteil, kurve):
    """Kurve in Prozent: 0 = gerade, mehr = um 0 feiner, zum Ende hin staerker."""
    k = kurve / 100
    return (1 - k) * anteil + k * anteil ** 3


def hebelstellung(wert, eintrag):
    """-> (Anteil vorwaerts 0..1, Anteil hinter der Raste 0..1)."""
    null, voll = eintrag["grenzen"]
    if eintrag["umkehren"]:
        null, voll = voll, null
    raste = eintrag["raste"]
    if raste is None:
        return normiere(wert, null, voll), 0.0
    spiel = RASTE_SPIEL if null > raste else -RASTE_SPIEL
    if raste + spiel == null:
        return normiere(wert, raste, voll), 0.0
    return normiere(wert, raste, voll), normiere(wert, raste + spiel, null)


def forme_hebel(anteil, eintrag):
    """Totzone an beiden Enden (Leerlauf und Vollgas sicher erreichen), dann Kurve."""
    t = eintrag["totzone"] / 100
    anteil = min(1.0, max(0.0, (anteil - t) / (1 - 2 * t))) if t < 0.5 else 0.0
    return biege(anteil, eintrag["kurve"])


def berechne(achse, roh, profil=None):
    """Rohwert -> FlightGear-Wert; profil (aus den Einstellungen) liefert Grenzen,
    Richtung, Totzone, Kurve und Raste."""
    wert = roh.get((achse[0], achse[1]))
    if wert is None:
        return achse[-1]
    eintrag = achs_eintrag(achse, profil)
    if achse[3] == "ruder":
        ergebnis = normiere_ruder(wert, *eintrag["grenzen"])
        if eintrag["umkehren"]:
            ergebnis = -ergebnis
        t = eintrag["totzone"] / 100
        betrag = max(0.0, abs(ergebnis) - t) / (1 - t) if t < 1 else 0.0
        return math.copysign(biege(betrag, eintrag["kurve"]), ergebnis)
    return forme_hebel(hebelstellung(wert, eintrag)[0], eintrag)


def umkehrschub(achse, roh, profil=None):
    """Wie weit der Hebel hinter der Raste steht (0..1); 0 ohne Raste im Profil."""
    wert = roh.get((achse[0], achse[1]))
    if wert is None:
        return 0.0
    eintrag = achs_eintrag(achse, profil)
    return forme_hebel(hebelstellung(wert, eintrag)[1], eintrag)


def schalterwert(name, regel, stabil, profil=None):
    wert = regel(stabil)
    if profil is not None and profil["umkehren"].get(name):
        return -wert
    return wert


def main():
    parser = argparse.ArgumentParser(description="Elite-Hardware -> FlightGear")
    parser.add_argument("--ziel", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5010)
    parser.add_argument("--rate", type=float, default=30, help="Pakete pro Sekunde")
    parser.add_argument("--zeigen", action="store_true", help="gesendete Werte ausgeben")
    parser.add_argument("--dauer", type=float, help="nach so vielen Sekunden beenden")
    parser.add_argument("--port-aus", type=int, default=5011,
                        help="UDP-Port, auf dem FlightGear die Frequenzen schickt")
    parser.add_argument("--testfrequenzen", action="store_true",
                        help="ohne FlightGear feste Frequenzen auf das AP-3000 schreiben")
    args = parser.parse_args()
    bruecke = Bruecke(args.ziel, args.port, args.port_aus, args.rate, args.zeigen,
                      args.testfrequenzen)
    try:
        bruecke.lauf(args.dauer)
    except KeyboardInterrupt:
        pass


class Bruecke:
    """Die eigentliche Bruecke. lauf() arbeitet, bis halt() aufgerufen wird (oder dauer
    um ist); das Bedienfenster (elite_gui.py) laesst sie in einem eigenen Faden laufen und
    liest Status (verbunden, fg_da, roh) und Einstellungen (profil_name) mit."""

    def __init__(self, ziel="127.0.0.1", port=5010, port_aus=5011, rate=30, zeigen=False,
                 testfrequenzen=False):
        self.ziel, self.port, self.port_aus, self.rate = ziel, port, port_aus, rate
        self.zeigen, self.testfrequenzen = zeigen, testfrequenzen
        self.einstellungen = lade_einstellungen()
        self.profil_name = "standard"
        self.geraete = [Geraet(PRO_PANEL, "Pro Panel"), Geraet(PEDALE, "Pedale")]
        self.ap3000 = Avionik(AP3000, "AP-3000")
        # Schalter-Meldungen aller Geraete fuer den Schalter-Test (das Fenster holt sie ab)
        self.protokoll = collections.deque(maxlen=300)
        for geraet in [*self.geraete, self.ap3000]:
            geraet.protokoll = self.protokoll
        self.entpreller = Entpreller()
        self.roh = {}
        self.fg_zuletzt = 0.0    # wann zuletzt Daten von FlightGear kamen
        self.flugzeug = ""       # laut FlightGear, z.B. "SenecaII"
        self.laeuft = False

    @property
    def profil(self):
        profile = self.einstellungen["profile"]
        return profile.get(self.profil_name) or profile["standard"]

    def verbunden(self):
        """Geraetename -> verbunden (True/False)."""
        status = {g.name: g.handle is not None for g in self.geraete}
        status[self.ap3000.name] = self.ap3000.handle is not None
        return status

    def fg_da(self):
        return time.monotonic() - self.fg_zuletzt < 3

    def pruefe_flugzeug(self):
        """Fragt FlightGear (httpd, Port 8080) nach dem Flugzeug und waehlt dessen Profil;
        ohne eigenes Profil gilt "standard"."""
        try:
            with urllib.request.urlopen("http://127.0.0.1:8080/json/sim/aircraft",
                                        timeout=0.3) as antwort:
                flugzeug = json.load(antwort).get("value") or ""
        except (OSError, ValueError):
            return
        self.flugzeug = flugzeug
        name = flugzeug if flugzeug in self.einstellungen["profile"] else "standard"
        if name != self.profil_name:
            self.profil_name = name
            print(f"Flugzeug {flugzeug}: Profil '{name}'", flush=True)

    def halt(self):
        self.laeuft = False

    def lauf(self, dauer=None):
        geraete, ap3000, roh = self.geraete, self.ap3000, self.roh
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_in.bind(("127.0.0.1", self.port_aus))
        sock_in.setblocking(False)
        if self.testfrequenzen:
            for typ, mhz in zip(AUSGABE, [118.25, 121.5, 125.75, 132.0, 110.3, 112.0, 113.9,
                                          112.4]):
                if typ:
                    ap3000.setze(typ, mhz)
            ap3000.soll["G"] = avionik.satz("G", 0, 0, 3, 50)    # ADF 350 kHz
            ap3000.soll["H"] = avionik.satz("H", 12, 34, 0, 0)   # ADF-Standby 1234 kHz
        print(f"Sende an {self.ziel}:{self.port}, Frequenzen von Port {self.port_aus}.",
              flush=True)

        entpreller = self.entpreller = Entpreller()
        sitzung = int(time.time()) % 30000  # sagt dem Add-on: Zaehler beginnen neu bei 0
        fahrwerk_gesendet, fahrwerk_zeit = None, 0.0
        intervall = 1.0 / self.rate
        start = naechstes = time.monotonic()
        flugzeug_geprueft = 0.0
        self.laeuft = True
        try:
            while self.laeuft and (dauer is None or time.monotonic() - start < dauer):
                for geraet in geraete:
                    geraet.lies(roh)
                if lies_fg_ausgabe(sock_in, ap3000):
                    # FlightGear (neu) da nach Pause: Zaehler neu bei 0 beginnen, damit das
                    # Add-on ab 0 rechnet und kein Dreh verloren geht oder doppelt zaehlt
                    if time.monotonic() - self.fg_zuletzt > 3:
                        sitzung = (sitzung + 1) % 30000
                        ap3000.zaehler = dict.fromkeys(ZAEHLER, 0)
                    self.fg_zuletzt = time.monotonic()
                    if self.fg_zuletzt - flugzeug_geprueft > 5:
                        self.pruefe_flugzeug()
                        flugzeug_geprueft = self.fg_zuletzt
                elif time.monotonic() - self.fg_zuletzt > 3:
                    # ohne FlightGear nichts aufsammeln, sonst wuerde es beim Start nachgeholt
                    for name in ZAEHLER:
                        ap3000.zaehler[name] = 0
                ap3000.arbeite()
                jetzt = time.monotonic()
                entpreller.aktualisiere(roh, jetzt)
                # Avionik-Anzeigen nur mit Batterie und Radio-Master (aktiv-niedrig: 0 = ein);
                # ohne Pro Panel (kein Wert) bleiben sie dunkel: der Zuendschluessel macht das
                # Pro Panel stromlos, das heisst "Flugzeug aus" (Nutzer 2026-11-12)
                ap3000.strom = all(entpreller.stabil.get(code) == 0 for code in (60, 61))
                # Fahrwerkslampen am Pro Panel: bei Aenderung sofort, sonst alle 2 s
                # (Elite-Treiber: alle 5 s); ohne FlightGear aus
                lampen = fahrwerk_lampen(ap3000.fahrwerk if self.fg_da() else None,
                                         entpreller.stabil.get(60, 0) == 0)
                if lampen != fahrwerk_gesendet or jetzt - fahrwerk_zeit > 2:
                    geraete[0].sende(avionik.paket([lampen]))
                    fahrwerk_gesendet, fahrwerk_zeit = lampen, jetzt
                # erst nach dem ersten Komplettabzug (~1 s) senden, sonst springen die Hebel
                if jetzt < naechstes or jetzt - start < 1.5:
                    time.sleep(0.002)
                    continue
                naechstes = jetzt + intervall
                profil = self.profil
                werte, umkehr = [], []
                for achse in ACHSEN:
                    wert = berechne(achse, roh, profil)
                    if achse[2] in UMKEHRSCHUB:
                        # hinter der Raste: Gas = Staerke des Umkehrschubs, das Add-on
                        # schaltet den Reverser
                        anteil = umkehrschub(achse, roh, profil)
                        umkehr.append(str(int(anteil > 0)))
                        if anteil > 0:
                            wert = anteil
                    werte.append(f"{wert:.3f}")
                for name, regel in SCHALTER:
                    wert = schalterwert(name, regel, entpreller.stabil, profil)
                    if name == "hoehentrimm":
                        # Trimm-Tempo je Profil: jedes Flugzeug trimmt verschieden stark
                        werte.append(f"{wert * profil.get('trimm_tempo', 1.0):.2f}")
                    else:
                        werte.append(str(wert))
                werte.append(str(sitzung))
                werte += [str(ap3000.zaehler[name]) for name in ZAEHLER]
                # Transponder-Modus (-1 = Schalter noch unbekannt) und IDENT
                werte += [str(-1 if ap3000.xpdr_modus is None else ap3000.xpdr_modus),
                          str(ap3000.xpdr_ident), str(ap3000.ap_trimm),
                          str(ap3000.dme_quelle())]
                werte += umkehr
                # OFF-Taster COM/NAV 1 und 2: 1 = an, -1 = aus (0 hiesse "noch unbekannt")
                werte += ["1" if an else "-1" for an in ap3000.geraet_an]
                zeile = ",".join(werte)
                sock.sendto((zeile + "\n").encode(), (self.ziel, self.port))
                if self.zeigen:
                    print(zeile, flush=True)
        finally:
            self.laeuft = False
            for geraet in geraete:
                geraet.schliesse()
            ap3000.schliesse()
            sock.close()
            sock_in.close()
            print("Bruecke gestoppt.", flush=True)


if __name__ == "__main__":
    main()
