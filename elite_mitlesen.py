"""Liest mit, was ein Windows-Programm ueber ftd2xx.dll an Elite-Hardware sendet.

Startet das Programm (Standard: Elite NavCom Test) unter Frida und protokolliert
FT_Open/FT_OpenEx, FT_SetBaudRate, FT_Write und FT_Read. Am Geraet und am
Programm wird nichts veraendert; es wird nur zugeschaut.

Beispiele:
  python elite_mitlesen.py
  python elite_mitlesen.py --msfs --log mitschnitt_msfs.log   # Elite-Treiber fuer MSFS 2020
"""

import argparse
import os
import time

import frida

HOOK_JS = r"""
function hex(p, n) {
  return Array.from(new Uint8Array(p.readByteArray(n)))
    .map(b => b.toString(16).padStart(2, '0')).join(' ');
}
function haken() {
  const m = Process.findModuleByName('ftd2xx.dll') || Process.findModuleByName('ftd2xx64.dll');
  if (!m) return false;
  const h = (name, cb) => { const a = m.findExportByName(name); if (a) Interceptor.attach(a, cb); };
  h('FT_Write', { onEnter(a) { send({f: 'W', h: a[0].toString(), d: hex(a[1], a[2].toInt32())}); } });
  h('FT_Read', {
    onEnter(a) { this.h = a[0]; this.buf = a[1]; this.got = a[3]; },
    onLeave(r) { const n = this.got.readU32(); if (n > 0) send({f: 'R', h: this.h.toString(), d: hex(this.buf, n)}); }
  });
  h('FT_OpenEx', {
    onEnter(a) { this.arg = a[0]; this.flags = a[1].toInt32(); this.out = a[2]; },
    onLeave(r) {
      let was = '';
      try { was = (this.flags === 1 || this.flags === 2) ? this.arg.readCString() : String(this.arg.toInt32()); } catch (e) {}
      send({f: 'O', was: was, h: this.out.readPointer().toString(), st: r.toInt32()});
    }
  });
  h('FT_Open', {
    onEnter(a) { this.idx = a[0].toInt32(); this.out = a[1]; },
    onLeave(r) { send({f: 'O', was: 'Index ' + this.idx, h: this.out.readPointer().toString(), st: r.toInt32()}); }
  });
  h('FT_W32_WriteFile', { onEnter(a) { send({f: 'W', h: a[0].toString(), d: hex(a[1], a[2].toInt32())}); } });
  h('FT_W32_ReadFile', {
    onEnter(a) { this.h = a[0]; this.buf = a[1]; this.got = a[3]; },
    onLeave(r) { const n = this.got.readU32(); if (n > 0) send({f: 'R', h: this.h.toString(), d: hex(this.buf, n)}); }
  });
  ['FT_SetBitMode', 'FT_SetDtr', 'FT_ClrDtr', 'FT_SetRts', 'FT_ClrRts', 'FT_SetBreakOn',
   'FT_SetBreakOff', 'FT_WriteEE', 'FT_EE_Program', 'FT_EE_UAWrite', 'FT_SetChars', 'FT_Purge']
    .forEach(n => h(n, { onEnter(a) { send({f: 'X', n: n, h: a[0].toString(), a1: a[1].toInt32()}); } }));
  h('FT_SetBaudRate', { onEnter(a) { send({f: 'B', h: a[0].toString(), baud: a[1].toInt32()}); } });
  h('FT_Close', { onEnter(a) { send({f: 'C', h: a[0].toString()}); } });
  send({f: 'I', msg: m.name + ' gefunden, Haken gesetzt'});
  return true;
}
if (!haken()) { const t = setInterval(() => { if (haken()) clearInterval(t); }, 10); }
"""


def main():
    parser = argparse.ArgumentParser(description="FT_Write/FT_Read eines Programms mitlesen")
    parser.add_argument("exe", nargs="?", default=r"C:\ELITE\Tools\NavCom Test\NavCom Test.exe")
    parser.add_argument("--log", default="mitschnitt_navcom.log")
    parser.add_argument("--msfs", action="store_true", help="Elite-Treiber fuer MSFS 2020 starten")
    args = parser.parse_args()
    if args.msfs:
        args.exe = (r"C:\Program Files (x86)\ELITE FS2020 Hardware Driver"
                    r"\FS2020_ELITE_Driver_Beta_0.4\ELITEHardwareFS2020_App.exe")

    start = time.monotonic()
    log = open(args.log, "w", encoding="utf-8")

    def nachricht(msg, _daten):
        if msg["type"] != "send":
            print("Frida:", msg)
            return
        p = msg["payload"]
        t = time.monotonic() - start
        f = p["f"]
        if f == "W":
            zeile = f"{t:9.3f} SENDEN  {p['h']}  {p['d']}"
            print(zeile, flush=True)
        elif f == "R":
            zeile = f"{t:9.3f} EMPFANG {p['h']}  {p['d']}"
        elif f == "O":
            zeile = f"{t:9.3f} OEFFNEN {p['was']} -> Handle {p['h']} (Status {p['st']})"
            print(zeile, flush=True)
        elif f == "B":
            zeile = f"{t:9.3f} BAUD    {p['h']}  {p['baud']}"
            print(zeile, flush=True)
        elif f == "X":
            zeile = f"{t:9.3f} AUFRUF  {p['h']}  {p['n']}({p['a1']})"
            print(zeile, flush=True)
        elif f == "C":
            zeile = f"{t:9.3f} SCHLIESSEN {p['h']}"
            print(zeile, flush=True)
        else:
            zeile = f"{t:9.3f} INFO    {p.get('msg')}"
            print(zeile, flush=True)
        log.write(zeile + "\n")
        log.flush()

    geraet = frida.get_local_device()
    pid = geraet.spawn([args.exe], cwd=os.path.dirname(args.exe))
    sitzung = geraet.attach(pid)
    skript = sitzung.create_script(HOOK_JS)
    skript.on("message", nachricht)
    skript.load()
    geraet.resume(pid)
    print(f"{os.path.basename(args.exe)} laeuft (PID {pid}). Mitschnitt nach {args.log}.")
    try:
        input("Programm bedienen; zum Beenden hier Enter druecken.\n")
    except (KeyboardInterrupt, EOFError):
        pass
    try:
        sitzung.detach()
    except frida.InvalidOperationError:
        pass
    log.close()
    print("Fertig.")


if __name__ == "__main__":
    main()
