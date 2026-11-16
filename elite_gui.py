"""Bedienfenster fuer die Elite-Bruecke.

Kopf: Status von Pro Panel, Pedale, AP-3000 und FlightGear (gruen = verbunden), Profil.
Reiter in der Reihenfolge des Gebrauchs:
- Start: FlightGear starten (Monitore), Anzeigen im Instrumentenbrett (Namen, Navi und
  Bordcomputer), Bruecke starten/stoppen; unter "Erweitert" die Startoptionen
- Achsen kalibrieren: Achsen live sehen, Min/Mitte/Max uebernehmen (von Hand oder
  automatisch), Umkehrschub-Raste, Totzone, Kurve, Richtung umdrehen
- Wippen und Trimmung: Richtung umdrehen, Tempo der Hoehentrimmung
- Schalter-Test: was die Bruecke aus jedem Schalter macht, und jede Meldung der Geraete
- Meldungen der Bruecke
Kalibrierung, Wippen und Trimmung gelten je Flugzeug-Profil (Profil "standard" + eigene);
die Bruecke waehlt das Profil des geflogenen Flugzeugs selbst.

Einstellungen: einstellungen.json (gleicher Ordner).

Start:  pythonw elite_gui.py   (oder bruecke-fenster.cmd)
"""

import copy
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from tkinter import messagebox, ttk

import elite_bord
import elite_einrichten
import elite_fg as fg
import elite_gps
import seneca_elite

ORDNER = os.path.dirname(os.path.abspath(__file__))
# fgfs.exe: gespeichert, sonst gesucht (elite_einrichten.finde_fgfs)
MONITORE = {
    1: ("1 Monitor: 3D-Cockpit", None),
    2: ("2 Monitore: Aussensicht + Instrumente",
        os.path.join(ORDNER, "fg-config", "zwei-monitore.xml")),
    3: ("3 Monitore: + GPS (kommt noch)", None),
}
# Cockpit der Seneca: "elite" = ohne die Teile, die es als Hardware gibt;
# "original" = unveraendertes Seneca-Cockpit (stellt SenecaII-set.xml um)
# Sichtweite der vollen Landschaftsdetails -> /sim/rendering/static-lod/detailed (Meter)
DETAIL = {"1,5 km": 1500, "3 km": 3000, "5 km": 5000, "10 km": 10000,
          "wie im Launcher eingestellt": None}
COCKPIT = {"elite": "Elite-Cockpit (ohne die Teile, die es als Hardware gibt)",
           "original": "Original-Seneca-Cockpit (alles wie im normalen FlightGear)"}
# Modell-Zeilen der Zwei-Monitor-Vorlage (Seneca ohne Armaturenbrett)
MODELL_AUSSEN = """    <model>
      <!-- Seneca ohne Armaturenbrett (erzeugt von seneca_elite.py) -->
      <path>Aircraft/SenecaII/Models/SenecaII-Aussen.xml</path>
    </model>
"""
GRUEN, ROT, GRAU = "#2e9e44", "#c0392b", "#9a9a9a"
# Das Instrumentenbrett ist 16:10 (1024 x 640 Einheiten). Auf einem Monitor mit anderem
# Seitenverhaeltnis schneidet FlightGear im Vollbild einen Teil ab; dann bekommt das
# Fenster "Instrumente" die groesste 16:10-Flaeche in der Mitte dieses Monitors.
KONFIG_AKTUELL = os.path.join(ORDNER, "fg-config", "zwei-monitore-aktuell.xml")
# Alles, was der Schalter-Test zeigt, steht auch hier (beginnt bei jedem Start neu)
MITSCHRIFT = os.path.join(ORDNER, "schalter-mitschrift.log")
FENSTER_VOLLBILD = """<name type="string">Instrumente</name>
            <screen type="int">1</screen>
            <fullscreen type="bool">true</fullscreen>"""
FENSTER_EINGEPASST = """<name type="string">Instrumente</name>
            <screen type="int">{screen}</screen>
            <fullscreen type="bool">false</fullscreen>
            <decoration type="bool">false</decoration>
            <x type="int">{x}</x>
            <y type="int">{y}</y>
            <width type="int">{breite}</width>
            <height type="int">{hoehe}</height>"""


class DEVMODE(ctypes.Structure):
    _fields_ = [("dmDeviceName", ctypes.c_wchar * 32), ("dmSpecVersion", ctypes.c_ushort),
                ("dmDriverVersion", ctypes.c_ushort), ("dmSize", ctypes.c_ushort),
                ("dmDriverExtra", ctypes.c_ushort), ("dmFields", ctypes.c_ulong),
                ("dmPositionX", ctypes.c_long), ("dmPositionY", ctypes.c_long),
                ("dmDisplayOrientation", ctypes.c_ulong),
                ("dmDisplayFixedOutput", ctypes.c_ulong), ("dmColor", ctypes.c_short),
                ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short),
                ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short),
                ("dmFormName", ctypes.c_wchar * 32), ("dmLogPixels", ctypes.c_ushort),
                ("dmBitsPerPel", ctypes.c_ulong), ("dmPelsWidth", ctypes.c_ulong),
                ("dmPelsHeight", ctypes.c_ulong), ("dmDisplayFlags", ctypes.c_ulong),
                ("dmDisplayFrequency", ctypes.c_ulong), ("dmRest", ctypes.c_byte * 32)]


class DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("DeviceName", ctypes.c_wchar * 32),
                ("DeviceString", ctypes.c_wchar * 128), ("StateFlags", ctypes.c_ulong),
                ("DeviceID", ctypes.c_wchar * 128), ("DeviceKey", ctypes.c_wchar * 128)]


def monitore_pixel(mit_namen=False):
    """Angeschlossene Monitore in Windows-Reihenfolge (= FlightGear screen 0, 1, ...):
    [(x, y, breite, hoehe, ist_hauptmonitor)] in echten Pixeln, unabhaengig von der
    Skalierung; x/y = Lage auf dem Windows-Desktop. Mit mit_namen haengt als sechster Wert
    der Windows-Name an (z. B. "\\\\.\\DISPLAY2")."""
    liste, nr = [], 0
    geraet = DISPLAY_DEVICE()
    geraet.cb = ctypes.sizeof(geraet)
    while ctypes.windll.user32.EnumDisplayDevicesW(None, nr, ctypes.byref(geraet), 0):
        nr += 1
        if not geraet.StateFlags & 1:      # nicht Teil des Desktops
            continue
        modus = DEVMODE()
        modus.dmSize = ctypes.sizeof(modus)
        if ctypes.windll.user32.EnumDisplaySettingsW(geraet.DeviceName, -1, ctypes.byref(modus)):
            eintrag = (modus.dmPositionX, modus.dmPositionY, modus.dmPelsWidth,
                       modus.dmPelsHeight, bool(geraet.StateFlags & 4))
            liste.append(eintrag + (geraet.DeviceName,) if mit_namen else eintrag)
    return liste


# Vom Nutzer gewaehlte Monitore als FlightGear-Nummer (screen 0, 1, ...); None = automatisch:
# Aussensicht auf dem Windows-Hauptbildschirm, Instrumente auf dem 16:10-Monitor.
MONITOR_WAHL = {"aussen": None, "instrumente": None}


def monitor_texte():
    """Beschriftung je Monitor fuer die Auswahl, in FlightGear-Reihenfolge. Ohne Nummern:
    Die Zahlen aus Windows ("Identifizieren") stimmen nicht mit der Reihenfolge ueberein,
    in der FlightGear die Monitore zaehlt - deshalb Groesse und Lage."""
    liste = monitore_pixel(mit_namen=True)
    haupt = next((m for m in liste if m[4]), None)
    texte = []
    for x, y, breite, hoehe, primaer, name in liste:
        if primaer or haupt is None:
            lage = "Hauptbildschirm"
        else:
            # wo er laut Windows-Anordnung liegt, vom Hauptbildschirm aus gesehen
            dx = (x + breite / 2) - (haupt[0] + haupt[2] / 2)
            dy = (y + hoehe / 2) - (haupt[1] + haupt[3] / 2)
            teile = []
            if abs(dx) > haupt[2] / 2:
                teile.append("rechts" if dx > 0 else "links")
            if abs(dy) > haupt[3] / 2:
                teile.append("unten" if dy > 0 else "oben")
            lage = " ".join(teile) or "daneben"
        texte.append(f"{breite} x {hoehe}, {lage}")
    return texte


def aussen_monitor(liste=None):
    """FlightGear-Nummer des Monitors fuer die Aussensicht."""
    liste = monitore_pixel() if liste is None else liste
    wahl = MONITOR_WAHL["aussen"]
    if wahl is not None and 0 <= wahl < len(liste):
        return wahl
    return next((nr for nr, m in enumerate(liste) if m[4]), 0)


def instrumenten_fenster():
    """Wo das Fenster "Instrumente" auf dem zweiten Monitor liegt: (screen, x, y, breite,
    hoehe, vollbild) mit x/y relativ zu diesem Monitor, dazu dessen Lage (mx, my) auf dem
    Desktop; None ohne zweiten Monitor."""
    liste = monitore_pixel()
    aussen = aussen_monitor(liste)
    zweite = [(nr, m) for nr, m in enumerate(liste) if nr != aussen]
    if not zweite:
        return None
    wahl = MONITOR_WAHL["instrumente"]
    if wahl is not None and wahl != aussen and 0 <= wahl < len(liste):
        zweite = [(wahl, liste[wahl])]
    # bei mehreren: der 16:10-Monitor (Anmite, Touch) passt genau zum Instrumentenbrett
    zweite.sort(key=lambda eintrag: abs(eintrag[1][2] / eintrag[1][3] - 1.6) > 0.02)
    nr, (mx, my, breite, hoehe, _) = zweite[0]
    if abs(breite / hoehe - 1.6) <= 0.02:
        return nr, 0, 0, breite, hoehe, True, mx, my
    # kein Vollbild: Die Windows-Taskleiste bleibt sichtbar, also nur die Flaeche darueber
    # nutzen (sonst verdeckt sie die untersten Instrumente)
    frei = arbeitsflaeche(mx, my) or (mx, my, mx + breite, my + hoehe)
    fb, fh = frei[2] - frei[0], frei[3] - frei[1]
    b, h = (round(fh * 1.6), fh) if fb / fh > 1.6 else (fb, round(fb / 1.6))
    return (nr, frei[0] - mx + (fb - b) // 2, frei[1] - my + (fh - h) // 2, b, h, False,
            mx, my)


def arbeitsflaeche(x, y):
    """Flaeche ohne Taskleiste (links, oben, rechts, unten) des Monitors, auf dem der
    Desktop-Punkt x/y liegt. Stimmt nur in echten Pixeln (siehe main)."""
    class PUNKT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class INFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", ctypes.c_long * 4),
                    ("rcWork", ctypes.c_long * 4), ("dwFlags", ctypes.c_ulong)]

    nutzer = ctypes.windll.user32
    nutzer.MonitorFromPoint.restype = ctypes.c_void_p
    monitor = nutzer.MonitorFromPoint(PUNKT(x + 10, y + 10), 2)
    info = INFO()
    info.cbSize = ctypes.sizeof(info)
    if not nutzer.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
        return None
    return tuple(info.rcWork)


def fg_laeuft():
    """Laeuft fgfs.exe gerade? (Einrichten aendert Dateien, die FlightGear geladen hat.)"""
    try:
        ausgabe = subprocess.run(["tasklist", "/FI", "IMAGENAME eq fgfs.exe", "/NH"],
                                 capture_output=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except OSError:
        return False
    return b"fgfs.exe" in (ausgabe or b"").lower()


def schreibe_monitor_konfig(cockpit="elite"):
    """Schreibt zwei-monitore-aktuell.xml passend zum zweiten Monitor; Rueckgabe = Meldung.
    Mit dem Original-Cockpit zeigt die Aussensicht das volle Seneca-Cockpit."""
    with open(MONITORE[2][1], encoding="utf-8") as f:
        text = f.read()
    if cockpit == "original":
        text = text.replace(MODELL_AUSSEN, "")
    # Aussensicht: Hauptbildschirm oder der gewaehlte Monitor
    aussen = aussen_monitor()
    text = text.replace('<name type="string">Aussensicht</name>\n'
                        '            <screen type="int">0</screen>',
                        '<name type="string">Aussensicht</name>\n'
                        f'            <screen type="int">{aussen}</screen>')
    meldung = "Instrumente: Vollbild auf Monitor 2"
    fenster = instrumenten_fenster()
    if fenster and FENSTER_VOLLBILD in text:
        nr, x, y, b, h, vollbild = fenster[:6]
        if vollbild:
            meldung = f"Instrumente: Vollbild auf Monitor {nr + 1}"
            # nur im Fenster "Instrumente" (die Aussensicht kann auch screen 1 sein)
            text = text.replace(FENSTER_VOLLBILD, FENSTER_VOLLBILD.replace(
                '<screen type="int">1</screen>', f'<screen type="int">{nr}</screen>'))
        else:
            text = text.replace(FENSTER_VOLLBILD, FENSTER_EINGEPASST.format(
                screen=nr, x=x, y=y, breite=b, hoehe=h))
            meldung = (f"Instrumente: Monitor {nr + 1} ist nicht 16:10, "
                       f"Fenster {b}x{h} in der Mitte")
    with open(KONFIG_AKTUELL, "w", encoding="utf-8") as f:
        f.write(text)
    return meldung


def feld_platz(feld):
    """Bildschirm-Rechteck (x, y, breite, hoehe) eines freien Felds im Instrumentenbrett
    (z. B. seneca_elite.NAVI_FREI), in echten Pixeln auf dem Desktop; None ohne zweiten
    Monitor."""
    fenster = instrumenten_fenster()
    if not fenster:
        return None
    _, x, y, b, h, _, mx, my = fenster
    x1, y1, x2, y2 = feld
    pro_einheit = b / seneca_elite.PANEL_W
    return (round(mx + x + x1 * pro_einheit), round(my + y + h - y2 * pro_einheit),
            round((x2 - x1) * pro_einheit), round((y2 - y1) * pro_einheit))
HINWEIS_KAL = ("Zahlen = Rohwerte des Geraets (0-127); 'hier' uebernimmt die aktuelle "
               "Stellung. Raste: Haekchen an = hinter der Markierung ist Umkehrschub. "
               "Fuer 'Automatisch' vorher Horn, Pedale und Trimmknopf in die Mitte.")
HINWEIS_AUTO = ("Jetzt jeden Hebel, das Horn (links/rechts, vor/zurueck), die Pedale, beide "
                "Bremsen und den Trimmknopf einmal bis zu BEIDEN Anschlaegen bewegen. "
                "Dann 'Fertig' druecken. Die Raste stellst du danach mit 'hier' ein.")


class Ausgabe:
    """Leitet print() der Bruecke in das Meldungsfeld um."""

    def __init__(self, ziel):
        self.ziel = ziel

    def write(self, text):
        if text:
            self.ziel.put(text)

    def flush(self):
        pass


class Fenster:
    def __init__(self, wurzel):
        self.wurzel = wurzel
        self.meldungen = queue.Queue()
        sys.stdout = sys.stderr = Ausgabe(self.meldungen)
        self.bruecke = fg.Bruecke()
        self.einstellungen = self.bruecke.einstellungen
        self.start = self.einstellungen.setdefault("start", {})
        # Seneca-Ordner: gespeichert (nach "Einrichten"), sonst suchen
        seneca = self.start.get("seneca")
        if not (seneca and os.path.isdir(seneca)):
            seneca = elite_einrichten.finde_seneca()
        seneca_elite.setze_seneca_ordner(seneca)
        self.faden = None
        self.achs_zeilen = []
        self.auto_kal = None   # waehrend "Automatisch kalibrieren": Mitte, Min, Max

        wurzel.title("Elite-Bruecke")
        wurzel.geometry("1200x800")
        wurzel.protocol("WM_DELETE_WINDOW", self.schliessen)
        self.baue_kopf()
        reiter = ttk.Notebook(wurzel)
        reiter.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        # Reiter in der Reihenfolge des Gebrauchs: taeglicher Start, Einstellungen je
        # Flugzeug-Profil, zuletzt Pruefen und Fehlersuche
        self.baue_fg_start(reiter)
        self.baue_kalibrieren(reiter)
        self.baue_wippen(reiter)
        self.baue_schaltertest(reiter)
        self.baue_meldungen(reiter)

        if self.start.get("bruecke_automatisch", True):
            self.starte_bruecke()
        # GPS-Bildschirm von selbst, wenn der kleine Touch-Monitor angeschlossen ist
        self.gps = self.bord = None
        self.monitor_geprueft = 0.0
        try:
            with open(MITSCHRIFT, "w", encoding="utf-8") as f:
                f.write(f"Mitschrift ab {time.strftime('%d.%m.%Y %H:%M:%S')}\n")
        except OSError:
            pass
        if elite_gps.gps_monitor():
            self.gps_umschalten()
        self.takt()

    # --- Kopf: Status und Bruecke ----------------------------------------------------
    def baue_kopf(self):
        kopf = ttk.Frame(self.wurzel, padding=8)
        kopf.pack(fill="x")
        self.lampen = {}
        for name in ("Pro Panel", "Pedale", "AP-3000", "FlightGear"):
            feld = ttk.Frame(kopf)
            feld.pack(side="left", padx=(0, 16))
            leinwand = tk.Canvas(feld, width=18, height=18, highlightthickness=0)
            leinwand.pack(side="left")
            punkt = leinwand.create_oval(2, 2, 16, 16, fill=GRAU, outline="")
            ttk.Label(feld, text=name).pack(side="left", padx=4)
            self.lampen[name] = (leinwand, punkt)
        self.profil_text = ttk.Label(kopf, text="")
        self.profil_text.pack(side="right")

    def beschriftung_senden(self, fg_da):
        """Schickt die Wahl an FlightGear, wenn sie neu ist oder FlightGear neu da ist."""
        if not fg_da:
            self.beschriftung_gesendet = None
            return
        wert = self.beschriftung.get()
        if self.beschriftung_laeuft or wert == self.beschriftung_gesendet:
            return
        self.beschriftung_laeuft = True

        def arbeit():
            try:
                anfrage = urllib.request.Request(
                    "http://127.0.0.1:8080/json/elite/beschriftung", method="POST",
                    data=json.dumps({"value": int(wert)}).encode(),
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(anfrage, timeout=1).close()
                self.beschriftung_gesendet = wert
            except OSError:
                pass   # beim naechsten Takt noch einmal
            finally:
                self.beschriftung_laeuft = False
        threading.Thread(target=arbeit, daemon=True).start()

    def gps_umschalten(self):
        if self.bord is not None and self.bord.winfo_exists():
            self.bord.schliessen()
        self.bord = None
        if self.gps is not None and self.gps.winfo_exists():
            self.gps.schliessen()
            self.gps = None
        else:
            # ohne eigenen GPS-Monitor: ins freie Feld des Instrumentenbretts (2 Monitore),
            # daneben Bordcomputer/Checkliste
            platz = None
            if not elite_gps.gps_monitor() and self.start.get("monitore", 2) == 2:
                platz = feld_platz(seneca_elite.NAVI_FREI)
            self.gps = elite_gps.GpsFenster(self.wurzel, self.bruecke.ap3000.gps_ereignisse,
                                            platz)
            if platz:
                self.bord = elite_bord.BordFenster(self.wurzel,
                                                   feld_platz(seneca_elite.RESERVE_FREI))

    def folge_monitor(self):
        """Navi und Bordcomputer bleiben in ihren Feldern, auch wenn der Instrumenten-Monitor
        in Windows verschoben, getauscht oder anders aufgeloest wird (alle 3 s geprueft)."""
        if time.monotonic() - self.monitor_geprueft < 3:
            return
        self.monitor_geprueft = time.monotonic()
        for fenster, feld in ((self.gps, seneca_elite.NAVI_FREI),
                              (self.bord, seneca_elite.RESERVE_FREI)):
            if fenster is not None and fenster.winfo_exists() and fenster.platz:
                fenster.setze_platz(feld_platz(feld))

    def starte_bruecke(self):
        if self.faden and self.faden.is_alive():
            return
        self.faden = threading.Thread(target=self.bruecke.lauf, daemon=True)
        self.faden.start()

    def stoppe_bruecke(self):
        self.bruecke.halt()

    def laeuft(self):
        return self.faden is not None and self.faden.is_alive()

    # --- Reiter Meldungen --------------------------------------------------------------
    def baue_meldungen(self, reiter):
        seite = ttk.Frame(reiter, padding=6)
        reiter.add(seite, text="Meldungen")
        self.meldefeld = tk.Text(seite, height=20, wrap="word", state="disabled")
        leiste = ttk.Scrollbar(seite, command=self.meldefeld.yview)
        self.meldefeld.configure(yscrollcommand=leiste.set)
        leiste.pack(side="right", fill="y")
        self.meldefeld.pack(fill="both", expand=True)

    # --- Reiter Kalibrieren ------------------------------------------------------------
    def baue_profilwahl(self, seite, aktualisiere):
        zeile = ttk.Frame(seite)
        zeile.pack(fill="x", pady=(0, 6))
        ttk.Label(zeile, text="Profil bearbeiten:").pack(side="left")
        wahl = ttk.Combobox(zeile, state="readonly", width=18)
        wahl.pack(side="left", padx=6)
        wahl.bind("<<ComboboxSelected>>", lambda _e: aktualisiere())
        ttk.Button(zeile, text="Profil fuer aktuelles Flugzeug anlegen",
                   command=self.neues_profil).pack(side="left", padx=6)
        ttk.Button(zeile, text="Profil loeschen", command=lambda: self.loesche_profil(wahl)
                   ).pack(side="left")
        ttk.Button(zeile, text="Speichern", command=self.speichern).pack(side="right")
        return wahl

    def profile_auffrischen(self):
        namen = sorted(self.einstellungen["profile"], key=lambda n: (n != "standard", n))
        for wahl in (self.kal_wahl, self.wip_wahl):
            wahl["values"] = namen
            if wahl.get() not in namen:
                wahl.set(self.bruecke.profil_name if self.bruecke.profil_name in namen
                         else "standard")

    def bearbeitet(self, wahl):
        return self.einstellungen["profile"][wahl.get() or "standard"]

    def neues_profil(self):
        name = self.bruecke.flugzeug
        if not name:
            messagebox.showinfo("Profil", "FlightGear laeuft nicht oder meldet kein Flugzeug.\n"
                                "Bitte erst FlightGear mit dem Flugzeug starten.")
            return
        profile = self.einstellungen["profile"]
        if name not in profile:
            profile[name] = copy.deepcopy(self.bruecke.profil)
            print(f"Profil '{name}' angelegt (Kopie von '{self.bruecke.profil_name}').")
        self.bruecke.pruefe_flugzeug()
        self.profile_auffrischen()
        self.kal_wahl.set(name)
        self.wip_wahl.set(name)
        self.kal_laden()
        self.wip_laden()

    def loesche_profil(self, wahl):
        name = wahl.get()
        if name == "standard":
            messagebox.showinfo("Profil", "Das Standard-Profil bleibt immer erhalten.")
            return
        if messagebox.askyesno("Profil", f"Profil '{name}' loeschen?"):
            del self.einstellungen["profile"][name]
            if self.bruecke.profil_name == name:
                self.bruecke.profil_name = "standard"
            self.profile_auffrischen()
            self.kal_laden()
            self.wip_laden()

    def baue_kalibrieren(self, reiter):
        seite = ttk.Frame(reiter, padding=6)
        reiter.add(seite, text="Achsen kalibrieren")
        self.kal_wahl = self.baue_profilwahl(seite, self.kal_laden)
        zeile = ttk.Frame(seite)
        zeile.pack(fill="x")
        self.kal_hinweis = ttk.Label(zeile, text=HINWEIS_KAL, wraplength=820)
        self.kal_hinweis.pack(side="left")
        self.knopf_auto = ttk.Button(zeile, text="Automatisch kalibrieren",
                                     command=self.auto_kalibrieren)
        self.knopf_auto.pack(side="right")
        self.knopf_abbruch = ttk.Button(zeile, text="Abbrechen", command=self.auto_ende)
        tabelle = ttk.Frame(seite)
        tabelle.pack(fill="both", expand=True, pady=6)
        for spalte, titel in enumerate(["Achse", "Roh", "Ergebnis", "", "Min / 0", "Mitte",
                                        "Max / 1", "Raste (Umkehr)", "Totzone %",
                                        "Kurve %", "umkehren"]):
            ttk.Label(tabelle, text=titel, font=("Segoe UI", 9, "bold")).grid(
                row=0, column=spalte, sticky="w", padx=4)
        for nr, achse in enumerate(fg.ACHSEN, start=1):
            geraet, code, name, art, *_ = achse
            ttk.Label(tabelle, text=name).grid(row=nr, column=0, sticky="w", padx=4, pady=2)
            zeile = {"achse": achse, "felder": [], "raste": None}
            zeile["roh"] = ttk.Label(tabelle, text="-", width=4)
            zeile["roh"].grid(row=nr, column=1, padx=4)
            zeile["balken"] = ttk.Progressbar(tabelle, length=140, maximum=100)
            zeile["balken"].grid(row=nr, column=2, padx=4)
            zeile["wert"] = ttk.Label(tabelle, text="", width=12)
            zeile["wert"].grid(row=nr, column=3, padx=4)
            for spalte in ((4, 5, 6) if art == "ruder" else (4, 6)):
                feld, wert = self.zahlfeld(tabelle, 0, 127, hier=(geraet, code))
                feld.grid(row=nr, column=spalte, sticky="w", padx=4)
                zeile["felder"].append(wert)
            if name in fg.RASTE_ACHSEN:
                feld, wert = self.zahlfeld(tabelle, 0, 127, hier=(geraet, code))
                an = tk.BooleanVar()
                ttk.Checkbutton(feld, variable=an, command=self.kal_uebernehmen).pack(
                    side="left", before=feld.winfo_children()[0])
                feld.grid(row=nr, column=7, sticky="w", padx=4)
                zeile["raste"] = (an, wert)
            feld, zeile["totzone"] = self.zahlfeld(tabelle, 0, 30)
            feld.grid(row=nr, column=8, sticky="w", padx=4)
            feld, zeile["kurve"] = self.zahlfeld(tabelle, 0, 100, schritt=10)
            feld.grid(row=nr, column=9, sticky="w", padx=4)
            zeile["umkehren"] = tk.BooleanVar()
            ttk.Checkbutton(tabelle, variable=zeile["umkehren"],
                            command=self.kal_uebernehmen).grid(row=nr, column=10)
            self.achs_zeilen.append(zeile)

    def zahlfeld(self, eltern, von, bis, schritt=1, hier=None):
        """Zahlenfeld; mit hier=(Geraet, Code) dazu ein Knopf fuer den aktuellen Rohwert."""
        feld = ttk.Frame(eltern)
        wert = tk.IntVar()
        wert.trace_add("write", lambda *_: self.kal_uebernehmen())
        ttk.Spinbox(feld, from_=von, to=bis, increment=schritt, width=4,
                    textvariable=wert).pack(side="left")
        if hier:
            ttk.Button(feld, text="hier", width=5,
                       command=lambda: self.setze_roh(wert, *hier)).pack(side="left", padx=2)
        return feld, wert

    def auto_kalibrieren(self):
        """1. Druck: Mitte merken und Min/Max sammeln; 2. Druck: Ergebnis uebernehmen."""
        roh = self.bruecke.roh
        if self.auto_kal is None:
            if not any(schluessel in roh for schluessel in fg.ACHS_CODES):
                messagebox.showinfo("Kalibrieren", "Keine Werte - sind Pro Panel und Pedale "
                                    "verbunden und laeuft die Bruecke?")
                return
            mitte = {z["achse"][2]: roh.get(z["achse"][:2]) for z in self.achs_zeilen
                     if z["achse"][3] == "ruder"}
            self.auto_kal = {"mitte": mitte, "min": {}, "max": {}}
            self.knopf_auto.configure(text="Fertig - uebernehmen")
            self.knopf_abbruch.pack(side="right", padx=6)
            self.kal_hinweis.configure(text=HINWEIS_AUTO)
            return
        fertig, fehlt = [], []
        self.laedt = True
        for z in self.achs_zeilen:
            achse = z["achse"]
            schluessel, name = achse[:2], achse[2]
            unten, oben = self.auto_kal["min"].get(schluessel), self.auto_kal["max"].get(
                schluessel)
            if unten is None or oben - unten < 20:
                fehlt.append(name)
                continue
            # 1 Rohwert Abstand: die Enden werden sicher erreicht
            unten, oben = unten + 1, oben - 1
            alt = [v.get() for v in z["felder"]]
            if achse[3] == "ruder":
                mitte = self.auto_kal["mitte"].get(name)
                if mitte is None or not unten < mitte < oben:
                    fehlt.append(name)
                    continue
                neu = [oben, mitte, unten] if alt[0] > alt[2] else [unten, mitte, oben]
            else:
                neu = [oben, unten] if alt[0] > alt[1] else [unten, oben]
            for variable, wert in zip(z["felder"], neu):
                variable.set(wert)
            fertig.append(name)
        self.laedt = False
        self.kal_uebernehmen()
        print(f"Automatisch kalibriert: {', '.join(fertig) or '-'}")
        if fehlt:
            print(f"Nicht (genug) bewegt, unveraendert: {', '.join(fehlt)}")
        print("Mit 'Speichern' dauerhaft sichern.")
        self.auto_ende()

    def auto_ende(self):
        self.auto_kal = None
        self.knopf_auto.configure(text="Automatisch kalibrieren")
        self.knopf_abbruch.pack_forget()
        self.kal_hinweis.configure(text=HINWEIS_KAL)

    def setze_roh(self, variable, geraet, code):
        wert = self.bruecke.roh.get((geraet, code))
        if wert is None:
            print("Kein Wert - ist das Geraet verbunden?")
            return
        variable.set(wert)
        self.kal_uebernehmen()

    def kal_laden(self):
        profil = self.bearbeitet(self.kal_wahl)
        self.laedt = True   # waehrend des Ladens nichts halbfertig zurueckschreiben
        for z in self.achs_zeilen:
            eintrag = profil["achsen"][z["achse"][2]]
            for variable, wert in zip(z["felder"], eintrag["grenzen"]):
                variable.set(wert)
            z["umkehren"].set(eintrag["umkehren"])
            z["totzone"].set(eintrag["totzone"])
            z["kurve"].set(eintrag["kurve"])
            if z["raste"]:
                an, wert = z["raste"]
                an.set(eintrag["raste"] is not None)
                wert.set(eintrag["grenzen"][0] if eintrag["raste"] is None
                         else eintrag["raste"])
        self.laedt = False

    def kal_uebernehmen(self):
        """Werte aus den Feldern sofort ins bearbeitete Profil (wirkt live, wenn aktiv)."""
        if getattr(self, "laedt", False) or not self.kal_wahl.get():
            return
        profil = self.bearbeitet(self.kal_wahl)
        for z in self.achs_zeilen:
            try:
                grenzen = [v.get() for v in z["felder"]]
                totzone, kurve = z["totzone"].get(), z["kurve"].get()
                raste = z["raste"][1].get() if z["raste"] and z["raste"][0].get() else None
            except tk.TclError:
                continue  # Feld gerade leer beim Tippen
            if len(set(grenzen)) < len(grenzen):
                continue  # gleiche Werte wuerden durch null teilen
            profil["achsen"][z["achse"][2]] = {
                "grenzen": grenzen, "umkehren": z["umkehren"].get(),
                "totzone": min(30, max(0, totzone)), "kurve": min(100, max(0, kurve)),
                "raste": raste}

    # --- Reiter Schalter-Test ----------------------------------------------------------
    def baue_schaltertest(self, reiter):
        seite = ttk.Frame(reiter, padding=6)
        reiter.add(seite, text="Schalter-Test")
        ttk.Label(seite, text="Schalter, Taste oder Knopf bedienen: links leuchtet, was die "
                  "Bruecke an FlightGear schickt (Wert ungleich 0 = gruen). Rechts steht jede "
                  "Meldung der Geraete mit Code und Wert - auch von Tasten, die noch nicht "
                  "belegt sind.", wraplength=940).pack(anchor="w")
        teile = ttk.Frame(seite)
        teile.pack(fill="both", expand=True, pady=6)
        links = ttk.Frame(teile)
        links.pack(side="left", fill="y", padx=(0, 10))
        self.schalter_zellen = {}
        for nr, (name, _) in enumerate(fg.SCHALTER):
            zelle = tk.Label(links, text=name, width=16, anchor="w", relief="groove", padx=4)
            zelle.grid(row=nr % 13, column=nr // 13, padx=2, pady=1, sticky="w")
            self.schalter_zellen[name] = zelle
        self.zellen_farbe = zelle.cget("background")
        rechts = ttk.Frame(teile)
        rechts.pack(side="left", fill="both", expand=True)
        ttk.Button(rechts, text="Liste leeren", command=lambda: self.leere(self.testliste)
                   ).pack(anchor="e")
        self.testliste = tk.Text(rechts, height=18, wrap="none", state="disabled",
                                 font=("Consolas", 9))
        leiste = ttk.Scrollbar(rechts, command=self.testliste.yview)
        self.testliste.configure(yscrollcommand=leiste.set)
        leiste.pack(side="right", fill="y")
        self.testliste.pack(fill="both", expand=True)

    @staticmethod
    def leere(feld):
        feld.configure(state="normal")
        feld.delete("1.0", "end")
        feld.configure(state="disabled")

    def schaltertest_auffrischen(self, profil):
        panel_da = self.laeuft() and self.bruecke.verbunden().get("Pro Panel")
        stabil = self.bruecke.entpreller.stabil
        for name, regel in fg.SCHALTER:
            zelle = self.schalter_zellen[name]
            if not panel_da:
                zelle.configure(text=f"{name}  -", background=self.zellen_farbe)
                continue
            wert = fg.schalterwert(name, regel, stabil, profil)
            zelle.configure(text=f"{name}  {wert}",
                            background=GRUEN if wert else self.zellen_farbe)
        protokoll = self.bruecke.protokoll
        if not protokoll:
            return
        self.testliste.configure(state="normal")
        while protokoll:
            zeit, geraet, code, wert = protokoll.popleft()
            name = (geraet == fg.AP3000 and fg.ap3000_klartext(code, wert)) or \
                (geraet == fg.PRO_PANEL and fg.pro_panel_klartext(code, wert)) or \
                fg.CODE_NAMEN.get((geraet, code), "(noch nicht belegt)")
            zeile = (f"{time.strftime('%H:%M:%S', time.localtime(zeit))}"
                     f"  {fg.GERAETE_NAMEN.get(geraet, geraet):9}  Code {code:3}"
                     f"  Wert {wert:3} ({wert:07b})  {name}\n")
            self.testliste.insert("end", zeile)
            # dieselbe Zeile in die Mitschrift (zum Anlernen unbekannter Schalter)
            try:
                with open(MITSCHRIFT, "a", encoding="utf-8") as f:
                    f.write(zeile)
            except OSError:
                pass
        zeilen = int(self.testliste.index("end-1c").split(".")[0])
        if zeilen > 500:
            self.testliste.delete("1.0", f"{zeilen - 500}.0")
        self.testliste.see("end")
        self.testliste.configure(state="disabled")

    # --- Reiter Wippen -----------------------------------------------------------------
    def baue_wippen(self, reiter):
        seite = ttk.Frame(reiter, padding=6)
        reiter.add(seite, text="Wippen und Trimmung")
        self.wip_wahl = self.baue_profilwahl(seite, self.wip_laden)
        ttk.Label(seite, text="Haekchen = Richtung umgedreht.").pack(anchor="w", pady=(0, 6))
        self.wippen = {}
        for name, titel in fg.UMKEHRBAR.items():
            variable = tk.BooleanVar()
            ttk.Checkbutton(seite, text=titel, variable=variable,
                            command=self.wip_uebernehmen).pack(anchor="w", pady=2)
            self.wippen[name] = variable
        # Tempo der Hoehentrimmung (Horn) je Profil
        zeile = ttk.Frame(seite)
        zeile.pack(anchor="w", pady=(12, 2))
        ttk.Label(zeile, text="Tempo Hoehentrimm (1 = Standard, groesser = schneller):"
                  ).pack(side="left")
        self.trimm_tempo = tk.DoubleVar(value=1.0)
        ttk.Spinbox(zeile, from_=0.2, to=10, increment=0.2, width=5, format="%.1f",
                    textvariable=self.trimm_tempo, command=self.wip_uebernehmen
                    ).pack(side="left", padx=6)
        self.trimm_tempo.trace_add("write", lambda *_: self.wip_uebernehmen())

    def wip_laden(self):
        profil = self.bearbeitet(self.wip_wahl)
        for name, variable in self.wippen.items():
            variable.set(profil["umkehren"].get(name, False))
        self.trimm_tempo.set(profil.get("trimm_tempo", 1.0))

    def wip_uebernehmen(self):
        profil = self.bearbeitet(self.wip_wahl)
        for name, variable in self.wippen.items():
            profil["umkehren"][name] = variable.get()
        try:
            profil["trimm_tempo"] = min(10.0, max(0.2, round(self.trimm_tempo.get(), 1)))
        except tk.TclError:
            pass   # Feld gerade leer oder halb getippt

    # --- Reiter FlightGear starten -----------------------------------------------------
    def baue_fg_start(self, reiter):
        """Erste Seite: alles fuer den taeglichen Start, von oben nach unten in der
        Reihenfolge, in der man es braucht. Selten Gebrauchtes steht unter "Erweitert"."""
        seite = ttk.Frame(reiter, padding=6)
        reiter.add(seite, text="Start")

        # 1. FlightGear starten
        feld = ttk.LabelFrame(seite, text="1. FlightGear starten", padding=8)
        feld.pack(fill="x", pady=(0, 8))
        self.monitore = tk.IntVar(value=self.start.get("monitore", 2))
        for nr, (titel, _) in MONITORE.items():
            knopf = ttk.Radiobutton(feld, text=titel, value=nr, variable=self.monitore,
                                    command=self.fg_vorschau)
            knopf.pack(anchor="w")
            if nr == 3:
                knopf.state(["disabled"])
        # Welcher Monitor was zeigt (gilt fuer "2 Monitore"); "Automatisch" = Aussensicht auf
        # dem Windows-Hauptbildschirm, Instrumente auf dem 16:10-Monitor
        self.monitor_wahl = {}
        for schluessel, titel in (("aussen", "Aussensicht auf:"),
                                  ("instrumente", "Instrumente auf:")):
            zeile = ttk.Frame(feld)
            zeile.pack(anchor="w", pady=(4, 0))
            ttk.Label(zeile, text=titel, width=16).pack(side="left")
            wahl = ttk.Combobox(zeile, state="readonly", width=42)
            wahl.configure(postcommand=self.monitor_wahl_fuellen)
            wahl.bind("<<ComboboxSelected>>", lambda _e: self.monitor_wahl_uebernehmen())
            wahl.pack(side="left")
            self.monitor_wahl[schluessel] = wahl
        self.monitor_wahl_fuellen()
        ttk.Label(feld, text="Cockpit der Seneca:").pack(anchor="w", pady=(6, 0))
        self.cockpit = tk.StringVar(value=self.start.get("cockpit", "elite"))
        for wert, titel in COCKPIT.items():
            ttk.Radiobutton(feld, text=titel, value=wert, variable=self.cockpit,
                            command=self.fg_vorschau).pack(anchor="w")
        # KI-Verkehr: an grossen Flughaefen hunderte KI-Flugzeuge (Zuerich: 327), die in jedem
        # Fenster mitgezeichnet werden -> Bildrate halbiert (gemessen 2026-11-16: 15 statt 31)
        self.ki_verkehr = tk.BooleanVar(value=self.start.get("ki_verkehr", False))
        ttk.Checkbutton(feld, text="KI-Verkehr (belebte Flughaefen, kostet viel Bildrate)",
                        variable=self.ki_verkehr, command=self.fg_vorschau
                        ).pack(anchor="w", pady=(6, 0))
        # Volle Detailstufe der Landschaft (Baeume, Gebaeude): weit = Prozessor am Anschlag.
        # Gemessen 2026-11-16 bei 26 km in LSZH: 30 Bilder/s, ohne Landschaft 60.
        zeile = ttk.Frame(feld)
        zeile.pack(fill="x", pady=(6, 0))
        ttk.Label(zeile, text="Volle Landschaftsdetails bis:").pack(side="left")
        self.detail = ttk.Combobox(zeile, state="readonly", width=24, values=list(DETAIL))
        self.detail.set(self.start.get("detail", "3 km"))
        if self.detail.get() not in DETAIL:
            self.detail.set("3 km")
        self.detail.bind("<<ComboboxSelected>>", lambda _e: self.fg_vorschau())
        self.detail.pack(side="left", padx=6)
        ttk.Label(zeile, text="(weniger = mehr Bilder pro Sekunde)").pack(side="left")
        zeile = ttk.Frame(feld)
        zeile.pack(fill="x", pady=(6, 0))
        ttk.Button(zeile, text="FlightGear starten", command=self.starte_fg).pack(side="left")
        ttk.Label(zeile, text="Flugzeug, Flughafen und Piste waehlst du danach wie gewohnt "
                  "im Launcher.").pack(side="left", padx=10)

        # 2. Anzeigen im Instrumentenbrett
        feld = ttk.LabelFrame(seite, text="2. Im Instrumentenbrett", padding=8)
        feld.pack(fill="x", pady=(0, 8))
        # Namensschilder der Instrumente im 2D-Panel (Wahl bleibt gespeichert)
        self.beschriftung = tk.BooleanVar(value=self.start.get("beschriftung", False))
        self.beschriftung_gesendet = None   # was FlightGear zuletzt bestaetigt bekommen hat
        self.beschriftung_laeuft = False
        ttk.Checkbutton(feld, text="Namen ueber den Instrumenten zeigen",
                        variable=self.beschriftung,
                        command=lambda: self.start.update(beschriftung=self.beschriftung.get())
                        ).pack(anchor="w")
        zeile = ttk.Frame(feld)
        zeile.pack(fill="x", pady=(6, 0))
        ttk.Button(zeile, text="Navi und Bordcomputer ein/aus", command=self.gps_umschalten
                   ).pack(side="left")
        ttk.Label(zeile, text="Oeffnen sich beim Start mit 2 Monitoren von selbst."
                  ).pack(side="left", padx=10)

        # 3. Bruecke
        feld = ttk.LabelFrame(seite, text="3. Bruecke (Verbindung zur Elite-Hardware)",
                              padding=8)
        feld.pack(fill="x", pady=(0, 8))
        self.auto = tk.BooleanVar(value=self.start.get("bruecke_automatisch", True))
        ttk.Checkbutton(feld, text="Beim Oeffnen dieses Fensters von selbst starten",
                        variable=self.auto, command=self.fg_vorschau).pack(anchor="w")
        zeile = ttk.Frame(feld)
        zeile.pack(fill="x", pady=(6, 0))
        self.knopf_start = ttk.Button(zeile, text="Bruecke starten", command=self.starte_bruecke)
        self.knopf_start.pack(side="left")
        self.knopf_stopp = ttk.Button(zeile, text="Bruecke stoppen", command=self.stoppe_bruecke)
        self.knopf_stopp.pack(side="left", padx=6)

        # Erweitert: braucht man nur selten
        feld = ttk.LabelFrame(seite, text="Erweitert", padding=8)
        feld.pack(fill="both", expand=True)
        zeile = ttk.Frame(feld)
        zeile.pack(fill="x", pady=(0, 6))
        ttk.Button(zeile, text="Einrichten", command=self.einrichten).pack(side="left")
        ttk.Label(zeile, text="Auf neuem Rechner und nach jedem Update von FlightGear oder "
                  "der Seneca (FlightGear vorher einmal gestartet, Seneca installiert)."
                  ).pack(side="left", padx=10)
        self.httpd = tk.BooleanVar(value=self.start.get("httpd", True))
        ttk.Checkbutton(feld, text="Web-Schnittstelle (Port 8080) - noetig fuer Profilwahl, "
                        "Navi, Bordcomputer und Instrumenten-Namen", variable=self.httpd,
                        command=self.fg_vorschau).pack(anchor="w")
        zeile = ttk.Frame(feld)
        zeile.pack(fill="x", pady=(6, 0))
        ttk.Label(zeile, text="fgfs.exe:").pack(side="left")
        self.fgfs = tk.StringVar(value=elite_einrichten.finde_fgfs(self.start.get("fgfs")) or "")
        ttk.Entry(zeile, textvariable=self.fgfs).pack(side="left", fill="x", expand=True,
                                                      padx=6)
        ttk.Label(feld, text="Weitere Startoptionen (eine pro Zeile; im Launcher unter "
                  "'Zusaetzliche Einstellungen' nichts doppelt eintragen):"
                  ).pack(anchor="w", pady=(6, 0))
        self.zusatz = tk.Text(feld, height=3)
        self.zusatz.insert("1.0", self.start.get("zusatz", ""))
        self.zusatz.bind("<KeyRelease>", lambda _e: self.fg_vorschau())
        self.zusatz.pack(fill="x")
        ttk.Label(feld, text="Befehl, mit dem FlightGear gestartet wird:").pack(anchor="w",
                                                                                  pady=(6, 0))
        self.vorschau = tk.Text(feld, height=5, state="disabled", wrap="word")
        self.vorschau.pack(fill="x")
        self.fg_vorschau()

    def monitor_wahl_fuellen(self):
        """Auswahllisten mit den gerade angeschlossenen Monitoren fuellen; die gespeicherte
        Wahl (FlightGear-Nummer) bleibt, solange es den Monitor gibt."""
        texte = ["Automatisch"] + monitor_texte()
        for schluessel, wahl in self.monitor_wahl.items():
            nr = self.start.get("monitor_" + schluessel)
            if nr is None or not 0 <= nr < len(texte) - 1:
                nr = None
            MONITOR_WAHL[schluessel] = nr
            wahl.configure(values=texte)
            wahl.current(0 if nr is None else nr + 1)

    def monitor_wahl_uebernehmen(self):
        for schluessel, wahl in self.monitor_wahl.items():
            nr = wahl.current() - 1
            self.start["monitor_" + schluessel] = MONITOR_WAHL[schluessel] = \
                None if nr < 0 else nr
        self.monitor_geprueft = 0.0      # Navi und Bordcomputer gleich mit umziehen

    def fg_befehl(self):
        befehl = [self.fgfs.get(), "--launcher",
                  "--generic=socket,in,30,127.0.0.1,5010,udp,elite",
                  "--generic=socket,out,10,127.0.0.1,5011,udp,elite_aus",
                  "--addon=" + os.path.join(ORDNER, "fg-addon")]
        if self.httpd.get():
            befehl.append("--httpd=8080")
        befehl.append("--enable-ai-traffic" if self.ki_verkehr.get() else "--disable-ai-traffic")
        meter = DETAIL.get(self.detail.get())
        if meter:
            befehl.append(f"--prop:/sim/rendering/static-lod/detailed={meter}")
        konfig = MONITORE[self.monitore.get()][1]
        if konfig:
            # starte_fg schreibt diese Datei passend zum angeschlossenen Monitor
            befehl.append("--config=" + KONFIG_AKTUELL)
        befehl += [z.strip() for z in self.zusatz.get("1.0", "end").splitlines() if z.strip()]
        return befehl

    def fg_vorschau(self):
        self.start.update(monitore=self.monitore.get(), cockpit=self.cockpit.get(),
                          ki_verkehr=self.ki_verkehr.get(), detail=self.detail.get(),
                          httpd=self.httpd.get(),
                          bruecke_automatisch=self.auto.get(), fgfs=self.fgfs.get(),
                          zusatz=self.zusatz.get("1.0", "end").strip())
        self.vorschau.configure(state="normal")
        self.vorschau.delete("1.0", "end")
        self.vorschau.insert("1.0", "\n".join(self.fg_befehl()))
        self.vorschau.configure(state="disabled")

    def starte_fg(self):
        self.fg_vorschau()
        befehl = self.fg_befehl()
        if not os.path.exists(befehl[0]):
            messagebox.showerror("FlightGear", f"fgfs.exe nicht gefunden:\n{befehl[0]}")
            return
        self.speichern()
        seneca = seneca_elite.SENECA
        if not seneca or not os.path.isfile(os.path.join(seneca, "Models", "SenecaII-Elite.xml")):
            if not messagebox.askyesno(
                    "FlightGear", "Die Seneca ist noch nicht eingerichtet (Elite-Cockpit, "
                    "Instrumentenbrett fehlen).\n\nTrotzdem starten? Sonst unter 'Erweitert' "
                    "auf 'Einrichten' druecken."):
                return
        else:
            try:
                print(seneca_elite.setze_cockpit(self.cockpit.get() == "elite"))
            except OSError as fehler:
                print("Cockpit nicht umgestellt:", fehler)
        if MONITORE[self.monitore.get()][1]:
            print(schreibe_monitor_konfig(self.cockpit.get()))
            # Navi-Display ins freie Feld des Instrumentenbretts
            if self.gps is None or not self.gps.winfo_exists():
                self.gps_umschalten()
        subprocess.Popen(befehl, cwd=os.path.dirname(befehl[0]))
        print("FlightGear-Launcher gestartet.")

    def einrichten(self):
        """Protokolle kopieren, Seneca korrigieren und Elite-Dateien erzeugen."""
        if fg_laeuft():
            messagebox.showinfo("Einrichten", "Bitte zuerst FlightGear beenden.")
            return
        self.config(cursor="watch")
        self.update()
        try:
            ok, meldungen = elite_einrichten.einrichten(self.cockpit.get() == "elite")
        finally:
            self.config(cursor="")
        if seneca_elite.SENECA:
            self.start["seneca"] = seneca_elite.SENECA
        gefunden = elite_einrichten.finde_fgfs(self.fgfs.get())
        if gefunden:
            self.fgfs.set(gefunden)
        else:
            ok = False
            meldungen.append("fgfs.exe nicht gefunden - bitte unten bei 'fgfs.exe' eintragen.")
        self.speichern()
        for zeile in meldungen:
            print("Einrichten:", zeile)
        (messagebox.showinfo if ok else messagebox.showwarning)(
            "Einrichten", ("Fertig.\n\n" if ok else "Nicht vollstaendig:\n\n") + "\n".join(meldungen))

    # --- Allgemein ---------------------------------------------------------------------
    def speichern(self):
        self.kal_uebernehmen()
        self.wip_uebernehmen()
        self.fg_vorschau()
        fg.speichere_einstellungen(self.einstellungen)
        print("Einstellungen gespeichert.")

    def takt(self):
        """10x pro Sekunde: Meldungen, Lampen, Rohwerte und Balken auffrischen."""
        while not self.meldungen.empty():
            self.meldefeld.configure(state="normal")
            self.meldefeld.insert("end", self.meldungen.get())
            self.meldefeld.see("end")
            self.meldefeld.configure(state="disabled")
        laeuft = self.laeuft()
        status = self.bruecke.verbunden() if laeuft else {}
        status["FlightGear"] = laeuft and self.bruecke.fg_da()
        self.beschriftung_senden(status["FlightGear"])
        self.folge_monitor()
        # Tasten INSTR / MAP am AP-3000: Bordcomputer <-> Checkliste, Navi-Text <-> Karte
        ereignisse = self.bruecke.ap3000.anzeige_ereignisse
        while ereignisse:
            taste = ereignisse.popleft()
            if taste == "map" and self.gps is not None and self.gps.winfo_exists():
                self.gps.taste("map")
            elif taste == "instr" and self.bord is not None and self.bord.winfo_exists():
                self.bord.wechsle_seite()
        for name, (leinwand, punkt) in self.lampen.items():
            farbe = GRAU if not laeuft else (GRUEN if status.get(name) else ROT)
            leinwand.itemconfigure(punkt, fill=farbe)
        flugzeug = self.bruecke.flugzeug or "-"
        self.profil_text.configure(text=f"Flugzeug: {flugzeug}   aktives Profil: "
                                   f"{self.bruecke.profil_name}")
        self.knopf_start.state(["disabled"] if laeuft else ["!disabled"])
        self.knopf_stopp.state(["!disabled"] if laeuft else ["disabled"])
        if not self.kal_wahl["values"] or set(self.kal_wahl["values"]) != set(
                self.einstellungen["profile"]):
            self.profile_auffrischen()
            self.kal_laden()
            self.wip_laden()
        # Kalibrieren zeigt das Profil, das gerade bearbeitet wird
        profil = self.bearbeitet(self.kal_wahl)
        roh = self.bruecke.roh
        for z in self.achs_zeilen:
            achse = z["achse"]
            wert = roh.get(achse[:2])
            z["roh"].configure(text="-" if wert is None else str(wert))
            if wert is not None and self.auto_kal is not None:
                kal = self.auto_kal
                kal["min"][achse[:2]] = min(wert, kal["min"].get(achse[:2], wert))
                kal["max"][achse[:2]] = max(wert, kal["max"].get(achse[:2], wert))
            ergebnis = fg.berechne(achse, roh, profil)
            umkehr = fg.umkehrschub(achse, roh, profil) if z["raste"] else 0.0
            if achse[3] == "ruder":
                z["balken"]["value"] = (ergebnis + 1) * 50
                z["wert"].configure(text=f"{ergebnis:+.2f}")
            else:
                z["balken"]["value"] = ergebnis * 100
                z["wert"].configure(text=f"UMKEHR {umkehr:.2f}" if umkehr > 0
                                    else f"{ergebnis:.2f}")
        self.schaltertest_auffrischen(self.bruecke.profil)
        self.wurzel.after(100, self.takt)

    def schliessen(self):
        if messagebox.askyesno("Elite-Bruecke", "Einstellungen speichern und beenden?"):
            self.speichern()
        self.bruecke.halt()
        if self.faden:
            self.faden.join(timeout=2)
        self.wurzel.destroy()


def main():
    # echte Pixel auf jedem Monitor (sonst rechnet Windows bei 125 % um und das
    # Navi-Display laege neben seinem Feld im Instrumentenbrett)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    wurzel = tk.Tk()
    Fenster(wurzel)
    wurzel.mainloop()


if __name__ == "__main__":
    main()
