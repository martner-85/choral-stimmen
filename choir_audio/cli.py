from __future__ import annotations

import argparse
import os
import sys

from . import midiio, omr, render, voices


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="choir_audio",
        description=(
            "Erzeugt aus einer Notendatei (MusicXML/MXL oder PDF/Bild) je Stimme "
            "eine Gesangs-Audiodatei mit Klavierbegleitung als Lernunterstützung "
            "für Chorgruppen."
        ),
    )
    parser.add_argument(
        "eingabe",
        help="Notendatei (.musicxml, .xml, .mxl, .pdf oder Notenbild .png/.jpg)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Ausgabeordner (Standard: <Name der Eingabedatei>_audio)",
    )
    parser.add_argument(
        "--tempo-scale",
        type=float,
        default=1.0,
        help="Tempofaktor, z. B. 0.7 für 70 %% Tempo (Standard: 1.0)",
    )
    parser.add_argument(
        "--bpm",
        type=float,
        default=None,
        help="Tempo überschreiben (Schläge pro Minute)",
    )
    parser.add_argument(
        "--others-gain",
        type=float,
        default=0.35,
        help="Lautstärke der Klavierbegleitung der übrigen Stimmen (Standard: 0.35)",
    )
    parser.add_argument(
        "--vokal",
        default="auto",
        choices=["auto", "a", "e", "o", "u"],
        help="Vokal der Gesangssynthese; 'auto' wählt je Stimme a/o/e/u (Standard: auto)",
    )
    parser.add_argument(
        "--a4",
        type=float,
        default=440.0,
        help="Stimmton a1 in Hz (Standard: 440)",
    )
    parser.add_argument(
        "--omr-dpi",
        type=int,
        default=200,
        help="Auflösung beim Rastern von PDF-Seiten (Standard: 200)",
    )
    parser.add_argument(
        "--lage",
        default="auto",
        choices=["auto", "original"],
        help=(
            "'auto' passt die Oktave an die erkannte Stimmlage an (z. B. Tenor "
            "eine Oktave tiefer) und singt mit stimmtypischem Klang; "
            "'original' lässt die notierte Oktave unverändert. Standard: auto"
        ),
    )
    parser.add_argument(
        "--lyrics",
        default="auto",
        choices=["auto", "aus"],
        help=(
            "'auto' erkennt den Liedtext (Silben) und singt ihn: bei MusicXML "
            "aus den eingebetteten Lyrics, bei PDF/Bild per Texterkennung (OCR). "
            "Standard: auto"
        ),
    )
    parser.add_argument(
        "--no-count-in",
        action="store_true",
        help="Keinen Takt Zählimpuls voranstellen",
    )
    parser.add_argument(
        "--no-midi",
        action="store_true",
        help="Zusätzlich keine MIDI-Dateien je Stimme erzeugen",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["gesang-solo", "gesang-klavier", "klavier"],
        choices=["gesang-solo", "gesang-klavier", "klavier"],
        help=(
            "Welche Dateien erzeugt werden: gesang-solo (nur eigene Stimme), "
            "gesang-klavier (eigene Stimme gesungen, übrige als Klavier), "
            "klavier (eine Gesamtaufnahme nur mit Klavier). Standard: alle"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not os.path.isfile(args.eingabe):
        print(f"Fehler: Datei nicht gefunden: {args.eingabe}", file=sys.stderr)
        return 2

    lower = args.eingabe.lower()
    if lower.endswith((".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")):
        if not omr.homr_available():
            print(
                "Fehler: Für PDF-/Bild-Eingaben wird die Notenerkennung 'homr' "
                "benötigt. Installation: pip install homr",
                file=sys.stderr,
            )
            return 2
        print("Notenerkennung läuft (das kann je Seite einige Minuten dauern) ...")

    try:
        score = omr.load_any(args.eingabe, dpi=args.omr_dpi, lyrics=args.lyrics)
    except omr.OmrError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Fehler: Datei konnte nicht gelesen werden ({exc})", file=sys.stderr)
        return 2

    if not score.parts:
        print("Fehler: Keine Notenstimmen in der Datei gefunden.", file=sys.stderr)
        return 2

    if args.lage == "auto":
        score = voices.apply_voice_ranges(score)

    options = render.RenderOptions(
        tempo_scale=args.tempo_scale,
        bpm_override=args.bpm,
        a4=args.a4,
        count_in=not args.no_count_in,
        others_gain=args.others_gain,
        vowel=args.vokal,
        modes=tuple(args.modes),
        midi=not args.no_midi,
    )

    out_dir = args.out_dir or (
        os.path.splitext(os.path.abspath(args.eingabe))[0] + "_audio"
    )
    os.makedirs(out_dir, exist_ok=True)

    bpm = render.effective_tempo(score, options)
    count_in_beats = score.beats_per_measure if options.count_in else 0.0
    syllable_count = sum(
        1 for p in score.parts for n in p.notes if n.syllable
    )
    stimmlagen = []
    for part in score.parts:
        vt = voices.detect_voice_type(part)
        stimmlagen.append(
            {"soprano": "Sopran", "alto": "Alt", "tenor": "Tenor", "bass": "Bass"}.get(vt, "?")
        )
    print(
        f"Stimmen erkannt: {len(score.parts)} ({', '.join(stimmlagen)}) | "
        f"Tempo: {bpm:.0f} BPM | Silben: {syllable_count}"
    )

    for filename, data in render.render_all(score, options).items():
        render.write_wav(os.path.join(out_dir, filename), data, options.sr)
        print(f"  WAV  {filename}")

    if options.midi:
        for idx, part in enumerate(score.parts, start=1):
            midi_name = f"{idx:02d} {render._sanitize(part.label)}.mid"
            midiio.write_midi(
                os.path.join(out_dir, midi_name),
                part.notes,
                bpm,
                count_in_beats,
            )
            print(f"  MIDI {midi_name}")

    print(f"Fertig. Dateien in: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
