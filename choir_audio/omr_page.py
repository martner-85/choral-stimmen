from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile


def _has_letters(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


_NOISE_TOKENS = {
    "mf", "mp", "ff", "pp", "pf", "sf", "sfz", "fp",
    "cresc", "crescendo", "dim", "diminuendo", "rit", "rall",
    "tempo", "atempo", "dol", "dolce", "espr", "sim", "legato",
    "pno", "ped", "solo", "soli", "tutti", "unis", "div",
}


_VOWELS = set("aeiouäöüyAEIOUÄÖÜY")


def _is_lyric_token(text: str) -> bool:
    token = text.strip()
    if not token:
        return False
    cleaned = _clean_syllable(token)
    if not cleaned:
        return False
    if len(cleaned) == 1:
        return cleaned in _VOWELS
    lowered = cleaned.lower()
    if lowered in _NOISE_TOKENS:
        return False
    if any(ch.isdigit() for ch in cleaned) or "=" in cleaned:
        return False
    if not all(ch.isalpha() or ch in "'’-" for ch in cleaned):
        return False
    return True


def _clean_syllable(text: str) -> str | None:
    token = text.strip().strip("-").strip(".,:;!?")
    if not token or not _has_letters(token):
        return None
    return token


def pdf_lyric_lines(pdf_path: str, page_index: int, dpi: int) -> list[list[str]]:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    page = doc[page_index]
    scale = dpi / 72.0
    tokens = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        if not _is_lyric_token(text):
            continue
        syllable = _clean_syllable(text)
        if syllable:
            tokens.append(
                ((y0 + y1) / 2.0 * scale, (x0 + x1) / 2.0 * scale, syllable)
            )
    doc.close()
    tokens.sort(key=lambda t: (t[0], t[1]))
    lines: list[list[str]] = []
    last_y: float | None = None
    for y, _x, syllable in tokens:
        if last_y is None or abs(y - last_y) > 14.0 * dpi / 200.0:
            lines.append([])
        lines[-1].append(syllable)
        last_y = y
    return lines


def ocr_lyric_lines(image_path: str) -> list[list[str]]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return []
    result, _ = RapidOCR()(image_path)
    tokens = []
    for box, text, _score in result or []:
        if not _is_lyric_token(text):
            continue
        syllable = _clean_syllable(text)
        if syllable:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            tokens.append(((min(ys) + max(ys)) / 2.0, sum(xs) / len(xs), syllable))
    tokens.sort(key=lambda t: (t[0], t[1]))
    lines: list[list[str]] = []
    last_y: float | None = None
    for y, _x, syllable in tokens:
        if last_y is None or abs(y - last_y) > 18.0:
            lines.append([])
        lines[-1].append(syllable)
        last_y = y
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="choir_audio.omr_page")
    parser.add_argument("bild", help="Gerasterte Seite (PNG)")
    parser.add_argument("ausgabe", help="Ausgabe-MusicXML")
    parser.add_argument("--lyrics", default="auto", choices=["auto", "aus"])
    parser.add_argument("--pdf", default=None, help="Original-PDF für die Textlage")
    parser.add_argument("--page-index", type=int, default=0)
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args(argv)

    from .omr import _run_homr

    with tempfile.TemporaryDirectory(prefix="choir_page_") as tmp:
        lokal = os.path.join(tmp, os.path.basename(args.bild))
        shutil.copyfile(args.bild, lokal)
        xml_path = _run_homr(lokal, tmp)
        shutil.copyfile(xml_path, args.ausgabe)

    lyric_lines: list[list[str]] = []
    if args.lyrics == "auto":
        if args.pdf and os.path.isfile(args.pdf):
            lyric_lines = pdf_lyric_lines(args.pdf, args.page_index, args.dpi)
        if not lyric_lines:
            lyric_lines = ocr_lyric_lines(args.bild)

    sidecar = args.ausgabe[:-8] + ".json" if args.ausgabe.endswith(".musicxml") else args.ausgabe + ".json"
    with open(sidecar, "w", encoding="utf-8") as fh:
        json.dump({"lyric_lines": lyric_lines}, fh, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
