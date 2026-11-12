"""GPS-Bildschirm (Apollo GX) fuer den kleinen Touch-Monitor neben dem AP-3000.

Oben das Apollo-Display mit den Seiten NAV / NRST / DIRECT / INFO, bedient mit den
Apollo-Tasten am AP-3000 (die Bruecke sammelt sie in Avionik.gps_ereignisse) oder per
Touch auf die Tastenbeschriftung; darunter eine bewegte Karte (Norden oben oder
Flugrichtung oben) mit Flugplaetzen, VOR und NDB.

Daten: das Add-on schreibt /elite/gps (Lage alle 0,5 s, Umgebung alle 5 s), dieses Fenster
liest sie per httpd (Port 8080). Peilungen und Kurse werden missweisend angezeigt.

Allein testen (ohne Bruecke, nur Touch/Maus):  python elite_gps.py
"""

import json
import math
import sys
import threading
import time
import tkinter as tk
import urllib.request

URL = "http://127.0.0.1:8080/json/elite/gps?d=4"
URL_SETZEN = "http://127.0.0.1:8080/json/"
FG_TYP = {"apt": "airport", "vor": "vor", "ndb": "ndb"}
BERNSTEIN, BERNSTEIN_DUNKEL = "#ffb000", "#5a3e00"
RAHMEN, SCHWARZ, KARTE = "#2b2b2b", "#000000", "#0b1a2a"
FARBE = {"apt": "#4fc3f7", "vor": "#64b5f6", "ndb": "#ce93d8", "ziel": "#ff40ff"}
RADIEN = [2, 5, 10, 20, 40, 60]          # Kartenradius in NM
LISTENTYPEN = ["apt", "vor", "ndb"]
TYPNAME = {"apt": "FLUGPLATZ", "vor": "VOR", "ndb": "NDB"}
SOFTKEYS = [("soft1", "NAV"), ("soft2", "NRST"), ("soft3", "ZOOM-"), ("soft4", "ZOOM+"),
            ("soft5", "N/TRK")]
ZEILEN_NRST = 5


def monitore():
    """[(x, y, breite, hoehe, primaer)] aller Monitore; ausserhalb Windows leer."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class INFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    liste = []
    rueckruf_typ = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.POINTER(wintypes.RECT), ctypes.c_double)

    def rueckruf(monitor, _dc, _rechteck, _daten):
        info = INFO()
        info.cbSize = ctypes.sizeof(INFO)
        ctypes.windll.user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info))
        r = info.rcMonitor
        liste.append((r.left, r.top, r.right - r.left, r.bottom - r.top,
                      bool(info.dwFlags & 1)))
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(None, None, rueckruf_typ(rueckruf), 0)
    return liste


def gps_monitor():
    """Der kleine Monitor (z.B. Elo 1280x800, hochkant oder quer), sonst None."""
    for m in monitore():
        if not m[4] and max(m[2], m[3]) <= 1366:
            return m
    return None


def wandle(knoten):
    """httpd-JSON in ein dict; apt/nav werden Listen."""
    if "children" not in knoten:
        return knoten.get("value")
    daten = {}
    for kind in knoten["children"]:
        wert = wandle(kind)
        if kind["name"] in ("apt", "nav"):
            daten.setdefault(kind["name"], []).append(wert)
        else:
            daten[kind["name"]] = wert
    return daten


def kurs_distanz(lat1, lon1, lat2, lon2):
    """Rechtweisender Kurs (Grad) und Distanz (NM) auf der Grosskreis-Strecke."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    distanz = 2 * math.asin(min(1.0, math.sqrt(a))) * 3440.065
    kurs = math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                   math.cos(p1) * math.sin(p2)
                                   - math.sin(p1) * math.cos(p2) * math.cos(dl)))
    return kurs % 360, distanz


def sende(werte):
    """Schreibt [(pfad, wert)] der Reihe nach per httpd (im Hintergrund)."""
    def arbeit():
        for pfad, wert in werte:
            anfrage = urllib.request.Request(URL_SETZEN + pfad, method="POST",
                                             data=json.dumps({"value": wert}).encode(),
                                             headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(anfrage, timeout=1).close()
            except OSError:
                return
    threading.Thread(target=arbeit, daemon=True).start()


class Leser(threading.Thread):
    """Holt /elite/gps alle 0,5 s; daten = None, solange FlightGear nicht antwortet."""

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
                if isinstance(daten, dict) and daten.get("lat") is not None:
                    self.daten, self.zeit = daten, time.monotonic()
            except (OSError, ValueError):
                pass
            time.sleep(0.5)

    def aktuell(self):
        return self.daten if time.monotonic() - self.zeit < 3 else None


class GpsFenster(tk.Toplevel):
    def __init__(self, eltern, ereignisse=None, platz=None):
        """platz = (x, y, breite, hoehe): Feld im Instrumentenbrett, ueber das sich das
        Fenster rahmenlos legt (ohne eigenen GPS-Monitor)."""
        super().__init__(eltern)
        self.ereignisse = ereignisse
        self.title("GPS")
        self.configure(bg=SCHWARZ)
        self.platz = platz
        # im Instrumentenbrett nur eine Anzeige: MAP wechselt zwischen Text und Karte
        self.einzeln = bool(platz)
        self.karte_an = False
        self.monitor = None if platz else gps_monitor()
        if platz:
            self.overrideredirect(True)
            self.attributes("-topmost", True)    # bleibt ueber dem FlightGear-Fenster
            self.geometry("{2}x{3}+{0}+{1}".format(*platz))
            self.after(200, self.nicht_aktivieren)
        elif self.monitor:
            self.platziere()
        else:
            self.geometry("600x960")
        self.monitor_geprueft = time.monotonic()
        self.leinwand = tk.Canvas(self, bg=SCHWARZ, highlightthickness=0)
        self.leinwand.pack(fill="both", expand=True)
        self.leinwand.bind("<Button-1>", self.beruehrt)
        self.leser = Leser()
        self.leser.start()
        self.an = True
        self.seite = "nav"           # nav / nrst / direct / info
        self.typ = "apt"             # Liste in NRST / DIRECT
        self.auswahl = 0
        self.ziel = None             # dict mit id, name, lat, lon, typ
        self.radius = 2              # Index in RADIEN
        self.nord_oben = True
        self.meldung = ("", 0.0)
        self.auftrag = int(time.time()) % 100000   # Zaehler fuer Auftraege an das Add-on
        self.flaechen = []           # Touch: (x1, y1, x2, y2, taste)
        self.protocol("WM_DELETE_WINDOW", self.schliessen)
        self.takt()

    def schliessen(self):
        self.leser.laeuft = False
        self.destroy()

    def platziere(self):
        x, y, breite, hoehe, _ = self.monitor
        self.overrideredirect(True)
        self.geometry(f"{breite}x{hoehe}+{x}+{y}")

    def setze_platz(self, platz):
        """Neues Feld (x, y, breite, hoehe), z. B. wenn der Monitor in Windows verschoben wurde."""
        if platz and platz != self.platz:
            self.platz = platz
            self.geometry("{2}x{3}+{0}+{1}".format(*platz))

    def nicht_aktivieren(self):
        """Touch/Klick auf das Navi nimmt FlightGear nicht die Tastatur weg."""
        if sys.platform != "win32":
            return
        import ctypes
        nutzer = ctypes.windll.user32
        fenster = nutzer.GetParent(self.winfo_id()) or self.winfo_id()
        stil = nutzer.GetWindowLongW(fenster, -20)             # GWL_EXSTYLE
        nutzer.SetWindowLongW(fenster, -20, stil | 0x08000000)  # WS_EX_NOACTIVATE

    def pruefe_monitor(self):
        """Folgt dem Monitor, wenn er in Windows verschoben oder gedreht wurde."""
        if self.platz or time.monotonic() - self.monitor_geprueft < 3:
            return
        self.monitor_geprueft = time.monotonic()
        monitor = gps_monitor()
        if monitor and monitor != self.monitor:
            self.monitor = monitor
            self.platziere()

    # --- Bedienung -----------------------------------------------------------------
    def melde(self, text):
        self.meldung = (text, time.monotonic() + 2)

    def taste(self, name):
        if name == "onoff":
            self.an = not self.an
            return
        if not self.an:
            return
        if self.einzeln:
            if name == "map":
                self.karte_an = not self.karte_an
                return
            if name in ("nav", "nrst", "direct", "info", "soft1", "soft2"):
                self.karte_an = False       # Seitentasten zeigen wieder den Text
        if isinstance(name, tuple):
            art, schritt = name
            if self.seite in ("nrst", "direct", "info"):
                if art == "fein":
                    self.auswahl = max(0, self.auswahl + schritt)
                else:
                    i = LISTENTYPEN.index(self.typ)
                    self.typ = LISTENTYPEN[(i + schritt) % len(LISTENTYPEN)]
                    self.auswahl = 0
            else:
                self.radius = max(0, min(len(RADIEN) - 1, self.radius - schritt))
        elif name in ("nav", "soft1"):
            self.seite = "nav"
        elif name in ("nrst", "soft2"):
            if self.seite == "nrst":
                self.typ = LISTENTYPEN[(LISTENTYPEN.index(self.typ) + 1) % 3]
                self.auswahl = 0
            self.seite = "nrst"
        elif name == "soft3":
            self.radius = min(len(RADIEN) - 1, self.radius + 1)
        elif name == "soft4":
            self.radius = max(0, self.radius - 1)
        elif name in ("soft5", "map"):
            self.nord_oben = not self.nord_oben
        elif name == "direct":
            self.seite = "direct"
        elif name == "info":
            self.seite = "nrst" if self.seite == "info" else "info"
        elif name == "enter":
            if self.seite in ("nrst", "direct"):
                eintrag = self.gewaehlt()
                if eintrag:
                    self.ziel = eintrag
                    self.seite = "nav"
                    self.melde(f"DIRECT {eintrag['id']}")
                    self.sende_ziel()
        elif name == "navgps":
            # Kursinstrument NAV1 und Autopilot folgen dem GPS bzw. wieder dem VOR
            self.auftrag += 1
            sende([("elite/gps/quelle-auftrag", self.auftrag)])
        else:
            self.melde("KOMMT NOCH")

    def beruehrt(self, ereignis):
        for x1, y1, x2, y2, name in self.flaechen:
            if x1 <= ereignis.x <= x2 and y1 <= ereignis.y <= y2:
                self.taste(name)
                return

    # --- Daten ---------------------------------------------------------------------
    def liste(self, daten):
        """Eintraege des gewaehlten Typs, nach Distanz, mit brg (rw) und dis."""
        umgebung = daten.get("umgebung") or {}
        if self.typ == "apt":
            roh = umgebung.get("apt") or []
        else:
            roh = [n for n in umgebung.get("nav") or [] if n.get("typ") == self.typ]
        ergebnis = []
        for e in roh:
            if not isinstance(e, dict) or e.get("lat") is None:
                continue
            brg, dis = kurs_distanz(daten["lat"], daten["lon"], e["lat"], e["lon"])
            ergebnis.append(dict(e, brg=brg, dis=dis, typ=self.typ))
        ergebnis.sort(key=lambda e: e["dis"])
        return ergebnis

    def gewaehlt(self):
        daten = self.leser.aktuell()
        if not daten:
            return None
        liste = self.liste(daten)
        if not liste:
            return None
        self.auswahl = min(self.auswahl, len(liste) - 1)
        return liste[self.auswahl]

    def sende_ziel(self):
        self.auftrag += 1
        self.ziel_gesendet = time.monotonic()
        sende([("elite/gps/ziel/ident", self.ziel["id"]),
               ("elite/gps/ziel/lat", self.ziel["lat"]),
               ("elite/gps/ziel/lon", self.ziel["lon"]),
               ("elite/gps/ziel/typ", FG_TYP[self.ziel["typ"]]),
               ("elite/gps/ziel/auftrag", self.auftrag)])

    def pruefe_ziel(self):
        """Hat FlightGear das Ziel nicht (z. B. nach seinem Neustart), alle 5 s nochmals senden."""
        daten = self.leser.aktuell()
        if not self.ziel or not daten or "typ" not in self.ziel:
            return
        if daten.get("gps-modus") == "dto" and daten.get("gps-id") == self.ziel["id"]:
            return
        if time.monotonic() - getattr(self, "ziel_gesendet", 0) > 5:
            self.sende_ziel()

    # --- Zeichnen ------------------------------------------------------------------
    def takt(self):
        while self.ereignisse:
            self.taste(self.ereignisse.popleft())
        self.pruefe_monitor()
        self.pruefe_ziel()
        self.zeichne()
        self.after(200, self.takt)

    def zeichne(self):
        lw = self.leinwand
        lw.delete("all")
        self.flaechen = []
        breite, hoehe = lw.winfo_width(), lw.winfo_height()
        if breite < 50:
            return
        if self.einzeln:
            if self.karte_an and self.an:
                self.zeichne_karte(0, 0, breite, hoehe)
            else:
                self.zeichne_apollo(0, 0, breite, hoehe)
            return
        apollo_h = int(hoehe * (0.30 if hoehe > breite else 0.40))
        self.zeichne_apollo(0, 0, breite, apollo_h)
        self.zeichne_karte(0, apollo_h, breite, hoehe)

    def zeichne_apollo(self, x0, y0, x1, y1):
        lw = self.leinwand
        rand = 12
        lw.create_rectangle(x0, y0, x1, y1, fill=RAHMEN, outline="")
        dx0, dy0, dx1, dy1 = x0 + rand, y0 + rand, x1 - rand, y1 - rand
        lw.create_rectangle(dx0, dy0, dx1, dy1, fill=SCHWARZ, outline="#555")
        if not self.an:
            return
        zeile_h = (dy1 - dy0) / 8
        # Schrift nach Zeilenhoehe, im schmalen hohen Feld aber nur so gross, dass zwei
        # Spalten nebeneinander passen
        groesse = min(zeile_h * 0.8, (dx1 - dx0) / 13.5)
        schrift = ("Consolas", -int(groesse), "bold")
        klein = ("Consolas", -int(groesse * 0.75), "bold")

        def text(spalte, zeile, inhalt, farbe=BERNSTEIN, s=schrift, anker="w"):
            lw.create_text(dx0 + 14 + spalte * (dx1 - dx0 - 28), dy0 + zeile_h * (zeile + 0.6),
                           text=inhalt, fill=farbe, font=s, anchor=anker)

        def balken(zeile):
            lw.create_rectangle(dx0 + 4, dy0 + zeile_h * (zeile + 0.1), dx1 - 4,
                                dy0 + zeile_h * (zeile + 1.1), fill=BERNSTEIN, outline="")

        daten = self.leser.aktuell()
        if not daten:
            text(0.5, 2.5, "WARTE AUF FLIGHTGEAR", anker="center")
        else:
            magvar = daten.get("magvar-deg") or 0
            if self.seite == "nav":
                self.seite_nav(daten, magvar, text)
            else:
                self.seite_liste(daten, magvar, text, klein, balken)
        if daten:
            # wem NAV1 (Kursinstrument, Autopilot) folgt
            if daten.get("quelle-gps"):
                lw.create_rectangle(dx1 - 14 - zeile_h * 2.2, dy0 + zeile_h * 0.15,
                                    dx1 - 6, dy0 + zeile_h * 1.05, fill=BERNSTEIN,
                                    outline="")
                text(1, 0, "GPS", SCHWARZ, klein, "e")
            else:
                text(1, 0, "VLOC", BERNSTEIN, klein, "e")
        meldung, bis = self.meldung
        if meldung and time.monotonic() < bis:
            text(0.62, 0, meldung, s=klein, anker="center")
        # Bildschirmtasten 1-5 (auch per Touch)
        teil = (dx1 - dx0) / len(SOFTKEYS)
        oben = dy1 - zeile_h * 1.2
        for i, (name, beschriftung) in enumerate(SOFTKEYS):
            kx0, kx1 = dx0 + i * teil + 4, dx0 + (i + 1) * teil - 4
            lw.create_rectangle(kx0, oben, kx1, dy1 - 4, outline=BERNSTEIN_DUNKEL)
            lw.create_text((kx0 + kx1) / 2, (oben + dy1 - 4) / 2, text=beschriftung,
                           fill=BERNSTEIN, font=klein)
            self.flaechen.append((kx0, oben, kx1, dy1, name))
        if self.einzeln:
            # Touch auf die Anzeige selbst = MAP-Taste (nach den Bildschirmtasten pruefen)
            self.flaechen.append((dx0, dy0, dx1, dy1, "map"))

    def seite_nav(self, daten, magvar, text):
        gs = daten.get("gs-kt") or 0
        trk = ((daten.get("trk-deg") or 0) - magvar) % 360
        if self.ziel:
            brg, dis = kurs_distanz(daten["lat"], daten["lon"],
                                    self.ziel["lat"], self.ziel["lon"])
            text(0, 0, f"-> {self.ziel['id']}")
            text(0, 1.3, f"DIS {dis:6.1f} NM")
            text(0.55, 1.3, f"BRG {(brg - magvar) % 360:03.0f}°")
            # Soll-Kurs (DTK) und Ablage (XTK) vom FlightGear-GPS, wenn es dasselbe Ziel hat
            if daten.get("gps-modus") == "dto" and daten.get("gps-id") == self.ziel["id"]:
                text(0, 2.6, f"DTK {daten.get('dtk-deg') or 0:03.0f}°")
                text(0.55, 2.6, f"XTK {abs(daten.get('xtk-nm') or 0):4.1f} NM")
            if gs > 30:
                minuten = dis / gs * 60
                text(0, 5.2, f"ETE {int(minuten // 60):d}:{int(minuten % 60):02d}")
        else:
            text(0, 0, "NAV  - KEIN ZIEL -")
            text(0, 1.3, "DIRECT + ENTER = ZIEL")
        text(0, 3.9, f"GS  {gs:5.0f} KT")
        text(0.55, 3.9, f"TRK {trk:03.0f}°")
        text(0.55, 5.2, f"ALT {daten.get('alt-ft') or 0:5.0f} FT")

    def seite_liste(self, daten, magvar, text, klein, balken):
        liste = self.liste(daten)
        titel = {"nrst": "NRST", "direct": "DIRECT?", "info": "INFO"}[self.seite]
        text(0, 0, f"{titel} {TYPNAME[self.typ]}")
        if not liste:
            text(0, 2, "NICHTS IN 60 NM")
            return
        self.auswahl = min(self.auswahl, len(liste) - 1)
        if self.seite == "info":
            e = liste[self.auswahl]
            text(0, 1.3, e["id"])
            text(0, 2.4, str(e.get("name") or "")[:28], s=klein)
            if self.typ == "apt":
                text(0, 3.4, f"PISTE {e.get('piste') or 0} FT", s=klein)
            else:
                freq = e.get("freq") or 0
                text(0, 3.4, f"FRQ {freq / 100:.2f}" if self.typ == "vor" else f"FRQ {freq}",
                     s=klein)
            text(0, 4.4, f"BRG {(e['brg'] - magvar) % 360:03.0f}°  DIS {e['dis']:.1f} NM",
                 s=klein)
            return
        erste = max(0, min(self.auswahl - 2, len(liste) - ZEILEN_NRST))
        for i, e in enumerate(liste[erste:erste + ZEILEN_NRST]):
            nr = erste + i
            farbe = SCHWARZ if nr == self.auswahl else BERNSTEIN
            zeile = 1.2 + i
            if nr == self.auswahl:
                balken(zeile)
            text(0, zeile, f"{e['id']:<5}", farbe, klein)
            text(0.3, zeile, f"{(e['brg'] - magvar) % 360:03.0f}°", farbe, klein)
            text(0.55, zeile, f"{e['dis']:5.1f} NM", farbe, klein)

    def zeichne_karte(self, x0, y0, x1, y1):
        lw = self.leinwand
        lw.create_rectangle(x0, y0, x1, y1, fill=KARTE, outline="")
        daten = self.leser.aktuell()
        mx = (x0 + x1) / 2
        my = (y0 + y1) / 2 if self.nord_oben else y0 + (y1 - y0) * 0.68
        radius_nm = RADIEN[self.radius]
        massstab = (min(x1 - x0, y1 - y0) / 2 - 20) / radius_nm   # Pixel pro NM
        schrift = ("Segoe UI", -16, "bold")
        if daten:
            lat0, lon0 = daten["lat"], daten["lon"]
            trk = daten.get("trk-deg") or 0
            drehung = 0 if self.nord_oben else math.radians(trk)

            def punkt(lat, lon):
                ost = (lon - lon0) * 60 * math.cos(math.radians(lat0))
                nord = (lat - lat0) * 60
                ost, nord = (ost * math.cos(drehung) - nord * math.sin(drehung),
                             ost * math.sin(drehung) + nord * math.cos(drehung))
                return mx + ost * massstab, my - nord * massstab

            def sichtbar(x, y):
                return x0 + 8 <= x <= x1 - 8 and y0 + 8 <= y <= y1 - 8

            r = radius_nm * massstab
            lw.create_oval(mx - r, my - r, mx + r, my + r, outline="#2c4a66")
            lw.create_oval(mx - r / 2, my - r / 2, mx + r / 2, my + r / 2, outline="#2c4a66",
                           dash=(4, 4))
            lw.create_text(mx + r / 2 * 0.71 + 4, my - r / 2 * 0.71, text=f"{radius_nm / 2:g}",
                           fill="#6f93b5", font=("Segoe UI", -14), anchor="sw")
            umgebung = daten.get("umgebung") or {}
            for nav in umgebung.get("nav") or []:
                if not isinstance(nav, dict) or nav.get("lat") is None:
                    continue
                x, y = punkt(nav["lat"], nav["lon"])
                if not sichtbar(x, y):
                    continue
                farbe = FARBE.get(nav.get("typ"), "#aaa")
                if nav.get("typ") == "vor":
                    lw.create_polygon(*[c for w in range(6) for c in (
                        x + 8 * math.cos(w * math.pi / 3), y + 8 * math.sin(w * math.pi / 3))],
                        outline=farbe, fill="")
                else:
                    lw.create_oval(x - 4, y - 4, x + 4, y + 4, fill=farbe, outline="")
                lw.create_text(x + 10, y, text=nav.get("id", ""), fill=farbe,
                               font=("Segoe UI", -13), anchor="w")
            for apt in umgebung.get("apt") or []:
                if not isinstance(apt, dict) or apt.get("lat") is None:
                    continue
                x, y = punkt(apt["lat"], apt["lon"])
                if not sichtbar(x, y):
                    continue
                gross = (apt.get("piste") or 0) >= 4000
                g = 7 if gross else 5
                lw.create_oval(x - g, y - g, x + g, y + g, outline=FARBE["apt"], width=2)
                lw.create_text(x + g + 3, y, text=apt.get("id", ""), fill=FARBE["apt"],
                               font=schrift if gross else ("Segoe UI", -13), anchor="w")
            if self.ziel:
                x, y = punkt(self.ziel["lat"], self.ziel["lon"])
                laenge = math.hypot(x - mx, y - my)
                if laenge > r:   # am Kartenrand enden lassen
                    x, y = mx + (x - mx) * r / laenge, my + (y - my) * r / laenge
                lw.create_line(mx, my, x, y, fill=FARBE["ziel"], width=3)
            # Flugzeug: zeigt in Flugrichtung
            winkel = math.radians(trk) if self.nord_oben else 0
            spitze = [(0, -16), (10, 12), (0, 6), (-10, 12)]
            lw.create_polygon(*[c for px, py in spitze for c in (
                mx + px * math.cos(winkel) - py * math.sin(winkel),
                my + px * math.sin(winkel) + py * math.cos(winkel))],
                fill="white", outline="black")
            # Nordpfeil
            nx, ny = x0 + 34, y0 + 34
            lw.create_oval(nx - 22, ny - 22, nx + 22, ny + 22, outline="#6f93b5")
            lw.create_text(nx + 22 * math.sin(-drehung), ny - 22 * math.cos(-drehung),
                           text="N", fill="white", font=schrift)
        else:
            lw.create_text(mx, my, text="keine Daten von FlightGear", fill="#6f93b5",
                           font=schrift)
        # Touch-Knoepfe der Karte
        knoepfe = [("soft4", "+"), ("soft3", "-"), ("soft5", "N/TRK")]
        if self.einzeln:
            knoepfe.append(("map", "TEXT"))     # zurueck zur Apollo-Anzeige
        for i, (name, beschriftung) in enumerate(knoepfe):
            bx1 = x1 - 12
            bx0 = bx1 - (110 if len(beschriftung) > 1 else 60)
            by0 = y1 - 12 - (i + 1) * 70
            lw.create_rectangle(bx0, by0, bx1, by0 + 60, fill="#16314d", outline="#6f93b5")
            lw.create_text((bx0 + bx1) / 2, by0 + 30, text=beschriftung, fill="white",
                           font=("Segoe UI", -26 if len(beschriftung) == 1 else -18, "bold"))
            self.flaechen.append((bx0, by0, bx1, by0 + 60, name))
        lw.create_text(x0 + 12, y1 - 12, anchor="sw", fill="#6f93b5", font=("Segoe UI", -15),
                       text=f"{'NORDEN OBEN' if self.nord_oben else 'FLUGRICHTUNG OBEN'}   "
                            f"Radius {radius_nm} NM")


def main():
    wurzel = tk.Tk()
    wurzel.withdraw()
    fenster = GpsFenster(wurzel)
    fenster.protocol("WM_DELETE_WINDOW", lambda: (fenster.schliessen(), wurzel.destroy()))
    fenster.bind("<Escape>", lambda _e: (fenster.schliessen(), wurzel.destroy()))
    wurzel.mainloop()


if __name__ == "__main__":
    main()
