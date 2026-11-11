import os
import shutil
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from choir_audio import omr
from choir_audio.musicxml import NoteEvent, Score, VoicePart, load_score

EXAMPLE_PDF = os.path.join(os.path.dirname(__file__), "..", "examples", "chorale.pdf")


def _score_with_notes(midi_values, start=0.0):
    part = VoicePart(part_id="P1", part_name="Sopran", voice="1")
    part.notes = [
        NoteEvent(start + i, 1.0, m) for i, m in enumerate(midi_values)
    ]
    return Score(parts=[part], tempo_bpm=90.0, beats_per_measure=4.0)


class TestMergeScores(unittest.TestCase):
    def test_merges_pages_with_offset(self):
        page1 = _score_with_notes([60, 62])
        page2 = _score_with_notes([64, 65])
        merged = omr.merge_scores([page1, page2])
        self.assertEqual(len(merged.parts), 1)
        self.assertEqual([n.midi for n in merged.parts[0].notes], [60, 62, 64, 65])
        self.assertEqual(merged.parts[0].notes[2].onset, 2.0)

    def test_new_part_on_later_page(self):
        page1 = _score_with_notes([60, 62])
        page2 = Score(
            parts=[
                VoicePart(
                    part_id="P1",
                    part_name="Sopran",
                    voice="1",
                    notes=[NoteEvent(0.0, 1.0, 64)],
                ),
                VoicePart(
                    part_id="P2",
                    part_name="Alt",
                    voice="1",
                    notes=[NoteEvent(0.0, 1.0, 55)],
                ),
            ],
            tempo_bpm=90.0,
            beats_per_measure=4.0,
        )
        merged = omr.merge_scores([page1, page2])
        self.assertEqual(len(merged.parts), 2)
        self.assertEqual(merged.parts[1].notes[0].onset, 2.0)
        self.assertEqual(merged.parts[0].notes[-1].onset, 2.0)

    def test_empty_raises(self):
        with self.assertRaises(omr.OmrError):
            omr.merge_scores([])


class TestLoadAny(unittest.TestCase):
    def test_musicxml_passthrough(self):
        score = omr.load_any(
            os.path.join(
                os.path.dirname(__file__), "..", "examples", "chorale.musicxml"
            )
        )
        self.assertEqual(len(score.parts), 4)

    def test_pdf_requires_homr(self):
        with mock.patch.object(omr, "homr_available", return_value=False), \
             mock.patch.object(omr, "_run_homr", side_effect=omr.OmrError("fehlt")):
            with self.assertRaises(omr.OmrError):
                omr.load_any(EXAMPLE_PDF)


@unittest.skipUnless(
    omr.homr_available() and os.path.isfile(EXAMPLE_PDF),
    "homr oder Beispieldatei nicht vorhanden",
)
class TestOmrIntegration(unittest.TestCase):
    def test_pdf_end_to_end(self):
        score = omr.load_any(EXAMPLE_PDF)
        self.assertGreaterEqual(len(score.parts), 4)
        total_notes = sum(len(p.notes) for p in score.parts)
        self.assertGreater(total_notes, 10)
        for part in score.parts:
            for note in part.notes:
                self.assertTrue(21 <= note.midi <= 108)


if __name__ == "__main__":
    unittest.main()
