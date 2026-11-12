"""Rohdaten von Fly-Elite-USB-Geraeten (FTDI VID 0403, PID FA50) lesen.

Spricht den FTDI-D2XX-Treiber direkt per ctypes an, ohne Elite-DLL:
Windows: ftd2xx.dll (vom Elite-Treiber installiert), Linux: libftd2xx.so.

Protokoll (38400 Baud, 8N1): Paare aus Code-Byte (Bit 7 = 0, Nummer wie in
Typedef.txt) und Wert-Byte (Bit 7 = 1, Wert = Byte & 0x7F, also 0..127).
Etwa jede Sekunde schickt das Geraet nach "75 c3" alle aktuellen Werte.

Beispiele:
  python elite_rohdaten.py --list
  python elite_rohdaten.py BR200000            # Pro Panel II, nur Aenderungen
  python elite_rohdaten.py BR200000 --hex      # rohe Bytes
"""

import argparse
import ctypes
import sys
import time
from datetime import datetime

FT_OK = 0
FT_OPEN_BY_SERIAL_NUMBER = 1
FT_PURGE_RX_TX = 3

CHIP_TYPEN = {0: "BM", 1: "AM", 2: "100AX", 4: "2232C", 5: "232R",
              6: "2232H", 7: "4232H", 8: "232H", 9: "X-Serie"}

FT_STATUS_TEXT = {1: "INVALID_HANDLE", 2: "DEVICE_NOT_FOUND", 3: "DEVICE_NOT_OPENED",
                  4: "IO_ERROR", 5: "INSUFFICIENT_RESOURCES", 6: "INVALID_PARAMETER"}


def lade_d2xx():
    if sys.platform.startswith("win"):
        return ctypes.WinDLL("ftd2xx.dll")
    for name in ("libftd2xx.so", "libftd2xx.so.1"):
        try:
            return ctypes.CDLL(name)
        except OSError:
            pass
    sys.exit("libftd2xx.so nicht gefunden (FTDI D2XX fuer Linux installieren).")


d2xx = lade_d2xx()


def pruefe(status, aufruf):
    if status != FT_OK:
        text = FT_STATUS_TEXT.get(status, str(status))
        raise RuntimeError(f"{aufruf} fehlgeschlagen: FT_STATUS {text}")


def geraeteliste():
    anzahl = ctypes.c_ulong()
    pruefe(d2xx.FT_CreateDeviceInfoList(ctypes.byref(anzahl)), "FT_CreateDeviceInfoList")
    geraete = []
    for i in range(anzahl.value):
        flags, typ, dev_id, loc = (ctypes.c_ulong() for _ in range(4))
        seriennr = ctypes.create_string_buffer(16)
        beschr = ctypes.create_string_buffer(64)
        handle = ctypes.c_void_p()
        pruefe(d2xx.FT_GetDeviceInfoDetail(
            ctypes.c_ulong(i), ctypes.byref(flags), ctypes.byref(typ), ctypes.byref(dev_id),
            ctypes.byref(loc), seriennr, beschr, ctypes.byref(handle)), "FT_GetDeviceInfoDetail")
        geraete.append({
            "index": i,
            "seriennr": seriennr.value.decode(errors="replace"),
            "beschreibung": beschr.value.decode(errors="replace"),
            "chip": CHIP_TYPEN.get(typ.value, f"Typ {typ.value}"),
            "vid_pid": f"{dev_id.value >> 16:04X}:{dev_id.value & 0xFFFF:04X}",
            "offen": bool(flags.value & 1),
        })
    return geraete


def oeffne(seriennr, baud):
    # D2XX haengt bei manchen Chips ein "A" an; auch Praefix-Treffer akzeptieren
    treffer = [g for g in geraeteliste() if g["seriennr"].startswith(seriennr)]
    if not treffer:
        raise RuntimeError(f"Kein Geraet mit Seriennummer {seriennr} gefunden (--list zeigt alle).")
    echte_nr = treffer[0]["seriennr"]
    handle = ctypes.c_void_p()
    pruefe(d2xx.FT_OpenEx(echte_nr.encode(), FT_OPEN_BY_SERIAL_NUMBER, ctypes.byref(handle)),
           f"FT_OpenEx({echte_nr})")
    pruefe(d2xx.FT_SetBaudRate(handle, ctypes.c_ulong(baud)), "FT_SetBaudRate")
    pruefe(d2xx.FT_SetDataCharacteristics(handle, ctypes.c_ubyte(8), ctypes.c_ubyte(0),
                                          ctypes.c_ubyte(0)), "FT_SetDataCharacteristics")
    pruefe(d2xx.FT_SetFlowControl(handle, ctypes.c_ushort(0), ctypes.c_ubyte(0),
                                  ctypes.c_ubyte(0)), "FT_SetFlowControl")
    pruefe(d2xx.FT_SetLatencyTimer(handle, ctypes.c_ubyte(2)), "FT_SetLatencyTimer")
    pruefe(d2xx.FT_SetTimeouts(handle, ctypes.c_ulong(50), ctypes.c_ulong(50)), "FT_SetTimeouts")
    pruefe(d2xx.FT_Purge(handle, ctypes.c_ulong(FT_PURGE_RX_TX)), "FT_Purge")
    return handle, echte_nr


def lies_verfuegbar(handle):
    in_queue = ctypes.c_ulong()
    pruefe(d2xx.FT_GetQueueStatus(handle, ctypes.byref(in_queue)), "FT_GetQueueStatus")
    if in_queue.value == 0:
        return b""
    puffer = ctypes.create_string_buffer(in_queue.value)
    gelesen = ctypes.c_ulong()
    pruefe(d2xx.FT_Read(handle, puffer, in_queue, ctypes.byref(gelesen)), "FT_Read")
    return puffer.raw[:gelesen.value]


def lade_codenamen(pfad):
    namen = {}
    try:
        for zeile in open(pfad, encoding="latin-1"):
            if zeile.startswith("Code") and "=" in zeile:
                nr, name = zeile[4:].split("=", 1)
                namen[int(nr)] = name.strip()
    except OSError:
        pass
    return namen


class Dekoder:
    """Setzt Code/Wert-Paare zusammen; synchronisiert ueber Bit 7."""

    def __init__(self):
        self.code = None

    def fuettere(self, daten):
        for byte in daten:
            if byte & 0x80 == 0:
                self.code = byte
            elif self.code is not None:
                yield self.code, byte & 0x7F
                self.code = None


def mitschneiden(seriennr, baud, dauer, logdatei, roh, typedef, alle=False, ignoriere=()):
    namen = lade_codenamen(typedef)
    handle, echte_nr = oeffne(seriennr, baud)
    print(f"Geoeffnet: {echte_nr} mit {baud} Baud. Hebel bewegen, Strg+C beendet.")
    start = time.monotonic()
    gesamt = 0
    dekoder = Dekoder()
    zustand = {}
    with open(logdatei, "a", encoding="utf-8") as log:
        log.write(f"# {datetime.now().isoformat()} {echte_nr} {baud} Baud\n")
        try:
            while dauer is None or time.monotonic() - start < dauer:
                daten = lies_verfuegbar(handle)
                if not daten:
                    time.sleep(0.005)
                    continue
                gesamt += len(daten)
                zeit = time.monotonic() - start
                if roh:
                    zeile = f"{zeit:8.3f}s  {len(daten):3d}B  {daten.hex(' ')}"
                    print(zeile, flush=True)
                    log.write(zeile + "\n")
                    continue
                for code, wert in dekoder.fuettere(daten):
                    if code in ignoriere:
                        continue
                    # Drehgeber melden pro Raste denselben Wert -> mit --alle jede Meldung zeigen
                    if zustand.get(code) == wert and not alle:
                        continue
                    alt = zustand.get(code)
                    zustand[code] = wert
                    zeile = (f"{zeit:8.3f}s  Code {code:3d} {namen.get(code, '?'):<14} "
                             f"= {wert:3d}" + ("" if alt is None else f"  (vorher {alt})"))
                    print(zeile, flush=True)
                    log.write(zeile + "\n")
        except KeyboardInterrupt:
            pass
        finally:
            d2xx.FT_Close(handle)
    print(f"Fertig: {gesamt} Bytes empfangen, Log in {logdatei}")


def main():
    parser = argparse.ArgumentParser(description="Rohdaten von Elite-USB-Geraeten lesen")
    parser.add_argument("seriennr", nargs="?", help="z.B. BR200000 (Pro Panel II)")
    parser.add_argument("--list", action="store_true", help="alle FTDI-Geraete anzeigen")
    parser.add_argument("--baud", type=int, default=38400)
    parser.add_argument("--dauer", type=float, help="Sekunden mitschneiden (sonst bis Strg+C)")
    parser.add_argument("--log", default="rohdaten.log")
    parser.add_argument("--hex", action="store_true", help="rohe Bytes statt Code/Wert zeigen")
    parser.add_argument("--typedef", default=r"C:\ELITE\Tools\Serial Down\Typedef.txt")
    parser.add_argument("--alle", action="store_true",
                        help="jede Meldung zeigen, auch wenn sich der Wert nicht aendert")
    parser.add_argument("--ignoriere", type=int, nargs="*", default=[],
                        help="Codes, die nicht angezeigt werden (z.B. Komplettabzug)")
    args = parser.parse_args()

    if args.list or not args.seriennr:
        for g in geraeteliste():
            status = "belegt" if g["offen"] else "frei"
            print(f"[{g['index']}] {g['seriennr']:<10} {g['vid_pid']}  Chip {g['chip']:<8} "
                  f"{status:<7} {g['beschreibung']}")
        return
    mitschneiden(args.seriennr, args.baud, args.dauer, args.log, args.hex, args.typedef,
                 args.alle, set(args.ignoriere))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as fehler:
        sys.exit(str(fehler))
