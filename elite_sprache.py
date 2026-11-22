"""Sprache der Oberflaeche: Englisch (Standard) oder Deutsch.

Alle Texte stehen im Code auf Deutsch; t() liefert in Englisch die Uebersetzung aus
EN. Zusammengesetzte Meldungen (mit Namen, Zahlen) werden Wort fuer Wort ueber
PHRASEN uebersetzt. Die Wahl steht in einstellungen.json unter start/sprache und gilt
nach dem naechsten Oeffnen des Bedienfensters.
"""

import json
import os

EINSTELLUNGEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "einstellungen.json")
SPRACHEN = {"en": "English", "de": "Deutsch"}


def lade():
    # Neue Installation (noch keine Einstellungen): Englisch. Einstellungen von vor der
    # Sprachwahl ohne Eintrag: Deutsch, so wie sie bisher war.
    try:
        with open(EINSTELLUNGEN, encoding="utf-8") as f:
            sprache = json.load(f).get("start", {}).get("sprache", "de")
    except (OSError, ValueError, AttributeError):
        sprache = "en"
    return sprache if sprache in SPRACHEN else "en"


SPRACHE = lade()


def t(text):
    """Text in der gewaehlten Sprache."""
    if SPRACHE == "de" or not text:
        return text
    if text in EN:
        return EN[text]
    for deutsch, englisch in PHRASEN:
        text = text.replace(deutsch, englisch)
    return text


EN = {
    # --- Bedienfenster: Kopf, Reiter, Knoepfe ---
    "Elite-Bruecke": "Elite Bridge",
    "Pedale": "Pedals",
    "Meldungen": "Messages",
    "Start": "Start",
    "Achsen kalibrieren": "Calibrate axes",
    "Wippen und Trimmung": "Rockers and trim",
    "Schalter-Test": "Switch test",
    "Profil": "Profile",
    "Profil bearbeiten:": "Edit profile:",
    "Profil fuer aktuelles Flugzeug anlegen": "Create profile for current aircraft",
    "Profil loeschen": "Delete profile",
    "Speichern": "Save",
    "FlightGear laeuft nicht oder meldet kein Flugzeug.\nBitte erst FlightGear mit dem "
    "Flugzeug starten.":
        "FlightGear is not running or reports no aircraft.\nPlease start FlightGear with the "
        "aircraft first.",
    "Das Standard-Profil bleibt immer erhalten.": "The standard profile is always kept.",
    "Profil '{name}' loeschen?": "Delete profile '{name}'?",
    "Automatisch kalibrieren": "Calibrate automatically",
    "Abbrechen": "Cancel",
    "hier": "here",
    "Kalibrieren": "Calibrate",
    "Keine Werte - sind Pro Panel und Pedale verbunden und laeuft die Bruecke?":
        "No values - are the Pro Panel and pedals connected and is the bridge running?",
    "Fertig - uebernehmen": "Done - apply",
    "Mit 'Speichern' dauerhaft sichern.": "Press 'Save' to keep it.",
    "Kein Wert - ist das Geraet verbunden?": "No value - is the device connected?",
    "Zahlen = Rohwerte des Geraets (0-127); 'hier' uebernimmt die aktuelle Stellung. "
    "Raste: Haekchen an = hinter der Markierung ist Umkehrschub. Fuer 'Automatisch' vorher "
    "Horn, Pedale und Trimmknopf in die Mitte.":
        "Numbers = raw device values (0-127); 'here' takes the current position. Detent: "
        "ticked = beyond the mark is reverse thrust. Before 'automatically', centre the "
        "yoke, pedals and trim knob.",
    "Jetzt jeden Hebel, das Horn (links/rechts, vor/zurueck), die Pedale, beide Bremsen und "
    "den Trimmknopf einmal bis zu BEIDEN Anschlaegen bewegen. Dann 'Fertig' druecken. Die "
    "Raste stellst du danach mit 'hier' ein.":
        "Now move every lever, the yoke (left/right, forward/back), the pedals, both brakes "
        "and the trim knob once to BOTH stops. Then press 'Done'. Set the detent afterwards "
        "with 'here'.",
    "Achse": "Axis", "Roh": "Raw", "Ergebnis": "Result", "Mitte": "Centre",
    "Raste (Umkehr)": "Detent (reverse)", "Totzone %": "Dead zone %", "Kurve %": "Curve %",
    "umkehren": "reverse", "UMKEHR": "REVERSE", "Wert": "Value",
    "Schalter, Taste oder Knopf bedienen: links leuchtet, was die Bruecke an FlightGear "
    "schickt (Wert ungleich 0 = gruen). Rechts steht jede Meldung der Geraete mit Code und "
    "Wert - auch von Tasten, die noch nicht belegt sind.":
        "Operate a switch, key or knob: on the left you see what the bridge sends to "
        "FlightGear (value not 0 = green). On the right is every message of the devices "
        "with code and value - also from keys that are not assigned yet.",
    "Liste leeren": "Clear list",
    "(noch nicht belegt)": "(not assigned yet)",
    "Haekchen = Richtung umgedreht.": "Ticked = direction reversed.",
    "Tempo Hoehentrimm (1 = Standard, groesser = schneller):":
        "Elevator trim speed (1 = standard, larger = faster):",
    # --- Start ---
    "1. FlightGear starten": "1. Start FlightGear",
    "1 Monitor: 3D-Cockpit": "1 monitor: 3D cockpit",
    "2 Monitore: Aussensicht + Instrumente": "2 monitors: outside view + instruments",
    "3 Monitore: + GPS (kommt noch)": "3 monitors: + GPS (not yet)",
    "Aussensicht auf:": "Outside view on:",
    "Instrumente auf:": "Instruments on:",
    "Automatisch": "Automatic",
    "Hauptbildschirm": "main screen", "rechts": "right", "links": "left", "unten": "below",
    "oben": "above", "daneben": "next to it",
    "Cockpit der Seneca:": "Seneca cockpit:",
    "Elite-Cockpit (ohne die Teile, die es als Hardware gibt)":
        "Elite cockpit (without the parts that exist as hardware)",
    "Original-Seneca-Cockpit (alles wie im normalen FlightGear)":
        "Original Seneca cockpit (everything as in normal FlightGear)",
    "KI-Verkehr (belebte Flughaefen, kostet viel Bildrate)":
        "AI traffic (busy airports, costs a lot of frame rate)",
    "Volle Landschaftsdetails bis:": "Full scenery detail up to:",
    "wie im Launcher eingestellt": "as set in the launcher",
    "(weniger = mehr Bilder pro Sekunde)": "(less = more frames per second)",
    "FlightGear starten": "Start FlightGear",
    "Flugzeug, Flughafen und Piste waehlst du danach wie gewohnt im Launcher.":
        "Then choose aircraft, airport and runway in the launcher as usual.",
    "2. Im Instrumentenbrett": "2. In the instrument panel",
    "Namen ueber den Instrumenten zeigen": "Show names above the instruments",
    "Navi und Bordcomputer ein/aus": "GPS and status page on/off",
    "Oeffnen sich beim Start mit 2 Monitoren von selbst.":
        "Open by themselves when starting with 2 monitors.",
    "3. Bruecke (Verbindung zur Elite-Hardware)": "3. Bridge (connection to the Elite hardware)",
    "Beim Oeffnen dieses Fensters von selbst starten": "Start automatically when this window opens",
    "Bruecke starten": "Start bridge",
    "Bruecke stoppen": "Stop bridge",
    "Erweitert": "Advanced",
    "Einrichten": "Set up",
    "Einrichten:": "Setup:",
    "Auf neuem Rechner und nach jedem Update von FlightGear oder der Seneca (FlightGear "
    "vorher einmal gestartet, Seneca installiert).":
        "On a new computer and after every update of FlightGear or the Seneca (start "
        "FlightGear once before, Seneca installed).",
    "Web-Schnittstelle (Port 8080) - noetig fuer Profilwahl, Navi, Bordcomputer und "
    "Instrumenten-Namen":
        "Web interface (port 8080) - needed for profile choice, GPS, status page and "
        "instrument names",
    "Weitere Startoptionen (eine pro Zeile; im Launcher unter 'Zusaetzliche Einstellungen' "
    "nichts doppelt eintragen):":
        "More start options (one per line; do not enter anything twice under 'Additional "
        "Settings' in the launcher):",
    "Befehl, mit dem FlightGear gestartet wird:": "Command used to start FlightGear:",
    "fgfs.exe nicht gefunden:": "fgfs.exe not found:",
    "Die Seneca ist noch nicht eingerichtet (Elite-Cockpit, Instrumentenbrett fehlen)."
    "\n\nTrotzdem starten? Sonst unter 'Erweitert' auf 'Einrichten' druecken.":
        "The Seneca is not set up yet (Elite cockpit and instrument panel are missing)."
        "\n\nStart anyway? Otherwise press 'Set up' under 'Advanced'.",
    "Bitte zuerst FlightGear beenden.": "Please close FlightGear first.",
    "fgfs.exe nicht gefunden - bitte unten bei 'fgfs.exe' eintragen.":
        "fgfs.exe not found - please enter it below at 'fgfs.exe'.",
    "Fertig.": "Done.",
    "Nicht vollstaendig:": "Not complete:",
    "Einstellungen gespeichert.": "Settings saved.",
    "Flugzeug: {flugzeug}   aktives Profil: {profil}": "Aircraft: {flugzeug}   active profile: {profil}",
    "Einstellungen speichern und beenden?": "Save settings and quit?",
    "FlightGear-Launcher gestartet.": "FlightGear launcher started.",
    "Bruecke gestoppt.": "Bridge stopped.",
    # --- Einrichten ---
    "Seneca-Fehler korrigiert: rechter Propeller-Regler":
        "Seneca bug fixed: right propeller governor",
    "Seneca-Fehler korrigiert: Kreisel-Geraeusche": "Seneca bug fixed: gyro sounds",
    "Protokolldateien sind aktuell.": "Protocol files are up to date.",
    "Elite-Cockpit, Aussensicht, 2D-Instrumentenbrett und Innenraum erzeugt.":
        "Elite cockpit, outside view, 2D instrument panel and interior created.",
    "Seneca auf Elite-Cockpit umgestellt": "Seneca switched to the Elite cockpit",
    "Seneca auf Original-Cockpit umgestellt": "Seneca switched to the original cockpit",
    "Seneca: Elite-Cockpit": "Seneca: Elite cockpit",
    "Seneca: Original-Cockpit": "Seneca: original cockpit",
    "WARNUNG: Modell-Pfad in SenecaII-set.xml nicht gefunden - Cockpit unveraendert":
        "WARNING: model path not found in SenecaII-set.xml - cockpit unchanged",
    "FlightGear-Datenordner nicht gefunden. Bitte FlightGear einmal starten (auch nur bis "
    "zum Launcher) und dann erneut 'Einrichten'.":
        "FlightGear data folder not found. Please start FlightGear once (the launcher is "
        "enough) and then press 'Set up' again.",
    "Seneca II nicht gefunden. Bitte im FlightGear-Launcher unter 'Flugzeuge' die 'Seneca "
    "II' installieren, einmal damit starten und dann erneut 'Einrichten'.":
        "Seneca II not found. Please install the 'Seneca II' in the FlightGear launcher "
        "under 'Aircraft', start it once and then press 'Set up' again.",
    # --- Schalter-Test: Geraete, Achsen, Schalter, Codes ---
    "Gas links": "Throttle left", "Gas rechts": "Throttle right",
    "Propeller links": "Prop left", "Propeller rechts": "Prop right",
    "Gemisch links": "Mixture left", "Gemisch rechts": "Mixture right",
    "Gemisch C172P": "Mixture C172P", "Seitenruder": "Rudder",
    "Bremse links": "Brake left", "Bremse rechts": "Brake right",
    "Rudertrimmung": "Rudder trim", "Querruder": "Ailerons", "Hoehenruder": "Elevator",
    "batterie": "battery", "parkbremse": "parking brake", "fahrwerk": "gear",
    "lima-l": "alternator L", "lima-r": "alternator R", "pumpe-l": "fuel pump L",
    "pumpe-r": "fuel pump R", "mag-0-l": "mag L engine L", "mag-0-r": "mag R engine L",
    "mag-1-l": "mag L engine R", "mag-1-r": "mag R engine R", "anlasser-0": "starter L",
    "anlasser-1": "starter R", "tankwahl": "fuel selector", "klappen": "flaps",
    "cowl-0": "cowl flaps L", "cowl-1": "cowl flaps R", "hoehentrimm": "elevator trim",
    "reserve": "spare (taxi)", "sprechtaste": "push-to-talk",
    "Batterie": "Battery", "Radio-Master": "Radio master", "Parkbremse": "Parking brake",
    "Fahrwerkshebel": "Gear lever", "Lichtmaschinen": "Alternators",
    "Benzinpumpen": "Fuel pumps", "Magnete": "Magnetos", "Anlasser": "Starter",
    "Licht": "Lights", "Tankwahl": "Fuel selector", "Klappen-Taster": "Flap switch",
    "Cowl-Flaps-Wippen": "Cowl flap rockers", "Hoehentrimm (Horn)": "Elevator trim (yoke)",
    "Cowl Flaps links": "Cowl flaps left", "Cowl Flaps rechts": "Cowl flaps right",
    "Reserve-Schalter: Rollscheinwerfer (Taxi)": "Spare switch: taxi light",
    "Sprechtaste (Horn): AP aus": "Push-to-talk (yoke): AP off", "CWS (Horn)": "CWS (yoke)",
    "Drehknopf COM/NAV/ADF/DME": "Knob COM/NAV/ADF/DME", "Taster / DME-Wahl": "Key / DME selector",
    "DME-Schalter": "DME switch", "HDG/MDI-Knopf": "HDG/MDI knob", "CRS-Knopf": "CRS knob",
    "Autopilot-Taste": "Autopilot key", "Trimm-Wippe AP": "AP trim rocker",
    "TEST-Taste": "TEST key", "QNH-Knopf": "QNH knob", "NAV2-Knopf": "NAV2 knob",
    "SET-Knopf: AP-Nickrad": "SET knob: AP pitch wheel",
    "Hoehenvorwahl ENG/ARM, V/S": "Altitude preselect ENG/ARM, V/S",
    "Transponder-Knopf": "Transponder knob", "Transponder-Modus/IDENT": "Transponder mode/IDENT",
    # --- GPS und Bordcomputer ---
    "WARTE AUF FLIGHTGEAR": "WAITING FOR FLIGHTGEAR",
    "NAV  - KEIN ZIEL -": "NAV  - NO TARGET -",
    "DIRECT + ENTER = ZIEL": "DIRECT + ENTER = TARGET",
    "NICHTS IN 60 NM": "NOTHING WITHIN 60 NM",
    "KOMMT NOCH": "NOT YET",
    "keine Daten von FlightGear": "no data from FlightGear",
    "NORDEN OBEN": "NORTH UP", "FLUGRICHTUNG OBEN": "TRACK UP",
    "Bordcomputer": "Status page", "BORD": "STATUS", "CHECKLISTE": "CHECKLIST",
    "TREIBSTOFF (gal)": "FUEL (gal)", "Motoren aus": "Engines off",
    "KEINE WARNUNG": "NO WARNINGS", "LISTE FERTIG  >": "LIST DONE  >",
    "Dieses Flugzeug hat\nkeine Checklisten": "This aircraft has\nno checklists",
    "FAHRWERK NICHT AUSGEFAHREN": "GEAR NOT DOWN", "PARKBREMSE GESETZT": "PARKING BRAKE SET",
    "PITOT-HEIZUNG AUS": "PITOT HEAT OFF", "BATTERIE SCHWACH": "BATTERY LOW",
}
# Warnungen des Bordcomputers je Seite
for _de, _en in (("LINKS", "LEFT"), ("RECHTS", "RIGHT")):
    EN.update({
        f"TANK {_de} LEER": f"TANK {_en} EMPTY", f"TANK {_de} FAST LEER": f"TANK {_en} LOW",
        f"MAGNET {_de}: NUR EINER": f"MAGNETO {_en}: ONLY ONE",
        f"LICHTMASCHINE {_de} AUS": f"ALTERNATOR {_en} OFF",
        f"TANKWAHL {_de} ZU": f"FUEL SELECTOR {_en} OFF",
        f"COWL FLAPS {_de} ZU": f"COWL FLAPS {_en} CLOSED",
        f"MAGNETE {_de} AUS": f"MAGNETOS {_en} OFF", f"GEMISCH {_de} ARM": f"MIXTURE {_en} LEAN",
    })

# Teile zusammengesetzter Meldungen (mit Namen, Zahlen); laengere werden zuerst ersetzt
PHRASEN = sorted({
    # Meldungen der Bruecke
    " verbunden.": " connected.",
    " nicht gefunden, suche weiter ...": " not found, still searching ...",
    " - verbinde neu ...": " - reconnecting ...",
    "Zustand nicht gespeichert:": "State not saved:",
    "Flugzeug ": "Aircraft ", ": Profil '": ": profile '",
    "Sende an ": "Sending to ", ", Frequenzen von Port ": ", frequencies from port ",
    "Avionik:": "Avionics:", "Strom an": "power on", "Strom aus": "power off",
    "Geraet 1 an": "unit 1 on", "Geraet 1 aus": "unit 1 off",
    "Geraet 2 an": "unit 2 on", "Geraet 2 aus": "unit 2 off",
    "Instrumente: Vollbild auf Monitor ": "Instruments: full screen on monitor ",
    "Instrumente: Monitor ": "Instruments: monitor ",
    " ist nicht 16:10, Fenster ": " is not 16:10, window ", " in der Mitte": " centred",
    "Cockpit nicht umgestellt:": "Cockpit not switched:",
    "Profil '": "Profile '", " angelegt (Kopie von '": " created (copy of '",
    "Automatisch kalibriert: ": "Calibrated automatically: ",
    "Nicht (genug) bewegt, unveraendert: ": "Not moved (enough), unchanged: ",
    # Einrichten
    "FlightGear-Daten: ": "FlightGear data: ",
    "Protokolldateien kopiert: ": "Protocol files copied: ",
    "FEHLER beim Kopieren der Protokolldateien: ": "ERROR copying the protocol files: ",
    "FEHLER beim Erzeugen der Seneca-Dateien: ": "ERROR creating the Seneca files: ",
    "geschrieben:": "written:", "Aussensicht: ": "Outside view: ",
    " Instrumente/Teile vorne entfernt.": " instruments/parts removed at the front.",
    "Fertig: ": "Done: ", " Geraete entfernt, ": " devices removed, ",
    " Cockpit-Teile und ": " cockpit parts and ", " Schalter versteckt.": " switches hidden.",
    " Beschriftungen als Bild geschrieben.": " labels written as images.",
    " Leder-Texturen geschrieben.": " leather textures written.",
    "Tuerverkleidungen: ": "Door panels: ", " Teile geschrieben.": " parts written.",
    "WARNUNG: ": "WARNING: ", "nicht gefunden": "not found",
    "verschoben nur:": "moved only:", "kein Platz fuer": "no room for",
    "nicht im Seneca-Panel": "not in the Seneca panel",
    # Schalter-Test (Klartext der Tasten und Knoepfe)
    "Frequenzknopf ": "Frequency knob ", "innen (fein)": "inner (fine)",
    "aussen (grob)": "outer (coarse)", "ADF-Reihe: ": "ADF row: ",
    "BFO-Taste": "BFO key", "IDENT-Taste": "IDENT key", "Taste losgelassen": "key released",
    "Tauschtaste ": "Swap key ", "OFF-Taste COM/NAV": "OFF key COM/NAV",
    "losgelassen, DME-Wahl ": "released, DME selector ", "ADF-Taste (ADF/ANT)": "ADF key (ADF/ANT)",
    "DME-Schalter ": "DME switch ", "FLT-Taste (FLT/ET)": "FLT key (FLT/ET)",
    "SET-Taste": "SET key", "FLT/SET losgelassen": "FLT/SET released",
    "MDI-Knopf (ADF-Rose) ": "MDI knob (ADF card) ",
    "HDG-Knopf (Heading Bug) ": "HDG knob (heading bug) ",
    "CRS-Knopf (Kurs NAV1) ": "CRS knob (NAV1 course) ", "Kippschalter auf ": "toggle switch at ",
    "QNH-Knopf": "QNH knob", "NAV2-Knopf (Kurs NAV2)": "NAV2 knob (NAV2 course)",
    "SET-Knopf (AP-Nickrad)": "SET knob (AP pitch wheel)",
    "AP-Taste losgelassen": "AP key released", "AP-Taste ": "AP key ",
    "AP-Trimmwippe unten": "AP trim rocker down", "AP-Trimmwippe oben": "AP trim rocker up",
    "AP-Trimmwippe Ruhe": "AP trim rocker neutral",
    "GPS-Taste losgelassen": "GPS key released", "GPS-Taste ": "GPS key ",
    "GPS-Knopf ": "GPS knob ", "Hoehenvorwahl ": "Altitude preselect ",
    "Kippschalter V/S": "toggle switch V/S", "Kippschalter ALT": "toggle switch ALT",
    "TEST-Taste gedrueckt": "TEST key pressed", "TEST-Taste losgelassen": "TEST key released",
    "FREEZE gedrueckt": "FREEZE pressed", "FREEZE losgelassen": "FREEZE released",
    "INSTR-Taste (Bordcomputer/Checkliste)": "INSTR key (status page/checklist)",
    "MAP-Taste (Navi Text/Karte)": "MAP key (GPS text/map)",
    "INSTR/MAP losgelassen": "INSTR/MAP released",
    "Transponder-Knopf Stelle ": "Transponder knob digit ", "(von links)": "(from left)",
    "Transponder-Schalter ": "Transponder switch ",
    "Licht an: ": "Lights on: ", "Licht: alle aus": "Lights: all off",
    "LANDING (Landescheinwerfer)": "LANDING (landing light)",
    "NAV (Positionslichter + Instrumente, nur mit Strom)":
        "NAV (position lights + panel lighting, needs power)",
    "STROBE (Blitzlicht)": "STROBE (strobe light)",
    "losgelassen": "released", "gedrueckt": "pressed", " rechts": " right", " links": " left",
    "aussen": "outer", "innen": "inner",
    # GPS (Seiten und Listen)
    "FLUGPLATZ": "AIRPORT", "PISTE ": "RWY ",
    # Bordcomputer
    "   REST ": "   ENDUR. ", "AUSSEN ": "OAT ", "BORDNETZ ": "BUS ",
}.items(), key=lambda p: -len(p[0]))
