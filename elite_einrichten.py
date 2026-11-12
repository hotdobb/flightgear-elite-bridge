"""Einrichten auf einem neuen Rechner (Knopf "Einrichten" im Bedienfenster).

Sucht FlightGear, dessen Datenordner (FG_ROOT) und die Seneca II, kopiert die
Protokolldateien, korrigiert zwei bekannte Fehler der Seneca und erzeugt
Elite-Cockpit, Aussensicht, 2D-Instrumentenbrett und Innenraum (seneca_elite.py).
Nach einem Update der Seneca oder von FlightGear einfach noch einmal ausfuehren.

Woher die Ordner kommen: FlightGear schreibt bei jedem Start ins Logbuch
(%APPDATA%\\flightgear.org\\fgfs.log), wo FG_ROOT und der Download-Ordner liegen.
Deshalb muss FlightGear mindestens einmal gestartet worden sein.
"""

import glob
import os
import re
import shutil
import string

import seneca_elite

ORDNER = os.path.dirname(os.path.abspath(__file__))
PROTOKOLLE = ["elite.xml", "elite_aus.xml"]
FG_LOGBUCH = os.path.join(os.environ.get("APPDATA", ""), "flightgear.org", "fgfs.log")
BENUTZER = os.path.expanduser("~")


def aus_logbuch():
    """FG_ROOT, Download- und Flugzeug-Ordner aus dem letzten FlightGear-Logbuch."""
    werte = {}
    try:
        with open(FG_LOGBUCH, encoding="utf-8", errors="replace") as f:
            for zeile in f:
                for schluessel, muster in (("fg_root", r'FG_ROOT = "Path "([^"]+)"'),
                                           ("download", r'download-dir = "([^"]+)"'),
                                           ("flugzeug", r'aircraft-dir = "([^"]+)"')):
                    treffer = re.search(muster, zeile)
                    if treffer and schluessel not in werte:
                        werte[schluessel] = os.path.normpath(treffer.group(1))
                if len(werte) == 3:
                    break
    except OSError:
        pass
    return werte


def finde_fgfs(gespeichert=None):
    """fgfs.exe: gespeichert, sonst in "Program Files" auf allen Laufwerken (neueste)."""
    if gespeichert and os.path.isfile(gespeichert):
        return gespeichert
    funde = []
    for lw in string.ascii_uppercase:
        if os.path.exists(f"{lw}:\\"):
            for programme in ("Program Files", "Program Files (x86)"):
                funde += glob.glob(f"{lw}:\\{programme}\\FlightGear*\\bin\\fgfs.exe")
    return sorted(funde)[-1] if funde else None


def finde_fg_root():
    root = aus_logbuch().get("fg_root")
    if root and os.path.isdir(root):
        return root
    funde = sorted(glob.glob(os.path.join(BENUTZER, "FlightGear", "Downloads", "fgdata_*")))
    return funde[-1] if funde else None


def finde_seneca():
    """Ordner der Seneca II (mit SenecaII-set.xml) oder None."""
    log = aus_logbuch()
    kandidaten = []
    if log.get("flugzeug", "").endswith("SenecaII"):
        kandidaten.append(log["flugzeug"])
    for download in (log.get("download"), os.path.join(BENUTZER, "FlightGear", "Downloads"),
                     os.path.join(BENUTZER, "Documents", "FlightGear", "Downloads")):
        if download:
            kandidaten += sorted(glob.glob(os.path.join(download, "Aircraft", "*", "Aircraft",
                                                        "SenecaII")), reverse=True)
    root = finde_fg_root()
    if root:
        kandidaten.append(os.path.join(root, "Aircraft", "SenecaII"))
    for ordner in kandidaten:
        if os.path.isfile(os.path.join(ordner, "SenecaII-set.xml")):
            return ordner
    return None


# --- Bekannte Fehler der Seneca II (FGAddon, Stand 2024) -------------------------------
def mit_sicherung(pfad, alt, neu):
    """Schreibt neu; legt vorher einmal pfad.original an."""
    if not os.path.exists(pfad + ".original"):
        with open(pfad + ".original", "w", encoding="utf-8") as f:
            f.write(alt)
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(neu)


def korrigiere_seneca(seneca):
    meldungen = []
    # 1) Rechter Propeller-Regler: Faktor 0.1 statt 1.0 -> rechter Propeller bleibt in
    #    Segelstellung, der rechte Motor springt nicht an
    pfad = os.path.join(seneca, "Systems", "prop-governor.xml")
    if os.path.isfile(pfad):
        text = open(pfad, encoding="utf-8").read()
        alt = "<value>0.1</value> <!-- 1/max-underspeed-rpm -->"
        if text.count(alt) == 1 and "<value>1.0</value> <!-- 1/max-underspeed-rpm" in text:
            mit_sicherung(pfad, text, text.replace(
                alt, "<value>1.0</value> <!-- 1/max-underspeed-rpm (Elite-Bruecke: war 0.1, "
                     "wie links korrigiert) -->"))
            meldungen.append("Seneca-Fehler korrigiert: rechter Propeller-Regler")
    # 2) Kreisel-Geraeusche ohne <condition> -> Fehlermeldung von FlightGear 2024
    pfad = os.path.join(seneca, "SenecaII-Sound.xml")
    if os.path.isfile(pfad):
        text = open(pfad, encoding="utf-8").read()
        neu = text
        for name, prop in (("HSIGyro", "/instrumentation/kcs55/kg102/spin-norm"),
                           ("TCGyro", "/instrumentation/turn-indicator/spin")):
            muster = rf"(<name>{name}</name>\n(\s*)<mode>looped</mode>\n)(?!\s*<condition>)"
            neu = re.sub(muster, lambda t: (t.group(1) + t.group(2) + "<condition>\n"
                                            + t.group(2) + f"  <property>{prop}</property>\n"
                                            + t.group(2) + "</condition>\n"), neu, count=1)
        if neu != text:
            mit_sicherung(pfad, text, neu)
            meldungen.append("Seneca-Fehler korrigiert: Kreisel-Geraeusche")
    return meldungen


def kopiere_protokolle(fg_root):
    ziel = os.path.join(fg_root, "Protocol")
    if not os.path.isdir(ziel):
        raise RuntimeError(f"Ordner Protocol fehlt in {fg_root}")
    kopiert = []
    for name in PROTOKOLLE:
        quelle, nach = os.path.join(ORDNER, name), os.path.join(ziel, name)
        if not os.path.exists(nach) or open(quelle, "rb").read() != open(nach, "rb").read():
            shutil.copyfile(quelle, nach)
            kopiert.append(name)
    return kopiert


def einrichten(elite_cockpit=True):
    """Fuehrt alles aus. Rueckgabe: (alles gut?, Liste von Meldungen fuer den Nutzer)."""
    meldungen, ok = [], True
    fg_root = finde_fg_root()
    if not fg_root:
        return False, ["FlightGear-Datenordner nicht gefunden. Bitte FlightGear einmal "
                       "starten (auch nur bis zum Launcher) und dann erneut 'Einrichten'."]
    meldungen.append(f"FlightGear-Daten: {fg_root}")
    try:
        kopiert = kopiere_protokolle(fg_root)
        meldungen.append("Protokolldateien kopiert: " + ", ".join(kopiert) if kopiert
                         else "Protokolldateien sind aktuell.")
    except (OSError, RuntimeError) as fehler:
        ok = False
        meldungen.append(f"FEHLER beim Kopieren der Protokolldateien: {fehler}")
    seneca = finde_seneca()
    if not seneca:
        return False, meldungen + ["Seneca II nicht gefunden. Bitte im FlightGear-Launcher "
                                   "unter 'Flugzeuge' die 'Seneca II' installieren, einmal "
                                   "damit starten und dann erneut 'Einrichten'."]
    meldungen.append(f"Seneca II: {seneca}")
    seneca_elite.setze_seneca_ordner(seneca)
    try:
        meldungen += korrigiere_seneca(seneca)
        seneca_elite.erzeuge()
        seneca_elite.erzeuge_panel()
        meldungen.append("Elite-Cockpit, Aussensicht, 2D-Instrumentenbrett und Innenraum "
                         "erzeugt.")
        meldungen.append(seneca_elite.setze_cockpit(elite_cockpit))
    except Exception as fehler:      # Seneca-Version mit anderem Aufbau o. ae.
        ok = False
        meldungen.append(f"FEHLER beim Erzeugen der Seneca-Dateien: {fehler}")
    return ok, meldungen


if __name__ == "__main__":
    ergebnis, texte = einrichten()
    print("\n".join(texte))
    print("FERTIG" if ergebnis else "NICHT VOLLSTAENDIG")
