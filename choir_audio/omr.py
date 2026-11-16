from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import numpy as np

from .musicxml import (
    NoteEvent,
    Score,
    VoicePart,
    guess_generic_voices,
    load_score,
)
from .voices import split_syllables

HOMR_TIMEOUT_SEC = 900
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")
PDF_EXTENSIONS = (".pdf",)


class OmrError(RuntimeError):
    pass


def _run_homr(image_path: str, out_dir: str) -> str:
    try:
        result = subprocess.run(
            ["homr", os.path.abspath(image_path)],
            cwd=out_dir,
            capture_output=True,
            text=True,
            timeout=HOMR_TIMEOUT_SEC,
        )
    except FileNotFoundError as exc:
        raise OmrError(
            "Das Programm 'homr' wurde nicht gefunden. Bitte installieren: "
            "pip install homr (siehe README, Abschnitt PDF-Verarbeitung)."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise OmrError(
            f"Die Notenerkennung hat nach {HOMR_TIMEOUT_SEC} Sekunden nicht reagiert."
        ) from exc
    xml_files = [
        f for f in os.listdir(out_dir) if f.lower().endswith((".musicxml", ".xml"))
    ]
    if result.returncode != 0 or not xml_files:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        hint = detail[-1] if detail else "unbekannter Fehler"
        raise OmrError(f"Notenerkennung fehlgeschlagen: {hint}")
    return os.path.join(out_dir, xml_files[0])


def rasterize_pdf(pdf_path: str, out_dir: str, dpi: int = 200) -> list[str]:
    try:
        import pymupdf
    except ImportError as exc:
        raise OmrError(
            "Für die PDF-Verarbeitung wird 'pymupdf' benötigt: pip install pymupdf"
        ) from exc
    paths = []
    with pymupdf.open(pdf_path) as doc:
        for index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            path = os.path.join(out_dir, f"seite_{index:02d}.png")
            pix.save(path)
            paths.append(path)
    if not paths:
        raise OmrError("Die PDF-Datei enthält keine Seiten.")
    return paths


def merge_scores(scores: list[Score]) -> Score:
    if not scores:
        raise OmrError("Keine erkannten Noten zum Zusammenführen.")
    merged: list[VoicePart] = []
    for page_index, score in enumerate(scores):
        page_offset = max((p.end for p in merged), default=0.0)
        for index, part in enumerate(score.parts):
            notes = [
                NoteEvent(n.onset + page_offset, n.duration, n.midi, n.syllable)
                for n in part.notes
            ]
            if index < len(merged):
                merged[index].notes.extend(notes)
            else:
                merged.append(
                    VoicePart(
                        part_id=part.part_id or f"P{index + 1}",
                        part_name=part.part_name,
                        voice=part.voice,
                        notes=notes,
                        guessed_voice=part.guessed_voice,
                    )
                )
    merged_score = Score(
        parts=merged,
        tempo_bpm=scores[0].tempo_bpm,
        beats_per_measure=scores[0].beats_per_measure,
    )
    guess_generic_voices(merged_score)
    return merged_score


def detect_systems(image_path: str) -> list[tuple[int, int]]:
    from PIL import Image

    img = np.array(Image.open(image_path).convert("L"))
    height = img.shape[0]
    dark_fraction = (img < 128).mean(axis=1)
    rows = np.where(dark_fraction > 0.30)[0]
    if len(rows) == 0:
        return []
    bands: list[list[int]] = []
    start = prev = int(rows[0])
    for row in rows[1:]:
        row = int(row)
        if row - prev <= 3:
            prev = row
            continue
        bands.append((start, prev))
        start = prev = row
    bands.append((start, prev))
    thin = [
        (s, e) for s, e in bands if (e - s) <= max(8, int(0.004 * height))
    ]
    if len(thin) < 2:
        return []
    centers = [(s + e) / 2.0 for s, e in thin]
    diffs = np.diff(centers)
    typical = float(np.median(diffs)) if len(diffs) else 0.0
    if typical <= 0:
        return []
    systems: list[tuple[int, int]] = []
    sys_start = thin[0]
    sys_end = thin[0]
    for idx in range(1, len(thin)):
        if centers[idx] - centers[idx - 1] > 4.0 * typical:
            systems.append((sys_start[0], sys_end[1]))
            sys_start = thin[idx]
        sys_end = thin[idx]
    systems.append((sys_start[0], sys_end[1]))
    return systems


def _ocr_boxes(image_path: str) -> list[tuple[float, float, float, float, str]]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return []
    result, _ = RapidOCR()(image_path)
    boxes = []
    for box, text, score in result or []:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        boxes.append((min(xs), min(ys), max(xs), max(ys), text))
    return boxes


def attach_ocr_lyrics(score: Score, image_path: str) -> int:
    boxes = _ocr_boxes(image_path)
    if not boxes or not score.parts:
        return 0
    systems = detect_systems(image_path)
    if not systems:
        return 0
    if len(systems) >= 2:
        max_gap = max(
            systems[i + 1][0] - systems[i][0] for i in range(len(systems) - 1)
        )
    else:
        max_gap = 200.0
    last_bottom = systems[-1][1]
    per_system: dict[int, list[str]] = {}
    for x1, y1, x2, y2, text in boxes:
        if len(text.strip()) < 2:
            continue
        y_center = (y1 + y2) / 2.0
        if any(s_top <= y_center <= s_bottom for s_top, s_bottom in systems):
            continue
        if y_center > last_bottom + max_gap:
            continue
        owner = None
        for idx, (s_top, s_bottom) in enumerate(systems):
            if y_center > s_bottom:
                owner = idx
        if owner is None:
            continue
        per_system.setdefault(owner, []).extend(split_syllables(text))

    n_parts = len(score.parts)
    total = 0
    for part_index, part in enumerate(score.parts):
        syllables: list[str] = []
        for system_index in sorted(per_system):
            if system_index % n_parts == part_index:
                syllables.extend(per_system[system_index])
        for note, syllable in zip(part.notes, syllables):
            if note.syllable is None:
                note.syllable = syllable
                total += 1
    return total


def attach_lyric_lines(score: Score, lines: list[list[str]]) -> int:
    if not lines or not score.parts:
        return 0
    total = 0
    n_parts = len(score.parts)
    cursors = [0] * n_parts
    for line_index, syllables in enumerate(lines):
        part_index = line_index % n_parts
        part = score.parts[part_index]
        i = cursors[part_index]
        for syllable in syllables:
            while i < len(part.notes) and part.notes[i].syllable is not None:
                i += 1
            if i >= len(part.notes):
                break
            part.notes[i].syllable = syllable
            total += 1
            i += 1
        cursors[part_index] = i
    return total


def _run_page_isolated(
    page_png: str,
    out_dir: str,
    page_index: int,
    dpi: int,
    lyrics: str,
    pdf_path: str | None,
) -> tuple[str, list[list[str]]]:
    import json
    import sys

    xml_out = os.path.join(out_dir, f"seite_{page_index:02d}.musicxml")
    command = [
        sys.executable,
        "-m",
        "choir_audio.omr_page",
        page_png,
        xml_out,
        "--lyrics",
        lyrics,
        "--dpi",
        str(dpi),
    ]
    if pdf_path:
        command.extend(["--pdf", pdf_path, "--page-index", str(page_index)])
    result = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not os.path.isfile(xml_out):
        detail = (result.stderr or "").strip().splitlines()
        message = detail[-1] if detail else "unbekannter Fehler"
        raise OmrError(
            f"Notenerkennung auf Seite {page_index + 1} fehlgeschlagen: {message}"
        )
    lines: list[list[str]] = []
    sidecar = xml_out[:-8] + ".json" if xml_out.endswith(".musicxml") else xml_out + ".json"
    if os.path.isfile(sidecar):
        with open(sidecar, encoding="utf-8") as fh:
            lines = json.load(fh).get("lyric_lines", [])
        os.unlink(sidecar)
    return xml_out, lines


def load_any(path: str, dpi: int = 200, lyrics: str = "auto") -> Score:
    lower = path.lower()
    if lower.endswith(PDF_EXTENSIONS):
        with tempfile.TemporaryDirectory(prefix="choir_omr_") as tmp:
            pages = rasterize_pdf(path, tmp, dpi=dpi)
            scores = []
            for index, page in enumerate(pages):
                xml_out, lyric_lines = _run_page_isolated(
                    page, tmp, index, dpi, lyrics, path
                )
                page_score = load_score(xml_out)
                if lyrics == "auto":
                    attach_lyric_lines(page_score, lyric_lines)
                guess_generic_voices(page_score)
                scores.append(page_score)
            merged = merge_scores(scores)
            guess_generic_voices(merged)
            return merged
    if lower.endswith(IMAGE_EXTENSIONS):
        with tempfile.TemporaryDirectory(prefix="choir_omr_") as tmp:
            xml_out, lyric_lines = _run_page_isolated(
                path, tmp, 0, dpi, lyrics, None
            )
            image_score = load_score(xml_out)
            if lyrics == "auto":
                attach_lyric_lines(image_score, lyric_lines)
            guess_generic_voices(image_score)
            return image_score
    return load_score(path)


def homr_available() -> bool:
    return shutil.which("homr") is not None
