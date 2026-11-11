# Chorstimmen-Audio-Generator (`choir_audio`)

Erzeugt aus einer Notendatei automatisch **je Stimme eine Gesangs-Audiodatei
mit Klavierbegleitung** – als Lernunterstützung für Chorgruppen. Die eigene
Stimme wird als menschlich klingende Singstimme (Vokalsynthese) erzeugt, die
übrigen Stimmen erscheinen leiser als Klavierbegleitung im Hintergrund.

## Funktionsweise

1. **Einlesen:**
   - MusicXML (`.musicxml`, `.xml`, `.mxl`) – Standard-Exportformat von
     MuseScore, Finale, Sibelius, Dorico & Co.
   - **PDF** und Notenbilder (`.png`, `.jpg`, …) – werden automatisch per
     Notenerkennung (OMR) in MusicXML umgewandelt (siehe unten).
2. **Stimmen trennen:** Jede Part wird als eigene Stimme behandelt; mehrere
   Stimmen innerhalb einer Part (z. B. S/A im Diskant- und T/B im Bass-System)
   werden automatisch getrennt. Fehlen Stimmnamen, werden sie aus der
   Tonlage geschätzt (Sopran/Alt/Tenor/Bass).
3. **Synthese:**
   - **Gesangsstimme:** Formant-Synthese (Kehlkopf-Quelle + Vokal-Formanten),
     mit Vibrato, Jitter und Atemrauschen – klingt wie ein gesungenes
     „Aah/Ooh/Eh/Uuh". Jede Stimme erhält standardmäßig einen eigenen Vokal,
     damit man sie akustisch gut unterscheiden kann.
   - **Klavierbegleitung:** additive Synthese mit inharmo­nischen Teiltönen,
     Hämmer-Geräusch und typischem Ausklang.
4. **Ausgabe pro Stimme:**
   - `<Stimme> (Gesang solo).wav` – nur die eigene Stimme gesungen
   - `<Stimme> (Gesang + Klavier).wav` – eigene Stimme laut gesungen,
     übrige Stimmen als leise Klavierbegleitung
   - `00 Klavier (alle Stimmen).wav` – der ganze Satz nur am Klavier
   - `<Stimme>.mid` – MIDI-Datei je Stimme (für DAW/Player)
   - vor jeder Datei liegt ein Takt Zählimpuls (Klick)

## Installation

```bash
pip install -r requirements.txt        # numpy + pymupdf (für PDFs)
pip install homr                       # Notenerkennung, nur für PDF/Bild nötig
```

Die OMR-Modelle von `homr` werden beim ersten Lauf automatisch geladen.

## Verwendung

```bash
# PDF verarbeiten: je Stimme Gesang solo + Gesang mit Klavierbegleitung
python -m choir_audio noten.pdf

# MusicXML, 70 % Tempo zum Üben
python -m choir_audio noten.musicxml --tempo-scale 0.7 --out-dir ueben

# Tempo fest vorgeben, ohne Zählimpuls, nur Solo-Dateien
python -m choir_audio noten.musicxml --bpm 80 --no-count-in --modes gesang-solo

# alle Stimmen mit demselben Vokal singen lassen
python -m choir_audio noten.pdf --vokal a
```

### Optionen

| Option | Bedeutung |
| --- | --- |
| `--out-dir` | Ausgabeordner (Standard: `<Dateiname>_audio`) |
| `--tempo-scale` | Tempofaktor, z. B. `0.7` (Standard `1.0`) |
| `--bpm` | Tempo überschreiben |
| `--others-gain` | Lautstärke der Klavierbegleitung der übrigen Stimmen (Standard `0.35`) |
| `--vokal` | Vokal der Gesangssynthese: `auto` (je Stimme a/o/e/u), `a`, `e`, `o`, `u` |
| `--a4` | Stimmton in Hz (Standard `440`) |
| `--omr-dpi` | Auflösung beim Rastern von PDF-Seiten (Standard `200`) |
| `--no-count-in` | ohne Zählimpuls-Takt |
| `--no-midi` | keine MIDI-Dateien erzeugen |
| `--modes` | `gesang-solo`, `gesang-klavier`, `klavier` (Standard: alle) |

## PDF-Verarbeitung (Notenerkennung)

PDFs und Scans werden Seite für Seite gerastert (`pymupdf`, `--omr-dpi`) und
mit dem Open-Source-OMR-System
[homr](https://github.com/liebharc/homr) (`pip install homr`) in MusicXML
umgewandelt. Mehrseitige PDFs werden automatisch zusammengeführt.

Hinweise:
- Die automatische Notenerkennung ist nicht fehlerfrei – besonders bei
  gescannten, schiefen oder dicht gesetzten Vorlagen. Kontrolliere die
  erzeugten MIDI-Dateien oder die Stimmenzahl im Log.
- Satzteile mit Oktav-Transpositionsschlüsseln (z. B. Tenor im
  Violinschlüssel mit 8) können eine Oktave zu hoch erkannt werden.
- Für verlässliche Ergebnisse ist MusicXML-Export aus dem Notensatzprogramm
  der PDF-Erkennung immer vorzuziehen.

## Beispiel

Im Ordner `examples/` liegen eine vierstimmige Chorale als MusicXML und als
PDF. Testlauf:

```bash
python -m choir_audio examples/chorale.musicxml
python -m choir_audio examples/chorale.pdf
```

Ergebnis: 9 WAV-Dateien (2 je Stimme plus Klaviergesamtaufnahme) und
4 MIDI-Dateien.

## Unterstützte Notensyntax (MusicXML)

- Einzelparts und mehrere Stimmen pro Part (`<voice>`)
- Verschiedene Taktarten, Tempoangaben (`<sound tempo>` / Metronom)
- übergebundene Noten (Ties), Akkorde, Pausen, Vorzeichen
- gepackte `.mxl`-Dateien

## Tests

```bash
python -m pytest tests
```

Der Integrationstest für die PDF-Erkennung läuft nur, wenn `homr`
installiert ist.
