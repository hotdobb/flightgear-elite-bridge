# flightgear-elite-bridge

*English version: [README.md](README.md)*

Eine Brücke, die **Elite-Flugsimulator-Hardware** mit **FlightGear 2024.1** verbindet,
ohne die DLLs des Elite-Treibers. Sie spricht direkt über den FTDI-USB-Chip mit den
Geräten und kann darum später auch unter Linux laufen.

> **Inoffizielles Projekt.** Es stammt nicht vom Hersteller der Elite-Hardware und wird
> von ihm weder unterstützt noch betreut. „Elite“ und die Produktnamen sind Marken ihrer
> Inhaber. Das Geräteprotokoll wurde durch Beobachten der Hardware ermittelt, damit sie
> mit FlightGear zusammenarbeitet.

## Unterstützte Hardware

| Gerät | Seriennummer | Was geht |
|---|---|---|
| Elite Pro Panel II | BR200000 | Steuerhorn, Gas-/Propeller-/Gemischhebel, Klappen, Fahrwerkshebel und -lampen, Trimmung, Schalter, Zündschlüssel |
| Elite Seitenruderpedale | BR800000 | Seitenruder und Bremsen |
| Elite AP-3000 Avionikpanel | BR000000 | COM/NAV 1+2, ADF, DME, Transponder (Anzeigen und Knöpfe), Tasten und Lampen des Century-III-Autopiloten, Knöpfe CRS/HDG/NAV2/QNH, Apollo-GPS-Tasten, FREEZE |

Hauptflugzeug ist die **Piper Seneca II** aus FGAddon. Die Grundsteuerung (Horn, Pedale,
Hebel, Klappen, Fahrwerk, Trimmung) nutzt die Standard-Werte von FlightGear und geht in
jedem Flugzeug. Funk, Autopilot und Schalter brauchen ein Profil pro Flugzeug; für die
C172P gibt es einen Teil davon.

## Funktionen

- **Brückenfenster** (`elite_gui.py`): FlightGear starten, Achsen kalibrieren (Totzone,
  Kurve, Umkehren), Schalter-Test mit Klartext-Namen jeder Taste, Profile pro Flugzeug.
- **FlightGear-Add-on** (`fg-addon/`): setzt Schalter und Knöpfe im Flugzeug um, steuert
  die Anzeigen und Lampen des AP-3000.
- **Cockpit „Seneca II Elite“** (`seneca_elite.py`): eine Variante der Seneca, in der die
  Teile versteckt sind, die es als echte Hardware gibt (Funk, Autopilot, Hebel, Horn ...),
  dazu ein flaches 2D-Instrumentenbrett für einen eigenen Monitor.
- **Apollo-GPS-Bildschirm** (`elite_gps.py`): ein GPS im Stil des Apollo GX auf einem
  kleinen Touch-Monitor (Seiten NAV / NRST / DIRECT / INFO und bewegte Karte), bedient mit
  den Apollo-Tasten des AP-3000. Direct-To koppelt an das FlightGear-GPS und den
  Autopiloten. Im Seneca-Elite-Cockpit ersetzt dieselbe Anzeige das Bild des Garmin GPS 155.
- **Korrektur zweier Seneca-Fehler** (macht „Einrichten“, Originale bleiben als
  `.original`): Propellerregler rechts mit Faktor 0,1 statt 1,0 (rechter Motor sprang
  nicht an), fehlende Sound-Bedingungen der Kreisel von HSI und Wendezeiger.
- **Englische oder deutsche** Oberfläche (Brückenfenster, GPS-Bildschirm, Bordcomputer).

## Voraussetzungen

- Windows 10/11 (Linux: geplant, nicht getestet; braucht `libftd2xx.so`)
- [Python 3](https://www.python.org/) von python.org (mit dem Starter `py`, tkinter ist
  dabei). Für die Brücke keine weiteren Pakete.
- FTDI-**D2XX**-Treiber (`ftd2xx.dll`). Er kommt mit dem Elite-Treiber; sonst bei FTDI.
- FlightGear 2024.1 und die **Seneca II** (im FlightGear-Launcher unter „Flugzeuge“
  installieren).

## Erste Schritte

1. Dieses Repository herunterladen (Code → Download ZIP) und entpacken, z. B. nach
   `C:\ElitePrj`.
2. FlightGear einmal starten (der Launcher genügt), die Seneca II installieren und einmal
   damit starten.
3. **`bruecke-fenster.cmd`** doppelklicken. Das Brückenfenster öffnet sich.
4. Oberfläche auf Deutsch stellen: Reiter **Start** → **Advanced** → **Language /
   Sprache** → Deutsch, Fenster schliessen und neu öffnen.
5. Reiter **Start** → **Erweitert** → **Einrichten**. Das kopiert die Protokolldateien
   nach FlightGear, korrigiert die Seneca-Fehler und erzeugt das Seneca-Elite-Cockpit.
6. Reiter **Achsen kalibrieren**: Hebel, Horn und Pedale kalibrieren.
7. Reiter **Start** → **FlightGear starten**.

## Stand und was noch fehlt

Funktioniert und mit der echten Hardware getestet: alles oben, auch ein ILS-Anflug mit
dem Century-III-Autopiloten (Modus APR) bis zur Landung von Hand.

Nicht fertig, **Mithilfe ist willkommen**:

- Code und Kommentare sind **Deutsch**. Die Oberfläche ist beim ersten Start Englisch und
  lässt sich auf Deutsch umstellen (Start → Erweitert → Language / Sprache); einzelne
  seltene Meldungen können noch deutsch sein.
- Linux (udev-Regeln, `libftd2xx.so`) ist nicht getestet.
- Am Gerät noch nicht geprüft: Reihenfolge der Marker-Lampen, TRIM-Lampe des Autopiloten,
  INSTR-Taste, Modi NAV (VOR) und BC, CWS und Sprechtaste am Horn.
- Profile gibt es vor allem für die Seneca II; andere Flugzeuge brauchen ein eigenes.
- Der KAP140-Autopilot der C172P ist nicht an die Tasten des AP-3000 angeschlossen.

## Dateien

| Datei | Zweck |
|---|---|
| `elite_gui.py`, `bruecke-fenster.cmd` | Brückenfenster (Hauptprogramm) |
| `elite_fg.py`, `bruecke.cmd` | Brücke ohne Fenster (Konsole) |
| `elite_rohdaten.py` | FTDI-Zugriff und Protokoll-Dekoder |
| `elite_avionik.py`, `elite_bord.py` | Anzeigen und Lampen des AP-3000 |
| `elite_gps.py` | Apollo-GPS-Bildschirm |
| `elite_einrichten.py` | Einrichten |
| `elite_sprache.py` | englische/deutsche Texte der Oberfläche |
| `seneca_elite.py`, `elite_innen.py` | Seneca-Elite-Cockpit, 2D-Panel, Innenraum |
| `elite.xml`, `elite_aus.xml` | FlightGear-Generic-Protokoll (Eingang/Ausgang) |
| `fg-addon/` | FlightGear-Add-on |
| `fg-config/` | Kamera-/Fenster-Einstellung für zwei Monitore |
| `elite_lernen.py`, `elite_senden.py`, `elite_anzeige.py`, `elite_mitlesen.py`, `hebel_auswertung.py`, `*.cmd` | Werkzeuge, mit denen das Protokoll ermittelt wurde (Tasten anlernen, Anzeigen testen, der Hersteller-Software zuschauen) |

## Lizenz

GNU General Public License, Version 2 oder (nach Wahl) jede spätere Version, wie
FlightGear und die Seneca II. Siehe [LICENSE](LICENSE).
