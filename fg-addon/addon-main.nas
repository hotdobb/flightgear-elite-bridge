# Elite Bruecke: elite_fg.py schreibt Schalterzustaende nach /elite/input/*,
# hier werden sie auf die Properties des geladenen Flugzeugs umgesetzt.
# Pfade fuer andere Flugzeuge zu setzen schadet nicht (sie bleiben unbenutzt),
# daher werden Seneca II und C172P gleichzeitig bedient.

var IN = "/elite/input/";

# einfache Ein/Aus-Schalter: Eingang -> Liste von Ziel-Properties
var SCHALTER = {
    "batterie":   ["/controls/electric/battery-switch", "/controls/switches/master-bat"],
    "radio":      ["/controls/switches/master-avionics", "/controls/electric/avionic-switch"],
    "pitot":      ["/controls/anti-ice/pitot-heat"],
    "fahrwerk":   ["/controls/gear/gear-down"],
    "lima-l":     ["/controls/electric/engine[0]/generator", "/controls/switches/master-alt"],
    "lima-r":     ["/controls/electric/engine[1]/generator"],
    "pumpe-l":    ["/controls/engines/engine[0]/fuel-pump"],
    "pumpe-r":    ["/controls/engines/engine[1]/fuel-pump"],
    # NAV schaltet auch die Instrumentenbeleuchtung, aber nur mit Strom (instrumentenlicht)
    "nav":        ["/controls/lighting/nav-lights"],
    "strobe":     ["/controls/lighting/strobe"],
    "landing":    ["/controls/lighting/landing-lights"],
    # Reserve-Schalter am Pro Panel = Rollscheinwerfer (Wunsch Nutzer 2026-11-12)
    "reserve":    ["/controls/lighting/taxi-light"],
};

# Instrumentenbeleuchtung: NAV-Schalter EIN und Strom auf dem Bus (wie im echten Flugzeug:
# ohne Batterie/Lichtmaschine bleibt es dunkel). Seneca instruments/factor, C172P
# instruments-norm; Funkgeraete gehoeren zum Radio-Master.
var LICHT_ZIELE = ["/sim/model/material/instruments/factor",
                   "/controls/lighting/instruments-norm"];
var LICHT_MIN_VOLT = 8;
var instrumentenlicht = func {
    var volt = getprop("/systems/electrical/bus[0]/u-volts");
    if (volt == nil)
        volt = getprop("/systems/electrical/volts") or 0;
    var an = (getprop(IN ~ "nav") and volt >= LICHT_MIN_VOLT) ? 1 : 0;
    foreach (var ziel; LICHT_ZIELE)
        if ((getprop(ziel) or 0) != an)
            setprop(ziel, an);
};

# Tankwahl am Panel (0 OFF, 1 LEFT, 2 BOTH, 3 RIGHT) -> Seneca-Wahlschalter
# je Motor (1 = eigener Tank, -1 = Crossfeed, 0 = aus)
var TANKWAHL = [[0, 0], [1, -1], [1, 1], [-1, 1]];

var setze_magnetos = func(motor) {
    var l = getprop(IN ~ "mag-" ~ motor ~ "-l") or 0;
    var r = getprop(IN ~ "mag-" ~ motor ~ "-r") or 0;
    var basis = "/controls/engines/engine[" ~ motor ~ "]/";
    if (getprop(basis ~ "magneto[0]") != nil) {
        # Seneca: magneto[0] = rechter, magneto[1] = linker Magnet
        setprop(basis ~ "magneto[0]", r);
        setprop(basis ~ "magneto[1]", l);
    } else {
        setprop(basis ~ "magnetos", r + 2 * l);
        if (motor == 0)
            setprop("/controls/switches/magnetos", r + 2 * l);
    }
};

var setze_anlasser = func(motor) {
    var an = getprop(IN ~ "anlasser-" ~ motor) or 0;
    var basis = "/controls/engines/engine[" ~ motor ~ "]/";
    if (getprop(basis ~ "starter-switch") != nil) {
        setprop(basis ~ "starter-switch", an);
    } else {
        setprop(basis ~ "starter", an);
        if (motor == 0)
            setprop("/controls/switches/starter", an);
    }
};

# C172P: Wahlschalter = selected-Flags links/rechts (0 OFF, 1 LEFT, 2 BOTH, 3 RIGHT);
# mit Langstreckentanks (/fdm/jsbsim/fuel/tank) gelten tank[2]/[3] statt [0]/[1]
var C172_TANKS = [[0, 0], [1, 0], [1, 1], [0, 1]];

var setze_tankwahl = func {
    var wahl = getprop(IN ~ "tankwahl") or 0;
    if (string.match(getprop("/sim/aircraft") or "", "c172p*")) {
        var lang = getprop("/fdm/jsbsim/fuel/tank") ? 1 : 0;
        forindex (var seite; [0, 1]) {
            var t = "/consumables/fuel/tank[";
            setprop(t ~ (seite + 2 * lang) ~ "]/selected", C172_TANKS[wahl][seite]);
            setprop(t ~ (seite + 2 * (1 - lang)) ~ "]/selected", 0);
        }
        return;
    }
    forindex (var seite; [0, 1]) {
        setprop("/controls/fuel/tank[" ~ seite ~ "]/fuel_selector-position",
                TANKWAHL[wahl][seite]);
        if (contains(globals, "SenecaII"))
            SenecaII.SetFuelSelector(seite);
    }
};

# Steuerhorn -> Ruder, ausser der Century III steuert die Achse gerade selbst
# (sonst wuerde das Horn seine Servo-Befehle staendig ueberschreiben)
var steuerhorn = func {
    var ap = "/autopilot/CENTURYIII/controls/";
    if (!getprop(ap ~ "roll/button-state"))
        setprop("/controls/flight/aileron", getprop(IN ~ "querruder") or 0);
    if (!getprop(ap ~ "pitch/button-state"))
        setprop("/controls/flight/elevator", getprop(IN ~ "hoehenruder") or 0);
};

# TRIM-Lampe am AP-3000: Der Trimm-Servo des Century III laeuft (Autopilot haelt die Nase
# oder die weisse Wippe wird gedrueckt) und die Trimmung bewegt sich. Die Lampe bleibt
# kurz nach, damit sie bei kleinen Korrekturen nicht flackert.
var trimm_alt = 0;
var trimm_nachlauf = 0;

var ap_trimmt = func {
    var trimm = getprop("/controls/flight/elevator-trim") or 0;
    var servo = getprop("/autopilot/CENTURYIII/controls/pitch/button-state")
                or (getprop("/autopilot/CENTURYIII/controls/manual-trim") or 0) != 0;
    if (servo and math.abs(trimm - trimm_alt) > 0.00002)
        trimm_nachlauf = 15;      # 15 Takte = 0,5 s
    elsif (trimm_nachlauf > 0)
        trimm_nachlauf -= 1;
    trimm_alt = trimm;
    setprop("/elite/ap-trimmt", trimm_nachlauf > 0 ? 1 : 0);
};

# Taster, die etwas verstellen, solange sie gehalten werden
var tick = func {
    steuerhorn();
    # Hoehentrimm: Richtung mal Trimm-Tempo des Profils (kommt fertig von der Bruecke)
    var trimm = getprop(IN ~ "hoehentrimm") or 0;
    if (trimm != 0)
        controls.elevatorTrim(trimm);
    ap_trimmt();
    adf_anzeige();
    foreach (var motor; [0, 1]) {
        var cowl = getprop(IN ~ "cowl-" ~ motor) or 0;
        if (cowl != 0) {
            var pfad = "/controls/engines/engine[" ~ motor ~ "]/cowl-flaps-norm";
            var neu = (getprop(pfad) or 0) + cowl * 0.01;
            setprop(pfad, math.min(1, math.max(0, neu)));
        }
    }
};

# --- AP-3000: Drehknoepfe und Tausch-Tasten -------------------------------------
# Die Bruecke schickt Zaehler; hier wird die Differenz zum letzten Wert angewendet.
# Aendert sich "ap-sitzung" (Bruecke neu gestartet), werden die Zaehler neu gemerkt.
var FUNK = {
    # Name: [Basis-Pfad, kleinste MHz, groesste MHz, Feinschritt in MHz]
    "com1": ["/instrumentation/comm[0]/frequencies/", 118, 136, 0.025],
    "com2": ["/instrumentation/comm[1]/frequencies/", 118, 136, 0.025],
    "nav1": ["/instrumentation/nav[0]/frequencies/", 108, 117, 0.05],
    "nav2": ["/instrumentation/nav[1]/frequencies/", 108, 117, 0.05],
    # DME hat keine Standby-Frequenz; der Knopf stellt die eigene direkt
    "dme":  ["/instrumentation/dme/frequencies/", 108, 117, 0.05, "selected-mhz"],
};
var zaehler_alt = {};

var umlauf = func(wert, von, bis) {
    var bereich = bis - von + 1;
    return von + math.mod(wert - von + bereich * 100, bereich);
};

var stelle_funk = func(name, grob, schritte) {
    var f = FUNK[name];
    var pfad = f[0] ~ (size(f) > 4 ? f[4] : "standby-mhz");
    var khz = math.round((getprop(pfad) or f[1]) * 1000);
    var mhz = int(khz / 1000);
    var rest = khz - mhz * 1000;
    var fein = math.round(f[3] * 1000);
    if (grob)
        mhz = umlauf(mhz + schritte, f[1], f[2]);
    else
        rest = math.mod(rest + schritte * fein + 100000, 1000);
    setprop(pfad, (mhz * 1000 + rest) / 1000);
};

var stelle_adf = func(grob, schritte) {
    var pfad = "/instrumentation/adf[0]/frequencies/standby-khz";
    var khz = int(getprop(pfad) or 200);
    khz = umlauf(khz + schritte * (grob ? 100 : 1), 200, 1799);
    setprop(pfad, khz);
};

var tausche = func(basis, einheit) {
    var aktiv = getprop(basis ~ "selected-" ~ einheit);
    setprop(basis ~ "selected-" ~ einheit, getprop(basis ~ "standby-" ~ einheit));
    setprop(basis ~ "standby-" ~ einheit, aktiv);
};

# OFF-Taster COM/NAV 1 bzw. 2 am AP-3000: schaltet das Funkgeraet auch in FlightGear aus
# (nicht nur die Anzeige dunkel). Solange die Bruecke noch nichts gemeldet hat, bleibt es an.
var setze_funk_an = func(nr) {
    # 1 = an, -1 = aus, 0 oder nichts = Bruecke hat noch nichts gemeldet
    var an = getprop(IN ~ "funk-an-" ~ nr) or 0;
    if (an == 0)
        return;
    setprop("/instrumentation/comm[" ~ nr ~ "]/power-btn", an > 0 ? 1 : 0);
    setprop("/instrumentation/nav[" ~ nr ~ "]/power-btn", an > 0 ? 1 : 0);
};

# Autopilot-Tasten des AP-3000 auf den Century III der Seneca
var AP = "/autopilot/CENTURYIII/controls/";
var AP_MODUS = {"nav": 0, "hdg": 2, "apr": 3, "bc": 4};

var ap_taste = func(taste) {
    if (taste == "eng") {
        # AP ENG: Autopilot (Roll + Pitch) ein, bzw. alles aus - auch die Kurssteuerung,
        # sonst floege er beim naechsten Einschalten ungefragt wieder den alten Kurs
        var an = !getprop(AP ~ "roll/button-state");
        setprop(AP ~ "roll/button-state", an);
        setprop(AP ~ "pitch/button-state", an);
        if (!an) {
            setprop(AP ~ "alt/button-state", 0);
            setprop(AP ~ "hdg/button-state", 0);
        }
    } elsif (taste == "alt") {
        setprop(AP ~ "alt/button-state", !getprop(AP ~ "alt/button-state"));
    } elsif (taste == "fd") {
        setprop(AP ~ "pitch/button-state", !getprop(AP ~ "pitch/button-state"));
    } elsif (contains(AP_MODUS, taste)) {
        # Moduswahl + HDG-Schalter des Century III (Kurssteuerung, braucht ROLL).
        # Nochmal dieselbe Taste: Kurssteuerung aus, nur noch Flaechen waagerecht.
        var hdg = AP ~ "hdg/button-state";
        if (getprop(hdg) and getprop(AP ~ "mode") == AP_MODUS[taste]) {
            setprop(hdg, 0);
        } else {
            setprop(AP ~ "mode", AP_MODUS[taste]);
            if (getprop(AP ~ "roll/button-state"))
                setprop(hdg, 1);
        }
    }
};

# Knoepfe am Horn. Sprechtaste = AP Disconnect: der Eingang "disconnect" des Century III
# schaltet ROLL ab und damit auch HDG, PITCH und ALT.
# CWS (Control Wheel Steering): solange gedrueckt, ist der Autopilot ab und das Horn
# steuert; beim Loslassen werden die vorher aktiven Schalter wieder eingeschaltet.
var AP_SCHALTER = ["roll", "pitch", "hdg", "alt"];
var cws_gemerkt = nil;

var cws = func(gedrueckt) {
    if (gedrueckt) {
        if (!getprop(AP ~ "roll/button-state"))
            return;
        cws_gemerkt = [];
        foreach (var name; AP_SCHALTER)
            append(cws_gemerkt, getprop(AP ~ name ~ "/button-state") ? 1 : 0);
        setprop(AP ~ "disconnect", 1);
    } elsif (cws_gemerkt != nil) {
        setprop(AP ~ "disconnect", 0);
        forindex (var i; AP_SCHALTER)
            setprop(AP ~ AP_SCHALTER[i] ~ "/button-state", cws_gemerkt[i]);
        cws_gemerkt = nil;
    }
};

# Kurs-Knoepfe der untersten Reihe: 1 Grad pro Raste
var drehe_grad = func(pfad, schritte) {
    setprop(pfad, math.mod((getprop(pfad) or 0) + schritte + 3600, 360));
};

# Hoehenmesser: 1 hPa pro Raste (beide Hoehenmesser, falls vorhanden)
var stelle_qnh = func(schritte) {
    # einmal rechnen, dann beide schreiben (sonst doppelt, falls [1] auf [0] zeigt)
    var inhg = getprop("/instrumentation/altimeter[0]/setting-inhg");
    if (inhg == nil)
        return;
    var hpa = math.min(1050, math.max(950, math.round(inhg * 33.8639) + schritte));
    foreach (var nr; [0, 1])
        setprop("/instrumentation/altimeter[" ~ nr ~ "]/setting-inhg", hpa / 33.8639);
};

var ap_ereignis = func(name, schritte) {
    var teile = split("-", name);
    if (name == "hdg") {
        # Heading Bug: Seneca (KI525) und C172P. Vom Kursinstrument aus rechnen und beide
        # gleich setzen, sonst bleiben sie versetzt, wenn einer im Simulator verstellt wurde.
        var ki525 = "/instrumentation/kcs55/ki525/selected-heading-deg";
        var bug = "/autopilot/settings/heading-bug-deg";
        var grad = getprop(ki525);
        if (grad == nil)
            grad = getprop(bug) or 0;
        grad = math.mod(grad + schritte + 3600, 360);
        if (getprop(ki525) != nil)
            setprop(ki525, grad);
        setprop(bug, grad);
    } elsif (name == "crs") {
        # Kurs NAV1 (bei der Seneca mit dem KI525 verbunden)
        drehe_grad("/instrumentation/nav[0]/radials/selected-deg", schritte);
    } elsif (name == "obs2") {
        drehe_grad("/instrumentation/nav[1]/radials/selected-deg", schritte);
    } elsif (name == "mdi") {
        # Kompassrose des ADF-Instruments
        drehe_grad("/instrumentation/adf[0]/rotation-deg", schritte);
    } elsif (name == "qnh") {
        stelle_qnh(schritte);
    } elsif (name == "freeze") {
        fgcommand("pause");
    } elsif (name == "nick") {
        # Nickrad des Century III: 0,5 Grad pro Klick, rechts = Nase hoch
        var pfad = "/autopilot/CENTURYIII/settings/pitch-wheel-deg";
        var grad = (getprop(pfad) or 0) + schritte * 0.5;
        setprop(pfad, math.min(10, math.max(-10, grad)));
    } elsif (teile[0] == "ap") {
        ap_taste(teile[1]);
    } elsif (teile[0] == "xpdr") {
        # Transponder-Ziffer 0..7 (digit[0] = Einer, digit[3] = Tausender)
        var pfad = "/instrumentation/transponder/inputs/digit[" ~ teile[1] ~ "]";
        setprop(pfad, math.mod((getprop(pfad) or 0) + schritte + 800, 8));
    } elsif (teile[0] == "adf") {
        var adf = "/instrumentation/adf[0]/";
        if (teile[1] == "tausch") {
            # FRQ-Taste (KR87): zeigt rechts die Zeit, kommt erst die Frequenz zurueck;
            # sonst tauscht sie aktive und Standby-Frequenz
            if (getprop(adf ~ "display-mode"))
                setprop(adf ~ "display-mode", 0);
            else
                tausche(adf ~ "frequencies/", "khz");
        } elsif (teile[1] == "modus") {
            # ADF-Taste: ADF <-> ANT (Seneca KR87 ueber adf-btn, sonst direkt der Modus)
            if (getprop(adf ~ "adf-btn") != nil)
                setprop(adf ~ "adf-btn", !getprop(adf ~ "adf-btn"));
            else
                setprop(adf ~ "mode", getprop(adf ~ "mode") == "ant" ? "adf" : "ant");
        } elsif (teile[1] == "bfo") {
            if (getprop(adf ~ "bfo-btn") != nil)
                setprop(adf ~ "bfo-btn", !getprop(adf ~ "bfo-btn"));
        } elsif (teile[1] == "flt") {
            # FLT/ET-Taste: Flugzeit zeigen, nochmal = Stoppuhr (ET), nochmal = Flugzeit
            setprop(adf ~ "display-mode", getprop(adf ~ "display-mode") == 1 ? 2 : 1);
        } elsif (teile[1] == "set") {
            # SET/RST: Stoppuhr (ET) auf null; das KR87 der Seneca liest set-btn alle 0,1 s
            setprop(adf ~ "set-btn", 1);
            adf_set_timer.restart(0.3);
        } elsif (teile[1] == "ident") {
            # Kennung des Funkfeuers hoerbar ein/aus
            setprop(adf ~ "ident-audible", !getprop(adf ~ "ident-audible"));
        } else {
            stelle_adf(teile[1] == "grob", schritte);
        }
    } elsif (teile[1] == "tausch") {
        tausche(FUNK[teile[0]][0], "mhz");
    } else {
        stelle_funk(teile[0], teile[1] == "grob", schritte);
    }
};

var AP_ZAEHLER = ["com1-grob", "com1-fein", "com2-grob", "com2-fein",
                  "nav1-grob", "nav1-fein", "nav2-grob", "nav2-fein",
                  "adf-grob", "adf-fein",
                  "com1-tausch", "com2-tausch", "nav1-tausch", "nav2-tausch", "adf-tausch",
                  "xpdr-0", "xpdr-1", "xpdr-2", "xpdr-3",
                  "ap-eng", "ap-hdg", "ap-nav", "ap-apr", "ap-bc", "ap-alt", "ap-fd", "hdg", "crs", "dme-grob", "dme-fein",
                  "mdi", "obs2", "qnh", "freeze", "nick",
                  "adf-modus", "adf-bfo", "adf-flt", "adf-set", "adf-ident"];

# SET-Taste der ADF-Reihe wieder loslassen (siehe ap_ereignis); angelegt in main
var adf_set_timer = nil;

# Schriftzuege und rechter Block der ADF-Anzeige am AP-3000 (Bits wie ADF_SCHRIFT in
# elite_fg.py: 1 ADF, 2 ANT, 4 BFO, 8 FRQ, 16 FLT, 32 ET)
var adf_anzeige = func {
    var adf = "/instrumentation/adf[0]/";
    var modus = getprop(adf ~ "mode") or "adf";
    var seite = getprop(adf ~ "display-mode") or 0;
    var bits = (modus == "ant" ? 2 : 1) + (modus == "bfo" ? 4 : 0)
               + (seite == 1 ? 16 : (seite == 2 ? 32 : 8));
    setprop("/elite/adf-anzeige", bits);
    setprop("/elite/adf-rechts", seite == 0 ? (getprop(adf ~ "frequencies/standby-khz") or 0)
                                            : (getprop(adf ~ "right-display") or 0));
};

# GPS-Bildschirm (elite_gps.py) liest /elite/gps per httpd: eigene Lage alle 0,5 s,
# Flugplaetze und Funkfeuer im Umkreis alle 5 s
var GPS = "/elite/gps/";
var GPS_UMKREIS = 60;  # NM

var gps_lage = func {
    setprop(GPS ~ "lat", getprop("/position/latitude-deg"));
    setprop(GPS ~ "lon", getprop("/position/longitude-deg"));
    setprop(GPS ~ "alt-ft", getprop("/position/altitude-ft"));
    setprop(GPS ~ "gs-kt", getprop("/velocities/groundspeed-kt"));
    setprop(GPS ~ "trk-deg", getprop("/orientation/track-deg")
                             or getprop("/orientation/heading-deg"));
    setprop(GPS ~ "magvar-deg", getprop("/environment/magnetic-variation-deg") or 0);
    # FlightGear-GPS (Direct-To) und ob NAV1 dem GPS folgt
    setprop(GPS ~ "gps-modus", getprop("/instrumentation/gps/mode") or "");
    setprop(GPS ~ "gps-id", getprop("/instrumentation/gps/wp/wp[1]/ID") or "");
    setprop(GPS ~ "dtk-deg", getprop("/instrumentation/gps/desired-course-deg") or 0);
    setprop(GPS ~ "xtk-nm", getprop("/instrumentation/gps/wp/wp[1]/course-error-nm") or 0);
    setprop(GPS ~ "quelle-gps", getprop("/instrumentation/nav[0]/slaved-to-gps") ? 1 : 0);
};

# Auftraege vom GPS-Bildschirm (per httpd geschrieben; httpd schreibt nur in vorhandene
# Knoten, darum legt gps_start sie an)
var gps_direct = func {
    var scratch = "/instrumentation/gps/scratch/";
    setprop(scratch ~ "ident", getprop(GPS ~ "ziel/ident"));
    setprop(scratch ~ "latitude-deg", getprop(GPS ~ "ziel/lat"));
    setprop(scratch ~ "longitude-deg", getprop(GPS ~ "ziel/lon"));
    setprop(scratch ~ "type", getprop(GPS ~ "ziel/typ"));
    setprop("/instrumentation/gps/command", "direct");
};

var gps_start = func {
    foreach (var name; ["ident", "typ"])
        setprop(GPS ~ "ziel/" ~ name, "");
    foreach (var name; ["lat", "lon", "auftrag"])
        setprop(GPS ~ "ziel/" ~ name, 0);
    setprop(GPS ~ "quelle-auftrag", 0);
    setlistener(GPS ~ "ziel/auftrag", gps_direct, 0, 0);
    # NAV/GPS-Taste: NAV1 (Kursinstrument und Autopilot) folgt dem GPS oder dem VOR
    setlistener(GPS ~ "quelle-auftrag", func {
        var pfad = "/instrumentation/nav[0]/slaved-to-gps";
        setprop(pfad, !getprop(pfad));
    }, 0, 0);
    apollo_start();
};

# Apollo-Display im 3D-Cockpit (Seneca Elite: Flaeche "ApolloScreen" statt des Garmin).
# elite_gps.py schickt den Inhalt des Elo-Displays als Text nach /elite/gps/anzeige:
# je Zeile ein Teil, Felder mit Tab getrennt
#   T spalte zeile farbe(b/s) groesse(g/k) anker(w/e/center) text | B zeile | G | K tasten...
var APOLLO_W = 1024;
var APOLLO_H = 320;
var APOLLO_RAND = 6;
var BERNSTEIN = [1, 0.69, 0];
var apollo_wurzel = nil;

var apollo_start = func {
    props.globals.initNode(GPS ~ "anzeige", "", "STRING");
    var leinwand = canvas.new({"name": "EliteApollo", "size": [APOLLO_W, APOLLO_H],
                               "view": [APOLLO_W, APOLLO_H], "mipmapping": 1});
    leinwand.setColorBackground(0, 0, 0, 1);
    leinwand.addPlacement({"node": "ApolloScreen"});
    apollo_wurzel = leinwand.createGroup();
    setlistener(GPS ~ "anzeige", func(n) apollo_zeichne(n.getValue() or ""), 1, 0);
};

var apollo_farbe = func(text) {
    if (text == "white")
        return [1, 1, 1];
    if (text == "black")
        return [0, 0, 0];
    if (size(text) != 7)
        return [0.67, 0.67, 0.67];
    return [num("0x" ~ substr(text, 1, 2)) / 255, num("0x" ~ substr(text, 3, 2)) / 255,
            num("0x" ~ substr(text, 5, 2)) / 255];
};

var apollo_zeichne = func(inhalt) {
    apollo_wurzel.removeAllChildren();
    var x0 = APOLLO_RAND;
    var y0 = APOLLO_RAND;
    var x1 = APOLLO_W - APOLLO_RAND;
    var y1 = APOLLO_H - APOLLO_RAND;
    var zeile_h = (y1 - y0) / 8;
    var gross = zeile_h * 0.8;
    var rechteck = func(xa, ya, xb, yb, fuellen) {
        var p = apollo_wurzel.createChild("path").rect(xa, ya, xb - xa, yb - ya);
        if (fuellen)
            p.setColorFill(BERNSTEIN[0], BERNSTEIN[1], BERNSTEIN[2]);
        else
            p.setColor(0.35, 0.24, 0).setStrokeLineWidth(2);
    };
    var schreibe = func(x, y, text, farbe, groesse, ausrichtung) {
        apollo_wurzel.createChild("text").setText(text)
            .setFont("LiberationFonts/LiberationMono-Bold.ttf")
            .setFontSize(groesse, 1).setColor(farbe[0], farbe[1], farbe[2])
            .setAlignment(ausrichtung).setTranslation(x, y);
    };
    foreach (var zeile; split("\n", inhalt)) {
        var f = split("\t", zeile);
        if (f[0] == "T" and size(f) >= 7) {
            var x = x0 + 14 + num(f[1]) * (x1 - x0 - 28);
            var y = y0 + zeile_h * (num(f[2]) + 0.6);
            var anker = f[5] == "w" ? "left-center"
                      : f[5] == "e" ? "right-center" : "center-center";
            schreibe(x, y, f[6], f[3] == "s" ? [0, 0, 0] : BERNSTEIN,
                     f[4] == "k" ? gross * 0.75 : gross, anker);
        } elsif (f[0] == "B" and size(f) >= 2) {
            rechteck(x0 + 4, y0 + zeile_h * (num(f[1]) + 0.1), x1 - 4,
                     y0 + zeile_h * (num(f[1]) + 1.1), 1);
        } elsif (f[0] == "G") {
            rechteck(x1 - 14 - zeile_h * 2.2, y0 + zeile_h * 0.15, x1 - 6,
                     y0 + zeile_h * 1.05, 1);
        # Karte (elite_gps.karte_teile): Pixel der Leinwand, Farben als #rrggbb
        } elsif (f[0] == "H" and size(f) >= 2) {
            apollo_wurzel.createChild("path").rect(0, 0, APOLLO_W, APOLLO_H)
                .setColorFill(apollo_farbe(f[1]));
        } elsif (f[0] == "O" and size(f) >= 7) {
            var p = apollo_wurzel.createChild("path").circle(num(f[3]), num(f[1]), num(f[2]))
                .setColor(apollo_farbe(f[4])).setStrokeLineWidth(num(f[6]));
            if (f[5] == "1")
                p.setStrokeDashArray([4, 4]);
        } elsif (f[0] == "F" and size(f) >= 5) {
            apollo_wurzel.createChild("path").circle(num(f[3]), num(f[1]), num(f[2]))
                .setColorFill(apollo_farbe(f[4]));
        } elsif (f[0] == "P" and size(f) >= 9) {
            var p = apollo_wurzel.createChild("path").moveTo(num(f[3]), num(f[4]));
            for (var i = 5; i + 1 < size(f); i += 2)
                p.lineTo(num(f[i]), num(f[i + 1]));
            p.close();
            if (f[1] != "")
                p.setColorFill(apollo_farbe(f[1]));
            if (f[2] != "")
                p.setColor(apollo_farbe(f[2])).setStrokeLineWidth(1.5);
        } elsif (f[0] == "L" and size(f) >= 7) {
            apollo_wurzel.createChild("path").moveTo(num(f[1]), num(f[2]))
                .lineTo(num(f[3]), num(f[4])).setColor(apollo_farbe(f[5]))
                .setStrokeLineWidth(num(f[6]));
        } elsif (f[0] == "X" and size(f) >= 8) {
            apollo_wurzel.createChild("text").setText(f[7])
                .setFont(f[5] == "1" ? "LiberationFonts/LiberationSans-Bold.ttf"
                                     : "LiberationFonts/LiberationSans-Regular.ttf")
                .setFontSize(num(f[4]), 1).setColor(apollo_farbe(f[3]))
                .setAlignment(f[6] == "w" ? "left-center"
                            : f[6] == "sw" ? "left-bottom" : "center-center")
                .setTranslation(num(f[1]), num(f[2]));
        } elsif (f[0] == "K") {
            # Bildschirmtasten unten
            var anzahl = size(f) - 1;
            var teil = (x1 - x0) / anzahl;
            var oben = y1 - zeile_h * 1.2;
            for (var i = 0; i < anzahl; i += 1) {
                var ka = x0 + i * teil + 4;
                var kb = x0 + (i + 1) * teil - 4;
                rechteck(ka, oben, kb, y1 - 4, 0);
                schreibe((ka + kb) / 2, (oben + y1 - 4) / 2, f[i + 1], BERNSTEIN,
                         gross * 0.75, "center-center");
            }
        }
    }
};

var laengste_piste_ft = func(apt) {
    var laenge = 0;
    foreach (var name; keys(apt.runways))
        laenge = math.max(laenge, apt.runways[name].length);
    return math.round(laenge * M2FT);
};

var gps_umgebung = func {
    var knoten = props.globals.getNode(GPS ~ "umgebung", 1);
    var liste = [];
    foreach (var apt; findAirportsWithinRange(GPS_UMKREIS)) {
        var kd = courseAndDistance(apt);
        append(liste, {apt: apt, brg: kd[0], dis: kd[1]});
    }
    liste = sort(liste, func(a, b) a.dis - b.dis);
    knoten.removeAllChildren();
    forindex (var i; liste) {
        if (i >= 40)
            break;
        var a = liste[i];
        knoten.getChild("apt", i, 1).setValues({
            id: a.apt.id, name: a.apt.name, lat: a.apt.lat, lon: a.apt.lon,
            brg: a.brg, dis: a.dis, piste: laengste_piste_ft(a.apt)});
    }
    var nr = 0;
    foreach (var typ; ["vor", "ndb"]) {
        foreach (var nav; findNavaidsWithinRange(GPS_UMKREIS, typ)) {
            if (nr >= 60)
                break;
            knoten.getChild("nav", nr, 1).setValues({
                id: nav.id, name: nav.name, typ: typ, freq: nav.frequency,
                lat: nav.lat, lon: nav.lon});
            nr += 1;
        }
    }
};

# Bordcomputer und Checkliste (elite_bord.py) lesen /elite/bord per httpd, alle 0,5 s neu.
# Das Fenster waehlt die Checkliste ueber /elite/bord/liste (Nummer in /sim/checklists).
var BORD = "/elite/bord/";

var bord_werte = func {
    forindex (var n; ["l", "r"]) {
        var s = ["l", "r"][n];
        var bedienung = "/controls/engines/engine[" ~ n ~ "]/";
        var motor = "/engines/engine[" ~ n ~ "]/";
        var tank = "/consumables/fuel/tank[";
        # Fluegeltank plus Zusatztank in der Motorgondel
        setprop(BORD ~ "tank-" ~ s, (getprop(tank ~ n ~ "]/level-gal_us") or 0)
                                    + (getprop(tank ~ (n + 2) ~ "]/level-gal_us") or 0));
        setprop(BORD ~ "ff-" ~ s, getprop(motor ~ "fuel-flow-gph") or 0);
        setprop(BORD ~ "lauf-" ~ s, getprop(motor ~ "running") ? 1 : 0);
        setprop(BORD ~ "rpm-" ~ s, getprop(motor ~ "rpm") or 0);
        setprop(BORD ~ "oeldruck-" ~ s, getprop(motor ~ "oil-pressure-psi") or 0);
        setprop(BORD ~ "mag-" ~ s, (getprop(bedienung ~ "magneto[0]") ? 1 : 0)
                                   + (getprop(bedienung ~ "magneto[1]") ? 1 : 0));
        setprop(BORD ~ "pumpe-" ~ s, getprop(bedienung ~ "fuel-pump") ? 1 : 0);
        setprop(BORD ~ "gas-" ~ s, getprop(bedienung ~ "throttle") or 0);
        setprop(BORD ~ "gemisch-" ~ s, getprop(bedienung ~ "mixture") or 0);
        setprop(BORD ~ "prop-" ~ s, getprop(bedienung ~ "propeller-pitch") or 0);
        setprop(BORD ~ "cowl-" ~ s, getprop(bedienung ~ "cowl-flaps-norm") or 0);
        setprop(BORD ~ "lima-" ~ s,
                getprop("/controls/electric/engine[" ~ n ~ "]/generator") ? 1 : 0);
        setprop(BORD ~ "tankwahl-" ~ s,
                getprop("/controls/fuel/tank[" ~ n ~ "]/fuel_selector-position") or 0);
    }
    setprop(BORD ~ "batterie", getprop("/controls/electric/battery-switch") ? 1 : 0);
    setprop(BORD ~ "avionik", getprop("/controls/electric/avionic-switch") ? 1 : 0);
    setprop(BORD ~ "volt", getprop("/systems/electrical/bus[0]/u-volts") or 0);
    setprop(BORD ~ "parkbremse", getprop("/controls/gear/brake-parking") ? 1 : 0);
    setprop(BORD ~ "fahrwerk", getprop("/controls/gear/gear-down") ? 1 : 0);
    setprop(BORD ~ "klappen", getprop("/controls/flight/flaps") or 0);
    setprop(BORD ~ "pitot", getprop("/controls/anti-ice/pitot-heat") ? 1 : 0);
    setprop(BORD ~ "landing", getprop("/controls/lighting/landing-lights") ? 1 : 0);
    setprop(BORD ~ "strobe", getprop("/controls/lighting/strobe") ? 1 : 0);
    setprop(BORD ~ "beacon", getprop("/controls/lighting/beacon") ? 1 : 0);
    setprop(BORD ~ "xpdr", getprop("/instrumentation/transponder/inputs/knob-mode") or 0);
    setprop(BORD ~ "oat-c", getprop("/environment/temperature-degc") or 0);
    setprop(BORD ~ "agl-ft", getprop("/position/altitude-agl-ft") or 0);
    setprop(BORD ~ "ias-kt", getprop("/velocities/airspeed-kt") or 0);
    setprop(BORD ~ "flugzeug", getprop("/sim/aircraft") or "");
    bord_checkliste();
};

# Gewaehlte Checkliste des Flugzeugs mit Name, Sollwert und - wenn die Liste selbst eine
# Bedingung mitbringt - ob der Punkt erfuellt ist (1/0, ohne Bedingung -1)
var bord_checkliste = func {
    var listen = props.globals.getNode("/sim/checklists", 1).getChildren("checklist");
    setprop(BORD ~ "listen", size(listen));
    var knoten = props.globals.getNode(BORD ~ "check", 1);
    knoten.removeAllChildren();
    if (size(listen) == 0)
        return;
    var nr = math.max(0, math.min(size(listen) - 1, getprop(BORD ~ "liste") or 0));
    var liste = listen[nr];
    var punkte = liste.getChildren("item");
    foreach (var seite; liste.getChildren("page"))
        foreach (var p; seite.getChildren("item"))
            append(punkte, p);
    knoten.getNode("nr", 1).setValue(nr);
    knoten.getNode("titel", 1).setValue(liste.getValue("title") or "");
    forindex (var i; punkte) {
        var wert = "";
        foreach (var w; punkte[i].getChildren("value"))
            wert = wert ~ (wert == "" ? "" : " ") ~ (w.getValue() or "");
        var bedingung = punkte[i].getNode("condition");
        knoten.getChild("item", i, 1).setValues({
            name: punkte[i].getValue("name") or "", wert: wert,
            ok: bedingung == nil ? -1 : (props.condition(bedingung) ? 1 : 0)});
    }
};

# Sitzhoehe (Augenhoehe der Cockpitsicht) je Flugzeug, vom Nutzer ausprobiert
var SITZHOEHE = {"SenecaII": 1.65};

var setze_sitzhoehe = func {
    var flugzeug = getprop("/sim/aircraft") or "";
    foreach (var name; keys(SITZHOEHE)) {
        if (find(name, flugzeug) < 0)
            continue;
        setprop("/sim/view[0]/config/y-offset-m", SITZHOEHE[name]);
        if (getprop("/sim/current-view/view-number") == 0)
            setprop("/sim/current-view/y-offset-m", SITZHOEHE[name]);
    }
};

var timer = nil;
var gps_timer = nil;
var gps_umgebung_timer = nil;
var sitz_timer = nil;
var schalter_timer = nil;
var bord_timer = nil;
var licht_timer = nil;

# Alle Schalterstellungen der Hardware einmal uebernehmen. Die Listener reagieren nur auf
# Aenderungen: Stehen Magnete/Pumpen schon beim Start auf EIN, oder setzt das Flugzeug
# beim Laden/Reset seine Vorgaben (Seneca: Magnete aus), kaeme sonst nichts an.
var alles_anwenden = func {
    foreach (var name; keys(SCHALTER))
        foreach (var ziel; SCHALTER[name])
            setprop(ziel, getprop(IN ~ name) ? 1 : 0);
    foreach (var nr; [0, 1])
        setze_funk_an(nr);
    foreach (var motor; [0, 1]) {
        setze_magnetos(motor);
        setze_anlasser(motor);
    }
    setze_tankwahl();
};

var main = func(addon) {
    foreach (var name; keys(SCHALTER)) {
        (func(name) {
            setlistener(IN ~ name, func(n) {
                foreach (var ziel; SCHALTER[name])
                    setprop(ziel, n.getValue() ? 1 : 0);
            }, 0, 0);
        })(name);
    }
    foreach (var motor; [0, 1]) {
        (func(motor) {
            setlistener(IN ~ "mag-" ~ motor ~ "-l", func setze_magnetos(motor), 0, 0);
            setlistener(IN ~ "mag-" ~ motor ~ "-r", func setze_magnetos(motor), 0, 0);
            setlistener(IN ~ "anlasser-" ~ motor, func setze_anlasser(motor), 0, 0);
            # Umkehrschub (nur mit Raste im Profil der Bruecke, z.B. fuer Duesen)
            setlistener(IN ~ "umkehr-" ~ motor, func(n) {
                setprop("/controls/engines/engine[" ~ motor ~ "]/reverser",
                        n.getValue() ? 1 : 0);
            }, 0, 0);
        })(motor);
    }
    setlistener(IN ~ "tankwahl", setze_tankwahl, 0, 0);
    # Parkbremse ist ein federnder Druckknopf: jeder Druck schaltet um
    setlistener(IN ~ "parkbremse", func(n) {
        if (n.getValue())
            setprop("/controls/gear/brake-parking", !getprop("/controls/gear/brake-parking"));
    }, 0, 0);
    # Klappentaster: jeder Druck = eine Stufe (+1 runter, -1 rauf)
    setlistener(IN ~ "klappen", func(n) {
        if (n.getValue() != 0)
            controls.flapsDown(n.getValue());
    }, 0, 0);

    # AP-3000: Zaehler beginnen in jeder Sitzung der Bruecke bei 0 (die Bruecke beginnt
    # auch nach einem FlightGear-Neustart eine neue Sitzung). "ap-sitzung" steht im
    # Paket vor den Zaehlern und ist hier also schon aktuell.
    foreach (var name; AP_ZAEHLER) {
        (func(name) {
            setlistener(IN ~ name, func(n) {
                var neu = n.getValue() or 0;
                var sitzung = getprop(IN ~ "ap-sitzung");
                var eintrag = contains(zaehler_alt, name) ? zaehler_alt[name] : nil;
                var alt = (eintrag != nil and eintrag[0] == sitzung) ? eintrag[1] : 0;
                zaehler_alt[name] = [sitzung, neu];
                var schritte = neu - alt;
                # grosse Spruenge = Bruecke neu gestartet, nicht anwenden
                if (schritte != 0 and math.abs(schritte) < 50)
                    ap_ereignis(name, schritte);
            }, 0, 0);
        })(name);
    }

    # Transponder-Modusschalter und IDENT-Taste
    setlistener(IN ~ "xpdr-modus", func(n) {
        if (n.getValue() >= 0)
            setprop("/instrumentation/transponder/inputs/knob-mode", n.getValue());
    }, 0, 0);
    # weisse Wippe: manuelle Trimmung des Century III (-1 rauf, 0, +1 runter)
    setlistener(IN ~ "ap-trimm", func(n) {
        setprop(AP ~ "manual-trim", n.getValue() or 0);
    }, 0, 0);
    # DME (Seneca KI266): 0 = aus, sonst Quelle 1 NAV1 / 2 eigene Frequenz / 3 NAV2
    setlistener(IN ~ "dme-quelle", func(n) {
        var quelle = n.getValue();
        if (quelle == nil or quelle < 0)
            return;
        setprop("/instrumentation/dme[0]/power-btn", quelle > 0);
        if (quelle > 0)
            setprop("/instrumentation/dme/switch-position", quelle);
    }, 0, 0);
    setlistener(IN ~ "sprechtaste", func(n) {
        # waehrend CWS gehoert "disconnect" dem CWS-Knopf
        if (cws_gemerkt == nil or n.getValue())
            setprop(AP ~ "disconnect", n.getValue() ? 1 : 0);
        if (n.getValue())
            cws_gemerkt = nil;  # AP aus heisst aus, auch nach CWS
    }, 0, 0);
    setlistener(IN ~ "cws", func(n) cws(n.getValue()), 0, 0);
    foreach (var nr; [0, 1]) {
        (func(nr) {
            setlistener(IN ~ "funk-an-" ~ nr, func setze_funk_an(nr), 0, 0);
        })(nr);
    }
    setlistener(IN ~ "xpdr-ident", func(n) {
        setprop("/instrumentation/transponder/inputs/ident-btn", n.getValue() ? 1 : 0);
    }, 0, 0);

    # Namensschilder im 2D-Panel; das Bedienfenster der Bruecke schaltet sie per httpd
    # (httpd schreibt nur in vorhandene Knoten)
    props.globals.initNode("/elite/beschriftung", 0, "BOOL");

    timer = maketimer(1 / 30, tick);
    timer.start();
    gps_start();
    # erst nach dem Laden der Ansichten, sonst ueberschreibt FlightGear sie wieder
    sitz_timer = maketimer(1, func {   # settimer() ist in Add-ons nicht erlaubt
        setze_sitzhoehe();
        # Tankwahl wie der Hardware-Schalter steht (nur wenn die Bruecke schon gemeldet hat)
        if (getprop(IN ~ "tankwahl") != nil)
            setze_tankwahl();
    });
    sitz_timer.singleShot = 1;
    # erst wenn das Flugzeug fertig geladen ist (auch nach Reset), sonst wird es ueberschrieben
    schalter_timer = maketimer(1, alles_anwenden);
    schalter_timer.singleShot = 1;
    setlistener("/sim/signals/fdm-initialized", func(n) {
        if (n.getBoolValue()) {
            sitz_timer.restart(1);
            schalter_timer.restart(2);   # nach den Vorgaben des Flugzeugs
        }
    }, 1, 0);
    gps_timer = maketimer(0.5, gps_lage);
    gps_timer.start();
    gps_umgebung_timer = maketimer(5, gps_umgebung);
    gps_umgebung_timer.start();
    adf_set_timer = maketimer(0.3, func setprop("/instrumentation/adf[0]/set-btn", 0));
    adf_set_timer.singleShot = 1;
    props.globals.initNode(BORD ~ "liste", 0, "INT");   # httpd schreibt nur in vorhandene Knoten
    bord_timer = maketimer(0.5, bord_werte);
    bord_timer.start();
    # Spannung aendert sich laufend -> zweimal pro Sekunde nachsehen
    licht_timer = maketimer(0.5, instrumentenlicht);
    licht_timer.start();
    logprint(LOG_INFO, "Elite Bruecke: Add-on geladen");
};

var unload = func(addon) {
    foreach (var t; [timer, gps_timer, gps_umgebung_timer, sitz_timer, schalter_timer,
                     bord_timer, adf_set_timer, licht_timer])
        if (t != nil)
            t.stop();
};
