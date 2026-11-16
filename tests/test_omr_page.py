import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from choir_audio import omr
from choir_audio.omr_page import (
    _clean_syllable,
    _is_lyric_token,
    pdf_lyric_lines,
)
from choir_audio.musicxml import NoteEvent, Score, VoicePart


class TestLyricTokens(unittest.TestCase):
    def test_lyric_tokens_kept(self):
        self.assertTrue(_is_lyric_token("Christ"))
        self.assertTrue(_is_lyric_token("Sil-"))
        self.assertTrue(_is_lyric_token("ev'ry"))
        self.assertTrue(_is_lyric_token("i-day"))

    def test_noise_tokens_dropped(self):
        self.assertFalse(_is_lyric_token("mf"))
        self.assertFalse(_is_lyric_token("Pno."))
        self.assertFalse(_is_lyric_token("J=roo"))
        self.assertFalse(_is_lyric_token("12"))
        self.assertFalse(_is_lyric_token("_-------.......--_"))
        self.assertFalse(_is_lyric_token("t\\"))
        self.assertFalse(_is_lyric_token("-"))

    def test_clean_syllable(self):
        self.assertEqual(_clean_syllable("mas."), "mas")
        self.assertEqual(_clean_syllable("-Bellsl-"), "Bellsl")
        self.assertIsNone(_clean_syllable("--"))
        self.assertIsNone(_clean_syllable("..."))


class TestPdfLyricLines(unittest.TestCase):
    def test_lines_from_synthetic_pdf(self):
        import pymupdf

        path = os.path.join(tempfile.gettempdir(), "choir_test_textlage.pdf")
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 700), "Sil- ver Bells, sil- ver bells")
        page.insert_text((72, 720), "mf    Pno.  12")
        page.insert_text((72, 760), "It's Christ- mas time in the cit- y")
        doc.save(path)
        doc.close()
        try:
            lines = pdf_lyric_lines(path, 0, 200)
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0], ["Sil", "ver", "Bells", "sil", "ver", "bells"])
            self.assertEqual(
                lines[1],
                ["It's", "Christ", "mas", "time", "in", "the", "cit", "y"],
            )
        finally:
            os.unlink(path)


class TestAttachLyricLines(unittest.TestCase):
    def _score(self, n_parts):
        parts = []
        for i in range(n_parts):
            part = VoicePart(part_id=f"P{i+1}", part_name="Voice", voice="1")
            part.notes = [NoteEvent(float(j), 1.0, 60 + j) for j in range(4)]
            parts.append(part)
        return Score(parts=parts, tempo_bpm=90.0, beats_per_measure=4.0)

    def test_lines_assigned_cyclically(self):
        score = self._score(2)
        attached = omr.attach_lyric_lines(
            score, [["Sil", "ver"], ["Christ", "mas", "time"], ["in", "the"]]
        )
        self.assertEqual(attached, 7)
        self.assertEqual(
            [n.syllable for n in score.parts[0].notes],
            ["Sil", "ver", "in", "the"],
        )
        self.assertEqual(
            [n.syllable for n in score.parts[1].notes],
            ["Christ", "mas", "time", None],
        )

    def test_existing_syllables_kept(self):
        score = self._score(1)
        score.parts[0].notes[0].syllable = "fest"
        omr.attach_lyric_lines(score, [["Sil", "ver"]])
        self.assertEqual(score.parts[0].notes[0].syllable, "fest")
        self.assertEqual(score.parts[0].notes[1].syllable, "Sil")
        self.assertEqual(score.parts[0].notes[2].syllable, "ver")


if __name__ == "__main__":
    unittest.main()
