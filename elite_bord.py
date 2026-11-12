"""Bordcomputer und Checkliste fuer das freie Feld im Instrumentenbrett (neben dem Navi).

Seite BORD: Treibstoff links/rechts mit Restflugzeit, Aussentemperatur, Bordspannung und
Warnungen im Klartext (Tank fast leer, Magnete aus, Parkbremse ...).
Seite CHECKLISTE: die Checklisten des Flugzeugs (/sim/checklists). Punkte, die sich an den
Bordwerten pruefen lassen, haken sich selbst ab; die anderen per Touch auf die Zeile.

Bedienung per Touch/Maus: Kopfzeile wechselt die Seite, < und > blaettern die Listen.

Daten: das Add-on schreibt /elite/bord (alle 0,5 s), dieses Fenster liest sie per httpd
(Port 8080) und waehlt die Liste ueber /elite/bord/liste.

Allein testen:  python elite_bord.py
"""

import json
import threading
import time
import tkinter as tk
import urllib.request

import elite_gps

URL = "http://127.0.0.1:8080/json/elite/bord?d=4"
SCHWARZ, RAHMEN, FELD = "#000000", "#2b2b2b", "#101418"
WEISS, GRAU, GRUEN, GELB, ROT = "#e8e8e8", "#7d8790", "#35c759", "#ffb000", "#ff453a"
TANK_VOLL = 61.5            # ausfliegbare Gallonen je Seite (Seneca II, Hauptfluegeltank)
TANK_KNAPP, TANK_LEER = 8.0, 4.0     # Gallonen je Seite: Warnung gelb / rot


def wandle(knoten):
    """httpd-JSON in ein dict; die Checklistenpunkte (item) werden eine Liste."""
    if "children" not in knoten:
        return knoten.get("value")
    daten = {}
    for kind in knoten["children"]:
        wert = wandle(kind)
        if kind["name"] == "item":
            daten.setdefault("item", []).append(wert)
        else:
            daten[kind["name"]] = wert
    return daten


class Leser(threading.Thread):
    """Holt /elite/bord alle 0,5 s; aktuell() = None, solange FlightGear nicht antwortet."""

    def __init__(self):
        super().__init__(daemon=True)
        self.daten = None
        self.zeit = 0.0
        self.laeuft = True

    def run(self):
        while self.laeuft:
            try:
                with urllib.request.urlopen(URL, timeout=1) as antwort:
                    daten = wandle(json.load(antwort))
                if isinstance(daten, dict) and "batterie" in daten:
                    self.daten, self.zeit = daten, time.monotonic()
            except (OSError, ValueError):
                pass
            time.sleep(0.5)

    def aktuell(self):
        return self.daten if time.monotonic() - self.zeit < 3 else None


def beide(d, name, pruefe):
    return pruefe(d.get(name + "-l") or 0) and pruefe(d.get(name + "-r") or 0)


def drehzahl(von, bis):
    return lambda d: beide(d, "rpm", lambda w: von <= w <= bis)


# Checklistenpunkte, die sich an den Bordwerten pruefen lassen:
# (Teil des Namens, Teil des Sollwerts, Pruefung) - alles klein geschrieben, erste passt
REGELN = [
    ("parking brake", "set", lambda d: d.get("parkbremse")),
    ("gear / flaps", "up", lambda d: not d.get("fahrwerk") and (d.get("klappen") or 0) < 0.01),
    ("gear", "down", lambda d: d.get("fahrwerk")),
    ("battery master", "on", lambda d: d.get("batterie")),
    ("battery master", "off", lambda d: not d.get("batterie")),
    ("alternators", "off", lambda d: not d.get("lima-l") and not d.get("lima-r")),
    ("alternators", "on", lambda d: d.get("lima-l") and d.get("lima-r")),
    ("radios", "off", lambda d: not d.get("avionik")),
    ("radios", "on", lambda d: d.get("avionik")),
    ("cowl flaps", "open", lambda d: beide(d, "cowl", lambda w: w > 0.9)),
    ("cowl flaps", "closed", lambda d: beide(d, "cowl", lambda w: w < 0.1)),
    ("fuel selector", "on", lambda d: beide(d, "tankwahl", lambda w: w == 1)),
    ("mixture", "rich", lambda d: beide(d, "gemisch", lambda w: w > 0.9)),
    ("mixture", "cutoff", lambda d: beide(d, "gemisch", lambda w: w < 0.05)),
    ("propeller", "high rpm", lambda d: beide(d, "prop", lambda w: w > 0.9)),
    ("throttle", "full", lambda d: beide(d, "gas", lambda w: w > 0.95)),
    ("throttle", "idle", lambda d: beide(d, "gas", lambda w: w < 0.05)),
    ("throttle", "800-1000", drehzahl(750, 1050)),
    ("throttle", "1000 rpm", drehzahl(950, 1080)),
    ("throttle", "1900 rpm", drehzahl(1850, 1950)),
    ("throttle", "1600 rpm", drehzahl(1550, 1650)),
    ("beacon", "on", lambda d: d.get("beacon")),
    ("magnetos", "both on", lambda d: beide(d, "mag", lambda w: w == 2)),
    ("engine starter", "", lambda d: beide(d, "lauf", bool)),
    ("oil pressure", "green", lambda d: beide(d, "oeldruck", lambda w: 30 <= w <= 80)),
    ("landing lights", "on", lambda d: d.get("landing")),
    ("landing lights", "off", lambda d: not d.get("landing")),
    ("pitot heat", "off", lambda d: not d.get("pitot")),
    ("strobe lights", "off", lambda d: not d.get("strobe")),
    ("flaps", "up", lambda d: (d.get("klappen") or 0) < 0.01),
    ("transponder", "alt", lambda d: d.get("xpdr") in (4, 5)),
    ("transponder", "standby", lambda d: d.get("xpdr") == 1),
]


def erfuellt(punkt, d):
    """True/False, wenn sich der Punkt pruefen laesst, sonst None (von Hand abhaken)."""
    if punkt.get("ok") in (0, 1):          # Bedingung aus der Checkliste des Flugzeugs
        return bool(punkt["ok"])
    name, wert = str(punkt.get("name") or "").lower(), str(punkt.get("wert") or "").lower()
    for teil_name, teil_wert, pruefung in REGELN:
        if teil_name in name and teil_wert in wert:
            return bool(pruefung(d))
    return None


def warnungen(d):
    """[(Farbe, Text)] - das Wichtigste zuerst."""
    liste = []
    am_boden = (d.get("agl-ft") or 0) < 30
    for s, seite in (("l", "LINKS"), ("r", "RECHTS")):
        tank = d.get("tank-" + s) or 0
        if tank < TANK_LEER:
            liste.append((ROT, f"TANK {seite} LEER"))
        elif tank < TANK_KNAPP:
            liste.append((GELB, f"TANK {seite} FAST LEER"))
    if not am_boden and not d.get("fahrwerk") and (d.get("agl-ft") or 0) < 600 \
            and (d.get("ias-kt") or 0) < 110:
        liste.append((ROT, "FAHRWERK NICHT AUSGEFAHREN"))
    if d.get("parkbremse") and (max(d.get("gas-l") or 0, d.get("gas-r") or 0) > 0.5
                                or not am_boden):
        liste.append((ROT, "PARKBREMSE GESETZT"))
    for s, seite in (("l", "LINKS"), ("r", "RECHTS")):
        laeuft = d.get("lauf-" + s)
        if laeuft and (d.get("mag-" + s) or 0) < 2:
            liste.append((GELB, f"MAGNET {seite}: NUR EINER"))
        if laeuft and not d.get("lima-" + s):
            liste.append((GELB, f"LICHTMASCHINE {seite} AUS"))
        if laeuft and not d.get("tankwahl-" + s):
            liste.append((ROT, f"TANKWAHL {seite} ZU"))
        if laeuft and am_boden and (d.get("cowl-" + s) or 0) < 0.5:
            liste.append((GELB, f"COWL FLAPS {seite} ZU"))
        # Motor steht, Batterie ein: was den Start verhindert
        if not laeuft and d.get("batterie"):
            if (d.get("mag-" + s) or 0) < 2:
                liste.append((GELB, f"MAGNETE {seite} AUS"))
            if (d.get("gemisch-" + s) or 0) < 0.5:
                liste.append((GELB, f"GEMISCH {seite} ARM"))
    if not am_boden and (d.get("oat-c") or 0) <= 5 and not d.get("pitot"):
        liste.append((GELB, "PITOT-HEIZUNG AUS"))
    if d.get("batterie") and 0 < (d.get("volt") or 0) < 11.5:
        liste.append((GELB, "BATTERIE SCHWACH"))
    return liste


class BordFenster(tk.Toplevel):
    def __init__(self, eltern, platz=None):
        """platz = (x, y, breite, hoehe): Feld im Instrumentenbrett (rahmenlos darueber)."""
        super().__init__(eltern)
        self.title("Bordcomputer")
        self.configure(bg=SCHWARZ)
        self.platz = platz
        if platz:
            self.overrideredirect(True)
            self.attributes("-topmost", True)
            self.geometry("{2}x{3}+{0}+{1}".format(*platz))
            self.after(200, lambda: elite_gps.GpsFenster.nicht_aktivieren(self))
        else:
            self.geometry("556x506")
        self.leinwand = tk.Canvas(self, bg=SCHWARZ, highlightthickness=0)
        self.leinwand.pack(fill="both", expand=True)
        self.leinwand.bind("<Button-1>", self.beruehrt)
        self.leser = Leser()
        self.leser.start()
        self.seite = "bord"          # bord / check
        self.liste = 0               # Nummer der Checkliste
        self.erledigt = set()        # abgehakte Punkte der gezeigten Liste
        self.erledigt_liste = None   # zu welcher Liste (Nummer, Titel) die Haken gehoeren
        self.flaechen = []           # Touch: (x1, y1, x2, y2, Aufruf)
        self.protocol("WM_DELETE_WINDOW", self.schliessen)
        self.takt()

    def schliessen(self):
        self.leser.laeuft = False
        self.destroy()

    def setze_platz(self, platz):
        """Neues Feld (x, y, breite, hoehe), z. B. wenn der Monitor in Windows verschoben wurde."""
        if platz and platz != self.platz:
            self.platz = platz
            self.geometry("{2}x{3}+{0}+{1}".format(*platz))

    def beruehrt(self, ereignis):
        for x1, y1, x2, y2, aufruf in self.flaechen:
            if x1 <= ereignis.x <= x2 and y1 <= ereignis.y <= y2:
                aufruf()
                self.zeichne()
                return

    def wechsle_seite(self):
        self.seite = "check" if self.seite == "bord" else "bord"

    def blaettere(self, schritt, anzahl):
        self.liste = (self.liste + schritt) % max(1, anzahl)
        elite_gps.sende([("elite/bord/liste", self.liste)])

    def hake(self, nr):
        self.erledigt.symmetric_difference_update({nr})

    def takt(self):
        self.zeichne()
        self.after(250, self.takt)

    # --- Zeichnen ------------------------------------------------------------------
    def zeichne(self):
        lw = self.leinwand
        lw.delete("all")
        self.flaechen = []
        breite, hoehe = lw.winfo_width(), lw.winfo_height()
        if breite < 50:
            return
        self.e = hoehe / 100                 # alles in Hundertstel der Hoehe
        e = self.e
        lw.create_rectangle(0, 0, breite, hoehe, fill=RAHMEN, outline="")
        lw.create_rectangle(e, e, breite - e, hoehe - e, fill=FELD, outline="#555")
        d = self.leser.aktuell()
        # Kopfzeile = Umschalter zwischen den beiden Seiten
        kopf = 11 * e
        halb = breite / 2
        for i, (name, titel) in enumerate((("bord", "BORD"), ("check", "CHECKLISTE"))):
            aktiv = self.seite == name
            lw.create_rectangle(e + i * (halb - e), e, e + (i + 1) * (halb - e), kopf,
                                fill=GELB if aktiv else FELD, outline="#555")
            lw.create_text(e + (i + 0.5) * (halb - e), (e + kopf) / 2, text=titel,
                           fill=SCHWARZ if aktiv else GRAU, font=self.schrift(5.5, True))
        self.flaechen.append((0, 0, breite, kopf, self.wechsle_seite))
        if not d:
            lw.create_text(breite / 2, hoehe / 2, text="WARTE AUF FLIGHTGEAR", fill=GELB,
                           font=self.schrift(5, True))
        elif self.seite == "bord":
            self.seite_bord(d, breite, hoehe, kopf)
        else:
            self.seite_check(d, breite, hoehe, kopf)

    def schrift(self, groesse, fett=False):
        return ("Segoe UI", -max(8, int(groesse * self.e)), "bold" if fett else "normal")

    def seite_bord(self, d, breite, hoehe, oben):
        lw, e = self.leinwand, self.e
        rand = 4 * e
        # Treibstoff: je Seite Balken und Gallonen
        y = oben + 3 * e
        lw.create_text(rand, y, text="TREIBSTOFF (gal)", fill=GRAU, font=self.schrift(4),
                       anchor="nw")
        y += 6.5 * e
        gesamt = 0.0
        for s, seite in (("l", "L"), ("r", "R")):
            tank = d.get("tank-" + s) or 0
            gesamt += max(0.0, tank - 2.5)       # rund 2,5 gal je Seite sind nicht ausfliegbar
            farbe = ROT if tank < TANK_LEER else GELB if tank < TANK_KNAPP else GRUEN
            lw.create_text(rand, y + 3.5 * e, text=seite, fill=WEISS,
                           font=self.schrift(6, True), anchor="w")
            bx0, bx1 = rand + 6 * e, breite - rand - 21 * e
            lw.create_rectangle(bx0, y, bx1, y + 7 * e, outline="#555", fill=SCHWARZ)
            lw.create_rectangle(bx0, y, bx0 + (bx1 - bx0) * min(1.0, tank / TANK_VOLL),
                                y + 7 * e, outline="", fill=farbe)
            lw.create_text(breite - rand, y + 3.5 * e, text=f"{tank:4.1f}", fill=farbe,
                           font=self.schrift(7, True), anchor="e")
            y += 9.5 * e
        verbrauch = (d.get("ff-l") or 0) + (d.get("ff-r") or 0)
        if verbrauch > 1:
            minuten = gesamt / verbrauch * 60
            rest = f"{verbrauch:4.1f} gal/h   REST {int(minuten // 60)}:{int(minuten % 60):02d} h"
        else:
            rest = "Motoren aus"
        lw.create_text(rand, y + 2.5 * e, text=rest, fill=WEISS, font=self.schrift(5),
                       anchor="w")
        y += 7.5 * e
        lw.create_text(rand, y + 2.5 * e, anchor="w", fill=GRAU, font=self.schrift(4.5),
                       text=f"AUSSEN {d.get('oat-c') or 0:+.0f} °C     BORDNETZ "
                            f"{d.get('volt') or 0:.1f} V")
        y += 7 * e
        lw.create_line(rand, y, breite - rand, y, fill="#555")
        y += 2 * e
        # Warnungen
        liste = warnungen(d)
        if not liste:
            lw.create_text(breite / 2, (y + hoehe) / 2, text="KEINE WARNUNG", fill=GRUEN,
                           font=self.schrift(6, True))
            return
        zeile = min(9 * e, (hoehe - y - 2 * e) / len(liste))
        for farbe, text in liste:
            lw.create_rectangle(rand, y + 0.5 * e, breite - rand, y + zeile - 0.5 * e,
                                fill=farbe, outline="")
            lw.create_text(breite / 2, y + zeile / 2, text=text, fill=SCHWARZ,
                           font=self.schrift(min(5.2, zeile / e * 0.62), True))
            y += zeile

    def seite_check(self, d, breite, hoehe, oben):
        lw, e = self.leinwand, self.e
        rand = 3 * e
        check = d.get("check") or {}
        punkte = [p for p in check.get("item") or [] if isinstance(p, dict)]
        anzahl = int(d.get("listen") or 0)
        if not anzahl:
            lw.create_text(breite / 2, hoehe / 2, text="Dieses Flugzeug hat\nkeine Checklisten",
                           fill=GRAU, font=self.schrift(5), justify="center")
            return
        nr = int(check.get("nr") or 0)
        if nr != self.liste and time.monotonic() - getattr(self, "gewaehlt_um", 0) > 2:
            self.liste = nr              # FlightGear zeigt (z. B. nach Neustart) eine andere
        kennung = (nr, check.get("titel"))
        if kennung != self.erledigt_liste:
            self.erledigt, self.erledigt_liste = set(), kennung
        # Titelzeile mit Blaettern
        y = oben + 1.5 * e
        titel_h = 10 * e
        for x0, text, schritt in ((rand, "<", -1), (breite - rand - 12 * e, ">", 1)):
            lw.create_rectangle(x0, y, x0 + 12 * e, y + titel_h, fill="#16314d",
                                outline="#6f93b5")
            lw.create_text(x0 + 6 * e, y + titel_h / 2, text=text, fill=WEISS,
                           font=self.schrift(7, True))
            self.flaechen.append((x0, y, x0 + 12 * e, y + titel_h,
                                  lambda s=schritt: self.waehle(s, anzahl)))
        lw.create_text(breite / 2, y + 3.2 * e, text=str(check.get("titel") or ""),
                       fill=WEISS, font=self.schrift(4.6, True))
        lw.create_text(breite / 2, y + 7.6 * e, text=f"{nr + 1} / {anzahl}", fill=GRAU,
                       font=self.schrift(3.6))
        y += titel_h + 1.5 * e
        zeile = min(8.5 * e, (hoehe - y - 7 * e) / max(1, len(punkte)))
        gross = min(4.6, zeile / e * 0.6)
        offen = 0
        for i, punkt in enumerate(punkte):
            auto = erfuellt(punkt, d)
            if auto:
                self.erledigt.add(i)     # bleibt abgehakt, auch wenn z. B. das Gas weitergeht
            fertig = i in self.erledigt
            offen += not fertig
            farbe = GRUEN if fertig else WEISS
            lw.create_rectangle(rand, y + zeile * 0.18, rand + zeile * 0.64, y + zeile * 0.82,
                                outline=farbe, fill=GRUEN if fertig else "")
            if auto is not None and not fertig:
                # laesst sich selbst pruefen, ist aber noch nicht erfuellt
                lw.create_text(rand + zeile * 0.32, y + zeile / 2, text="A", fill=GRAU,
                               font=self.schrift(gross * 0.7, True))
            lw.create_text(rand + zeile * 0.95, y + zeile / 2, anchor="w", fill=farbe,
                           text=str(punkt.get("name") or ""), font=self.schrift(gross, True))
            lw.create_text(breite - rand, y + zeile / 2, anchor="e", fill=farbe,
                           text=str(punkt.get("wert") or ""), font=self.schrift(gross * 0.85))
            self.flaechen.append((0, y, breite, y + zeile, lambda n=i: self.hake(n)))
            y += zeile
        if punkte and not offen:
            lw.create_text(breite / 2, hoehe - 3.5 * e, text="LISTE FERTIG  >", fill=GRUEN,
                           font=self.schrift(4, True))

    def waehle(self, schritt, anzahl):
        self.gewaehlt_um = time.monotonic()
        self.blaettere(schritt, anzahl)


def main():
    wurzel = tk.Tk()
    wurzel.withdraw()
    fenster = BordFenster(wurzel)
    fenster.protocol("WM_DELETE_WINDOW", lambda: (fenster.schliessen(), wurzel.destroy()))
    fenster.bind("<Escape>", lambda _e: (fenster.schliessen(), wurzel.destroy()))
    wurzel.mainloop()


if __name__ == "__main__":
    main()
