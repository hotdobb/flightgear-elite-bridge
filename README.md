# flightgear-elite-bridge

*Deutsche Fassung: [README.de.md](README.de.md)*

A bridge that connects **Elite flight simulator hardware** to **FlightGear 2024.1**,
without the Elite driver DLLs. It talks to the devices directly over their FTDI USB
chip, so it can later run on Linux as well.

> **Unofficial project.** It is not made, endorsed or supported by the manufacturer of
> the Elite hardware. "Elite" and the product names are trademarks of their owners.
> The device protocol was worked out by observing the hardware, for interoperability.

## Supported hardware

| Device | Serial prefix | What works |
|---|---|---|
| Elite Pro Panel II | BR200000 | yoke, throttle/prop/mixture levers, flaps, gear lever and gear lights, trims, switches, magnetos/starter key |
| Elite rudder pedals | BR800000 | rudder and toe brakes |
| Elite AP-3000 avionics panel | BR000000 | COM/NAV 1+2, ADF, DME, transponder (displays and knobs), Century III autopilot buttons and lights, CRS/HDG/NAV2/QNH knobs, Apollo GPS keys, FREEZE |

The main aircraft is the **Piper Seneca II** from FGAddon. The basic flight controls
(yoke, pedals, levers, flaps, gear, trims) use FlightGear's standard properties and work
in any aircraft. Radios, autopilot and switches need a per-aircraft profile; some
C172P support exists.

## Features

- **Bridge window** (`elite_gui.py`): start FlightGear, calibrate axes (dead zone, curve,
  reverse), switch test with plain-text names of every button, profiles per aircraft.
- **FlightGear add-on** (`fg-addon/`): applies switches and knobs to the aircraft, drives
  the AP-3000 displays and lamps.
- **"Seneca II Elite" cockpit** (`seneca_elite.py`): a variant of the Seneca where the
  parts that exist as real hardware (radios, autopilot, levers, yoke ...) are hidden,
  plus a flat 2D instrument panel for a separate monitor.
- **Apollo GPS screen** (`elite_gps.py`): an Apollo GX style GPS on a small touch
  monitor (NAV / NRST / DIRECT / INFO pages and a moving map), operated with the Apollo
  keys of the AP-3000. Direct-To couples to the FlightGear GPS and the autopilot. In the
  Seneca Elite cockpit the same display replaces the Garmin GPS 155 picture.
- **Fixes for two Seneca bugs** (applied by "Einrichten", originals kept as `.original`):
  right propeller governor factor 0.1 instead of 1.0 (right engine would not start),
  missing sound conditions for the HSI/turn coordinator gyros.

## Requirements

- Windows 10/11 (Linux: planned, not tested; needs `libftd2xx.so`)
- [Python 3](https://www.python.org/) from python.org (with the `py` launcher, tkinter
  included). No extra packages for the bridge.
- FTDI **D2XX** driver (`ftd2xx.dll`). It is installed with the Elite driver; otherwise
  get it from FTDI.
- FlightGear 2024.1 and the **Seneca II** (install it in the FlightGear launcher under
  "Aircraft").

## Getting started

1. Download this repository (Code → Download ZIP) and unpack it, e.g. to `C:\ElitePrj`.
2. Start FlightGear once (the launcher is enough), install the Seneca II and start it
   once.
3. Double-click **`bruecke-fenster.cmd`**. The bridge window opens.
4. Tab **Start** → **Erweitert** → **Einrichten**. This copies the protocol files into
   FlightGear, fixes the Seneca bugs and creates the Seneca Elite cockpit.
5. Tab **Achsen kalibrieren**: calibrate the levers, yoke and pedals.
6. Tab **Start** → **FlightGear starten**.

## Status and what is missing

Working and tested with the real hardware: all of the above, including an ILS approach
with the Century III autopilot (APR mode) down to a hand-flown landing.

Not finished — **contributions are welcome**:

- The user interface and the code comments are **German only**. An English UI was
  planned (switchable EN/DE) but is not done yet.
- Linux support (udev rules, `libftd2xx.so`) is untested.
- Not yet verified on the hardware: marker beacon lamp order, autopilot TRIM lamp,
  INSTR key, NAV (VOR) and BC modes, CWS and push-to-talk on the yoke.
- Profiles exist mainly for the Seneca II; other aircraft need their own profile.
- The KAP140 autopilot of the C172P is not mapped to the AP-3000 keys.

## Files

| File | Purpose |
|---|---|
| `elite_gui.py`, `bruecke-fenster.cmd` | bridge window (main entry point) |
| `elite_fg.py`, `bruecke.cmd` | bridge without window (console) |
| `elite_rohdaten.py` | FTDI access and protocol decoder |
| `elite_avionik.py`, `elite_bord.py` | AP-3000 displays and lamps |
| `elite_gps.py` | Apollo GPS screen |
| `elite_einrichten.py` | setup ("Einrichten") |
| `seneca_elite.py`, `elite_innen.py` | Seneca Elite cockpit, 2D panel, interior |
| `elite.xml`, `elite_aus.xml` | FlightGear generic protocol (input/output) |
| `fg-addon/` | FlightGear add-on |
| `fg-config/` | camera/window setup for two monitors |
| `elite_lernen.py`, `elite_senden.py`, `elite_anzeige.py`, `elite_mitlesen.py`, `hebel_auswertung.py`, `*.cmd` | tools used to work out the protocol (learning buttons, testing displays, watching the vendor software) |

## License

GNU General Public License, version 2 or (at your option) any later version — the same
license as FlightGear and the Seneca II. See [LICENSE](LICENSE).
