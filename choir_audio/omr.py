from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from .musicxml import NoteEvent, Score, VoicePart, load_score

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
                NoteEvent(n.onset + page_offset, n.duration, n.midi)
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
                    )
                )
    return Score(
        parts=merged,
        tempo_bpm=scores[0].tempo_bpm,
        beats_per_measure=scores[0].beats_per_measure,
    )


def load_any(path: str, dpi: int = 200) -> Score:
    lower = path.lower()
    if lower.endswith(PDF_EXTENSIONS):
        with tempfile.TemporaryDirectory(prefix="choir_omr_") as tmp:
            pages = rasterize_pdf(path, tmp, dpi=dpi)
            scores = []
            for page in pages:
                xml_path = _run_homr(page, tmp)
                scores.append(load_score(xml_path))
            return merge_scores(scores)
    if lower.endswith(IMAGE_EXTENSIONS):
        with tempfile.TemporaryDirectory(prefix="choir_omr_") as tmp:
            xml_path = _run_homr(path, tmp)
            return load_score(xml_path)
    return load_score(path)


def homr_available() -> bool:
    return shutil.which("homr") is not None
