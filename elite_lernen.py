"""Lern-Assistent: ordnet Bedienelemente eines Elite-Geraets ihren Codes zu.

Ablauf im Terminal: Namen des Bedienelements eintippen + Enter, das Element
bedienen, Enter. Gespeichert wird, welche (Code, Wert)-Paare dabei kamen.
Paare, die das Geraet auch in Ruhe schickt (Komplettabzug), werden ausgeblendet.

Ergebnis: lernliste_<seriennr>.json (wird bei jedem Eintrag aktualisiert).

Beispiel:
  python elite_lernen.py BR000000
"""

import argparse
import collections
import json
import threading
import time

from elite_rohdaten import Dekoder, d2xx, lade_codenamen, lies_verfuegbar, oeffne

# Status-/Versionsmeldungen aus dem Komplettabzug, nie ein Bedienelement
STATUS_CODES = {100, 101, 115, 116, 117}
# Codes, die rastende Schalter als Zustand im Komplettabzug (~1x/s) melden;
# Code 32 traegt dabei abwechselnd zwei Werte
ZUSTAND_CODES = {23, 31, 32, 49, 56}
ZUSTAND_FENSTER = 2.2  # Sekunden: deckt mindestens zwei Komplettabzuege ab


class Leser(threading.Thread):
    """Liest im Hintergrund, sammelt alle (Code, Wert)-Paare und merkt sich
    die Zustandsmeldungen mit Zeitstempel."""

    def __init__(self, handle):
        super().__init__(daemon=True)
        self.handle = handle
        self.sperre = threading.Lock()
        self.puffer = []
        self.verlauf = collections.deque(maxlen=2000)
        self.laeuft = True

    def run(self):
        dekoder = Dekoder()
        while self.laeuft:
            daten = lies_verfuegbar(self.handle)
            if not daten:
                time.sleep(0.005)
                continue
            jetzt = time.monotonic()
            with self.sperre:
                for code, wert in dekoder.fuettere(daten):
                    self.puffer.append((code, wert))
                    if code in ZUSTAND_CODES:
                        self.verlauf.append((jetzt, code, wert))

    def abholen(self):
        with self.sperre:
            paare, self.puffer = self.puffer, []
        return paare

    def zustand(self, von, bis):
        """Werte je Zustands-Code im Zeitfenster [von, bis]."""
        with self.sperre:
            ergebnis = collections.defaultdict(set)
            for t, code, wert in self.verlauf:
                if von <= t <= bis:
                    ergebnis[code].add(wert)
        return ergebnis


def main():
    parser = argparse.ArgumentParser(description="Bedienelemente anlernen")
    parser.add_argument("seriennr", help="z.B. BR000000 (AP-3000)")
    parser.add_argument("--typedef", default=r"C:\ELITE\Tools\Serial Down\Typedef.txt")
    args = parser.parse_args()

    namen = lade_codenamen(args.typedef)
    handle, echte_nr = oeffne(args.seriennr, 38400)
    leser = Leser(handle)
    leser.start()
    datei = f"lernliste_{echte_nr}.json"
    try:
        liste = json.load(open(datei, encoding="utf-8"))
    except (OSError, ValueError):
        liste = {}

    print("Ruhezustand wird 3 Sekunden gemessen - bitte nichts anfassen ...")
    leser.abholen()
    time.sleep(3)
    ruhe = set(leser.abholen())

    print(f"\nBereit. Ergebnisse gehen nach {datei}. Leere Eingabe beendet.\n")
    try:
        while True:
            name = input("Bedienelement (Name, Enter): ").strip()
            if not name:
                break
            if name in liste:
                nr = 2
                while f"{name} ({nr})" in liste:
                    nr += 1
                name = f"{name} ({nr})"
                print(f"  (Name schon vergeben - gespeichert als '{name}')")
            jetzt = time.monotonic()
            vorher = leser.zustand(jetzt - ZUSTAND_FENSTER, jetzt)
            leser.abholen()
            input(f"  -> jetzt '{name}' bedienen, danach Enter ")
            print("     (pruefe Zustand ...)")
            ende = time.monotonic()
            time.sleep(ZUSTAND_FENSTER)
            nachher = leser.zustand(ende, time.monotonic())

            # Zustandsaenderungen rastender Schalter
            zustand = {}
            for code in sorted(ZUSTAND_CODES):
                alt, neu = sorted(vorher.get(code, ())), sorted(nachher.get(code, ()))
                if alt and neu and alt != neu:
                    zustand[code] = [alt, neu]
                    print(f"     Zustand Code {code:3d} {namen.get(code, '?'):<14} {alt} -> {neu}")

            # Ereignisse von Tastern/Drehgebern; Werte, die nur den Zustand
            # wiederholen, zaehlen nicht
            def ist_zustand(paar):
                code, wert = paar
                return code in ZUSTAND_CODES and (
                    wert in vorher.get(code, ()) or wert in nachher.get(code, ()))

            paare = [p for p in leser.abholen()
                     if p not in ruhe and p[0] not in STATUS_CODES and not ist_zustand(p)]
            zaehler = collections.Counter(paare)
            for (code, wert), anzahl in sorted(zaehler.items()):
                print(f"     Code {code:3d} {namen.get(code, '?'):<14} = {wert:3d}   {anzahl}x")
            if not paare and not zustand:
                print("  !! nichts empfangen - nochmal versuchen?\n")
                continue
            liste[name] = {
                "ereignisse": [[code, wert, anzahl]
                               for (code, wert), anzahl in sorted(zaehler.items())],
                "zustand": {str(code): werte for code, werte in zustand.items()},
            }
            with open(datei, "w", encoding="utf-8") as f:
                json.dump(liste, f, ensure_ascii=False, indent=1)
            print()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        leser.laeuft = False
        leser.join(timeout=1)
        d2xx.FT_Close(handle)
    print(f"Gespeichert: {len(liste)} Bedienelemente in {datei}")


if __name__ == "__main__":
    main()
