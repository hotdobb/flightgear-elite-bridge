"""Schreibt Zahlen auf die Anzeigen eines Elite-Avionikpanels (AP-3000).

Ausgabeformat, aus EliteFSXUSB_x64.dll abgeleitet:
  C0 00 C1 02      Initialisieren (schickt der Elite-Treiber beim Start)
  C0 kk            Anzeige-Kanal kk (0..31) waehlen
  (hh|80) ll       Zahl = hh*100 + ll (hh 0..127, ll 0..99) an den gewaehlten Kanal

Beispiele:
  python elite_anzeige.py BR000000 init
  python elite_anzeige.py BR000000 zahl 3 1234       # Kanal 3, Zahl 1234
  python elite_anzeige.py BR000000 durchlauf 1234    # Kanaele 0..31 nacheinander
"""

import argparse
import ctypes
import time

from elite_rohdaten import d2xx, oeffne, pruefe


def schreibe(handle, daten):
    geschrieben = ctypes.c_ulong()
    pruefe(d2xx.FT_Write(handle, bytes(daten), ctypes.c_ulong(len(daten)),
                         ctypes.byref(geschrieben)), "FT_Write")


def init(handle):
    schreibe(handle, [0xC0, 0x00, 0xC1, 0x02])


def zahl(handle, kanal, wert):
    if not 0 <= kanal <= 31 or not 0 <= wert <= 12799:
        raise ValueError("Kanal 0..31, Zahl 0..12799")
    schreibe(handle, [0xC0, kanal, 0x80 | (wert // 100), wert % 100])


def main():
    parser = argparse.ArgumentParser(description="Zahlen auf Elite-Anzeigen schreiben")
    parser.add_argument("seriennr")
    unter = parser.add_subparsers(dest="modus", required=True)
    unter.add_parser("init")
    z = unter.add_parser("zahl")
    z.add_argument("kanal", type=int)
    z.add_argument("wert", type=int)
    d = unter.add_parser("durchlauf")
    d.add_argument("wert", type=int)
    d.add_argument("--pause", type=float, default=2.0)
    args = parser.parse_args()

    handle, _ = oeffne(args.seriennr, 38400)
    try:
        init(handle)
        print("Init gesendet: C0 00 C1 02")
        if args.modus == "zahl":
            zahl(handle, args.kanal, args.wert)
            print(f"Kanal {args.kanal}: {args.wert}")
            time.sleep(1)
        elif args.modus == "durchlauf":
            for kanal in range(32):
                zahl(handle, kanal, args.wert)
                print(f"  Kanal {kanal:2d}: {args.wert}", flush=True)
                time.sleep(args.pause)
        else:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Angehalten.")
    finally:
        d2xx.FT_Close(handle)


if __name__ == "__main__":
    main()
