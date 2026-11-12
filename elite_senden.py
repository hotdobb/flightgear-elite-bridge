"""Schickt Code/Wert-Paare an ein Elite-Geraet, um die Anzeigen zu finden.

Format wie in Geraeterichtung: Code-Byte (Bit 7 = 0), Wert-Byte (Bit 7 = 1).
Gesperrt sind Codes, die das Geraet verstellen koennten (intern, 2-Wege,
Seriennummer, Hersteller-/Produkt-ID usw.).

Beispiele:
  python elite_senden.py BR000000 einzel 30 8          # Code 30, Wert 8
  python elite_senden.py BR000000 durchlauf 0 98 8     # Codes 0..98 je 1x mit Wert 8
"""

import argparse
import ctypes
import sys
import time

from elite_rohdaten import Dekoder, d2xx, lies_verfuegbar, oeffne, pruefe

# Codes, die nie gesendet werden: 50/99 "Intern", ab 100 Zwei-Wege-Steuerung,
# Versions-IDs, Hersteller-/Produkt-ID, Seriennummer usw.
GESPERRT = {50, 99} | set(range(100, 128))


def sende(handle, code, wert):
    if code in GESPERRT or not 0 <= code <= 127 or not 0 <= wert <= 127:
        raise ValueError(f"Code {code} / Wert {wert} ist gesperrt oder ausserhalb 0..127")
    daten = bytes([code, 0x80 | wert])
    geschrieben = ctypes.c_ulong()
    pruefe(d2xx.FT_Write(handle, daten, ctypes.c_ulong(len(daten)), ctypes.byref(geschrieben)),
           "FT_Write")


def antworten(handle, dekoder, dauer):
    """Liest dauer Sekunden mit und gibt neue Meldungen zurueck (ohne Komplettabzug-Rauschen)."""
    ende = time.monotonic() + dauer
    gesehen = []
    while time.monotonic() < ende:
        for code, wert in dekoder.fuettere(lies_verfuegbar(handle)):
            if code not in (31, 32, 49, 23, 56, 100, 101, 115, 116, 117):
                gesehen.append((code, wert))
        time.sleep(0.01)
    return gesehen


def main():
    parser = argparse.ArgumentParser(description="Code/Wert an Elite-Geraet senden")
    parser.add_argument("seriennr")
    unter = parser.add_subparsers(dest="modus", required=True)
    e = unter.add_parser("einzel")
    e.add_argument("code", type=int)
    e.add_argument("wert", type=int)
    d = unter.add_parser("durchlauf")
    d.add_argument("von", type=int)
    d.add_argument("bis", type=int)
    d.add_argument("wert", type=int)
    d.add_argument("--pause", type=float, default=1.5, help="Sekunden je Code")
    args = parser.parse_args()

    handle, nr = oeffne(args.seriennr, 38400)
    dekoder = Dekoder()
    try:
        if args.modus == "einzel":
            sende(handle, args.code, args.wert)
            print(f"Gesendet: Code {args.code}, Wert {args.wert}")
            for code, wert in antworten(handle, dekoder, 1.5):
                print(f"  Antwort: Code {code} = {wert}")
        else:
            print(f"Durchlauf Codes {args.von}..{args.bis} mit Wert {args.wert}, "
                  f"{args.pause}s je Code. Strg+C haelt an.")
            for code in range(args.von, args.bis + 1):
                if code in GESPERRT:
                    continue
                sende(handle, code, args.wert)
                print(f"  Code {code:3d} gesendet", flush=True)
                for c, w in antworten(handle, dekoder, args.pause):
                    print(f"      Antwort: Code {c} = {w}", flush=True)
    except KeyboardInterrupt:
        print("Angehalten.")
    except ValueError as fehler:
        sys.exit(str(fehler))
    finally:
        d2xx.FT_Close(handle)


if __name__ == "__main__":
    main()
