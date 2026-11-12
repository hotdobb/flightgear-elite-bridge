"""Schickt Anzeigedaten an das Elite AP-3000 im Paketformat des Elite-Treibers.

Paket (aus ELITEHardware_x64.dll, Funktion 0x1c640 / 0x1df00):
  78 | n | 50 00 | P1 | Datensaetze (je 5 Byte: Typ + 4 Datenbytes) | P2
  n  = 4 + 5 * Anzahl Datensaetze
  P1 = Pruefsumme ueber n, 50, 00
  P2 = Pruefsumme ueber alles ab n bis zum letzten Datenbyte
  Pruefsumme: c = 0; je Byte: c = (c + b) XOR A5, dann 1 Bit nach links rotieren

Datensaetze COM-Frequenz (Typ L/M/N/O): Typ, 00, MHz-high, MHz-low, kHz/10
  (vermutlich L = COM1 aktiv, M = COM1 Standby, N = COM2 aktiv, O = COM2 Standby)

Bestaetigt: Typ '!' mit 00 01 01 01 schaltet die drei Marker-Lampen am Apollo ein.

Beispiele:
  python elite_avionik.py BR000000 test
  python elite_avionik.py BR000000 typen          # jeden Typ einzeln mit Testwerten
"""

import argparse
import ctypes
import threading
import time

from elite_rohdaten import d2xx, oeffne, pruefe


def pruefsumme(daten):
    c = 0
    for b in daten:
        c = ((c + b) & 0xFF) ^ 0xA5
        c = ((c << 1) | (c >> 7)) & 0xFF
    return c


def paket(datensaetze):
    nutz = b"".join(datensaetze)
    kopf = bytes([4 + len(nutz), 0x50, 0x00])
    rumpf = kopf + bytes([pruefsumme(kopf)]) + nutz
    return bytes([0x78]) + rumpf + bytes([pruefsumme(rumpf)])


# AP-3000 verliert Daten, wenn zu viel auf einmal kommt: ein Datensatz pro Paket,
# Pausen dazwischen (wie der Elite-Treiber, der nur Aenderungen schickt)
MAX_SAETZE = 1
PAKET_PAUSE = 0.05
AUFFRISCHEN = 3.0


def pakete(datensaetze):
    """Teilt Datensaetze auf mehrere kleine Pakete auf."""
    return [paket(datensaetze[i:i + MAX_SAETZE])
            for i in range(0, len(datensaetze), MAX_SAETZE)]


def satz(typ, b0, b1, b2, b3):
    return bytes([ord(typ) if isinstance(typ, str) else typ, b0, b1, b2, b3])


def frequenz(typ, mhz):
    # abschneiden wie Elite-Treiber und Seneca (121.875 -> 121.87), nicht runden;
    # kleiner Zuschlag gegen Gleitkomma-Fehler (121.88 darf nicht 121.87 werden)
    ganz = int(mhz)
    rest = int((mhz - ganz) * 100 + 1e-6)
    return satz(typ, 0, ganz >> 8, ganz & 0xFF, rest)


# Alle Typen aus der Treiber-Tabelle ausser '!' (Marker, schon bekannt) und ' ' (Grundzustand)
TESTTYPEN = [0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x4B,
             0x4C, 0x4D, 0x4E, 0x4F, 0x52, 0x53, 0x54, 0x59, 0x5A, 0x5B, 0x5C, 0x63,
             0x02, 0x64, 0x14]
# Schon gefundene Anzeigen; bleiben im Schritt-Modus dauerhaft an
BEKANNT = [
    satz("!", 0, 1, 1, 1),        # Marker-Lampen A / O / M am Apollo
    satz("@", 0, 0, 118, 25),     # Reihe 1, Block 4 (ganz rechts) zeigt "000"
    satz("A", 0, 0, 118, 25),     # Reihe 1, Block 3 zeigt "118.25"
    satz("C", 0, 0, 118, 25),     # Reihe 2, Block 4 zeigt "000"
    satz("F", 0, 0, 118, 25),     # Reihe 3, Block 1 zeigt "000"
]
LEER = {"", "dunkel", "dunken", "dukel", "nichts"}
# zwei Muster je Typ: Frequenzform (118.25) und 16-Bit-Zahlen (1234 / 5678)
TESTMUSTER = [("118.25", (0, 0, 118, 25)), ("1234/5678", (0x04, 0xD2, 0x16, 0x2E))]


def schreibe(handle, daten):
    geschrieben = ctypes.c_ulong()
    pruefe(d2xx.FT_Write(handle, daten, ctypes.c_ulong(len(daten)), ctypes.byref(geschrieben)),
           "FT_Write")


def schritt_modus(seriennr, ab=None, logdatei="avionik_beobachtungen.log"):
    """Jeder Typ/jedes Muster bleibt stehen, bis Enter; Beobachtung wird mitgeschrieben.

    Der getestete Datensatz blinkt (Testwert / Nullen im Halbsekundentakt), damit
    man die betroffene Anzeige sofort sieht. Bekannte Lampen (Marker) bleiben an.
    """
    handle, _ = oeffne(seriennr, 38400)
    grund = [satz(" ", 3, 3, 0, 3)] + BEKANNT
    # aktuell = [Dauer-Pakete, Test-Paket an, Test-Paket aus]
    aktuell = [pakete(grund), b"", b""]
    laeuft = [True]

    def sender():
        an = True
        letzte_auffrischung = 0.0
        while laeuft[0]:
            if time.monotonic() - letzte_auffrischung >= AUFFRISCHEN:
                for p in aktuell[0]:
                    schreibe(handle, p)
                    time.sleep(PAKET_PAUSE)
                letzte_auffrischung = time.monotonic()
            test = aktuell[1] if an else aktuell[2]
            if test:
                schreibe(handle, test)
            an = not an
            time.sleep(0.5)

    faden = threading.Thread(target=sender, daemon=True)
    faden.start()
    typen = TESTTYPEN
    if ab is not None:
        typen = TESTTYPEN[TESTTYPEN.index(ord(ab) if len(ab) == 1 else int(ab, 16)):]
    try:
        schritte = [(typ, name, werte) for typ in typen for name, werte in TESTMUSTER]
        i = 0
        with open(logdatei, "a", encoding="utf-8") as log:
            while i < len(schritte):
                typ, name, werte = schritte[i]
                # den getesteten Typ nicht zusaetzlich aus der Dauer-Liste schicken
                ohne = [s for s in grund if s[0] != typ]
                aktuell[:] = [pakete(ohne), paket([satz(typ, *werte)]),
                              paket([satz(typ, 0, 0, 0, 0)])]
                zeichen = chr(typ) if 32 <= typ < 127 else f"0x{typ:02x}"
                notiz = input(f"Typ '{zeichen}' Muster {name}: Beobachtung "
                              f"(Enter = weiter, z = zurueck): ")
                if notiz.strip().lower() == "z":
                    i = max(0, i - 1)
                    continue
                log.write(f"{zeichen}\t{name}\t{notiz}\n")
                log.flush()
                if notiz.strip().lower() not in LEER:
                    # Fund: bleibt ab jetzt dauerhaft an (ersetzt aelteren Eintrag gleichen Typs)
                    grund = [s for s in grund if s[0] != typ] + [satz(typ, *werte)]
                    print(f"     -> Typ '{zeichen}' bleibt ab jetzt an.")
                i += 1
        print(f"Fertig. Beobachtungen in {logdatei}")
    except (KeyboardInterrupt, EOFError):
        print("Angehalten.")
    finally:
        laeuft[0] = False
        faden.join(timeout=1)
        d2xx.FT_Close(handle)


def suche_modus(seriennr, logdatei="avionik_beobachtungen.log"):
    """Sucht den Typ fuer ADF-Block 2: ADF an (F=15, G=0), dann je ein Typ mit FF,
    der vor dem naechsten wieder auf 0 gesetzt wird. Tempo bestimmt der Nutzer."""
    kandidaten = [0x48, 0x45, 0x49, 0x4A, 0x4B, 0x5B, 0x5C, 0x63, 0x02, 0x64, 0x14,
                  0x59, 0x5A, 0x52, 0x53, 0x54, 0x40, 0x41, 0x42, 0x43, 0x44,
                  0x4C, 0x4D, 0x4E, 0x4F, 0x20, 0x21]
    handle, _ = oeffne(seriennr, 38400)
    try:
        for s in (satz("F", 0, 15, 0, 1), satz("G", 0, 0, 0, 0)):
            schreibe(handle, paket([s]))
            time.sleep(PAKET_PAUSE)
        input("ADF an (Block 1 sollte 000 zeigen). Enter = Start: ")
        with open(logdatei, "a", encoding="utf-8") as log:
            for typ in kandidaten:
                zeichen = chr(typ) if 32 < typ < 127 else f"0x{typ:02x}"
                schreibe(handle, paket([satz(typ, 255, 255, 255, 255)]))
                notiz = input(f"Typ '{zeichen}' = FF: Was leuchtet neu? (Enter = nichts): ")
                log.write(f"suche-block2\t{zeichen}\tFF\t{notiz}\n")
                log.flush()
                schreibe(handle, paket([satz(typ, 0, 0, 0, 0)]))
                time.sleep(0.3)
        print(f"Fertig. Beobachtungen in {logdatei}")
    except (KeyboardInterrupt, EOFError):
        print("Angehalten.")
    finally:
        d2xx.FT_Close(handle)


def lampen_modus(seriennr, logdatei="avionik_beobachtungen.log"):
    """Autopilot-Lampen: Datensatz T = [Lampenwort hoch, Lampenwort tief, FF, FF].
    Schaltet nacheinander je ein Bit ein; der Nutzer tippt, welche Lampe leuchtet."""
    handle, _ = oeffne(seriennr, 38400)
    try:
        with open(logdatei, "a", encoding="utf-8") as log:
            for bit in range(16):
                wort = 1 << bit
                schreibe(handle, paket([satz("T", wort >> 8, wort & 0xFF, 255, 255)]))
                notiz = input(f"Bit {bit} (Wert {wort}): Welche AP-Lampe leuchtet? "
                              f"(Enter = keine): ")
                log.write(f"ap-lampe\tbit {bit}\t{wort}\t{notiz}\n")
                log.flush()
            schreibe(handle, paket([satz("T", 0, 0, 255, 255)]))
        print(f"Fertig. Beobachtungen in {logdatei}")
    except (KeyboardInterrupt, EOFError):
        print("Angehalten.")
    finally:
        d2xx.FT_Close(handle)


def dme_modus(seriennr, logdatei="avionik_beobachtungen.log"):
    """DME (Reihe 4): I = Zustand/Beschriftungen (wie F beim ADF), J = Zahlen.
    Jeder Schritt bleibt stehen, bis Enter; z = zurueck, q = Ende."""
    test_j = (0x04, 0xD2, 0x16, 0x2E)  # 1234 / 5678
    schritte = [((0, 0, 0, 1), (0, 0, 0, 0)), ((0, 0, 0, 1), test_j)]
    for stelle in (1, 0, 2):
        for bit in range(7):
            i = [0, 0, 0, 1]
            i[stelle] |= 1 << bit
            schritte.append((tuple(i), test_j))
    schritte.append(((0, 0, 0, 0), test_j))
    handle, _ = oeffne(seriennr, 38400)
    aktuell = [[]]
    laeuft = [True]

    def sender():
        while laeuft[0]:
            if aktuell[0]:
                for p in pakete([satz(" ", 3, 3, 0, 3)]) + aktuell[0]:
                    schreibe(handle, p)
                    time.sleep(PAKET_PAUSE)
            time.sleep(1.0)

    faden = threading.Thread(target=sender, daemon=True)
    faden.start()
    try:
        with open(logdatei, "a", encoding="utf-8") as log:
            n = 0
            while n < len(schritte):
                i, j = schritte[n]
                for s in (satz("I", *i), satz("J", *j)):
                    schreibe(handle, paket([s]))
                    time.sleep(PAKET_PAUSE)
                aktuell[0] = pakete([satz("I", *i), satz("J", *j)])
                notiz = input(f"[{n + 1}/{len(schritte)}] I = {i}  J = {j}: Was zeigt das "
                              f"DME? (Enter = dunkel, z = zurueck, q = Ende): ").strip()
                if notiz.lower() == "q":
                    break
                if notiz.lower() == "z":
                    n = max(0, n - 1)
                    continue
                log.write(f"dme\tI={i}\tJ={j}\t{notiz or 'dunkel'}\n")
                log.flush()
                n += 1
        print(f"Fertig. Beobachtungen in {logdatei}")
    except (KeyboardInterrupt, EOFError):
        print("Angehalten.")
    finally:
        laeuft[0] = False
        faden.join(timeout=2)
        d2xx.FT_Close(handle)


def pro_modus(seriennr, logdatei="avionik_beobachtungen.log"):
    """Pro Panel II (Geraetetyp 3): der Elite-Treiber schickt ihm nur den Datensatz ' '
    (alle 5 s oder bei Aenderung). Testet Werte fuer die Fahrwerkslampen."""
    schritte = [(3, 3, 0, 3), (0, 0, 0, 0)]
    for stelle in range(4):
        for wert in (1, 2, 3):
            s = [0, 0, 0, 0]
            s[stelle] = wert
            schritte.append(tuple(s))
    schritte += [(255, 255, 255, 255), (0, 0, 0, 0)]
    handle, _ = oeffne(seriennr, 38400)
    aktuell = [b""]
    laeuft = [True]

    def sender():
        while laeuft[0]:
            if aktuell[0]:
                schreibe(handle, aktuell[0])
            time.sleep(1.0)

    faden = threading.Thread(target=sender, daemon=True)
    faden.start()
    try:
        with open(logdatei, "a", encoding="utf-8") as log:
            n = 0
            while n < len(schritte):
                werte = schritte[n]
                aktuell[0] = paket([satz(" ", *werte)])
                schreibe(handle, aktuell[0])
                notiz = input(f"[{n + 1}/{len(schritte)}] ' ' = {werte}: Welche Lampen "
                              f"leuchten? (Enter = keine, z = zurueck, q = Ende): ").strip()
                if notiz.lower() == "q":
                    break
                if notiz.lower() == "z":
                    n = max(0, n - 1)
                    continue
                log.write(f"pro\t' '={werte}\t{notiz or 'keine'}\n")
                log.flush()
                n += 1
        print(f"Fertig. Beobachtungen in {logdatei}")
    except (KeyboardInterrupt, EOFError):
        print("Angehalten.")
    finally:
        laeuft[0] = False
        faden.join(timeout=2)
        d2xx.FT_Close(handle)


def main():
    parser = argparse.ArgumentParser(description="Anzeigedaten an Elite AP-3000")
    parser.add_argument("seriennr")
    parser.add_argument("modus", choices=["test", "typen", "schritt", "einzel", "suche",
                                          "lampen", "dme", "pro"])
    parser.add_argument("satz", nargs="*", help="einzel: Typ und 4 Datenbytes, z.B. ! 0 1 1 1")
    parser.add_argument("--dauer", type=float, default=15, help="Sekunden wiederholt senden")
    parser.add_argument("--pause", type=float, default=6, help="Sekunden je Typ (typen)")
    parser.add_argument("--ab", help="schritt: bei diesem Typ anfangen, z.B. A oder 0x14")
    args = parser.parse_args()

    if args.modus == "einzel":
        typ = args.satz[0]
        typ = int(typ, 16) if typ.startswith("0x") else (" " if typ == "leer" else typ)
        daten = paket([satz(typ, *(int(x) for x in args.satz[1:5]))])
        print("Paket:", daten.hex(" "))
        handle, _ = oeffne(args.seriennr, 38400)
        try:
            ende = time.monotonic() + args.dauer
            while time.monotonic() < ende:
                schreibe(handle, daten)
                time.sleep(0.3)
        finally:
            d2xx.FT_Close(handle)
        print("Fertig.")
        return

    if args.modus == "suche":
        suche_modus(args.seriennr)
        return

    if args.modus == "pro":
        pro_modus(args.seriennr)
        return

    if args.modus == "dme":
        dme_modus(args.seriennr)
        return

    if args.modus == "lampen":
        lampen_modus(args.seriennr)
        return

    if args.modus == "schritt":
        schritt_modus(args.seriennr, args.ab)
        return

    if args.modus == "typen":
        handle, _ = oeffne(args.seriennr, 38400)
        try:
            # Grundzustand: Marker aus, Status "in Ordnung"
            grund = [satz("!", 0, 0, 0, 0), satz(" ", 3, 3, 0, 3)]
            for typ in TESTTYPEN:
                for name, werte in TESTMUSTER:
                    daten = paket(grund + [satz(typ, *werte)])
                    zeichen = chr(typ) if 32 <= typ < 127 else f"0x{typ:02x}"
                    print(f"  Typ '{zeichen}'  Muster {name:<10} {daten.hex(' ')}", flush=True)
                    ende = time.monotonic() + args.pause / len(TESTMUSTER)
                    while time.monotonic() < ende:
                        schreibe(handle, daten)
                        time.sleep(0.3)
            print("Fertig.")
        except KeyboardInterrupt:
            print("Angehalten.")
        finally:
            d2xx.FT_Close(handle)
        return

    saetze = [
        satz("!", 0, 1, 1, 1),        # Status-Flags (im Treiber aus Simulator-Schaltern)
        satz(" ", 3, 3, 0, 3),        # Spannungs-/Strom-Zustaende (3 = "in Ordnung")
        frequenz("L", 118.25),
        frequenz("M", 121.50),
        frequenz("N", 125.75),
        frequenz("O", 132.00),
    ]
    daten = paket(saetze)
    print("Paket:", daten.hex(" "))

    handle, _ = oeffne(args.seriennr, 38400)
    try:
        ende = time.monotonic() + args.dauer
        while time.monotonic() < ende:
            schreibe(handle, daten)
            time.sleep(0.5)
        print("Fertig.")
    except KeyboardInterrupt:
        print("Angehalten.")
    finally:
        d2xx.FT_Close(handle)


if __name__ == "__main__":
    main()
