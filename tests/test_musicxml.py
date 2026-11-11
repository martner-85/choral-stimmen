import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from choir_audio.musicxml import Score, load_score, guess_generic_voices
from choir_audio.omr import merge_scores
from choir_audio.musicxml import NoteEvent, VoicePart

EXAMPLE = os.path.join(
    os.path.dirname(__file__), "..", "examples", "chorale.musicxml"
)

MULTI_VOICE = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Sopran/Alt</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>2</divisions>
        <time><beats>2</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration><voice>1</voice><type>quarter</type></note>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration><voice>1</voice><type>quarter</type></note>
      <backup><duration>4</duration></backup>
      <note><pitch><step>E</step><octave>4</octave></pitch><duration>2</duration><voice>2</voice><type>quarter</type></note>
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>2</duration><voice>2</voice><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""

TIED = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Test</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions></attributes>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>2</duration><voice>1</voice><type>half</type>
        <tie type="start"/></note>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>2</duration><voice>1</voice><type>half</type>
        <tie type="stop"/></note>
    </measure>
  </part>
</score-partwise>
"""


class TestMusicXml(unittest.TestCase):
    def test_loads_example_with_four_parts(self):
        score = load_score(EXAMPLE)
        self.assertEqual(len(score.parts), 4)
        self.assertEqual([p.part_name for p in score.parts], ["Sopran", "Alt", "Tenor", "Bass"])
        self.assertEqual(score.tempo_bpm, 90.0)
        self.assertEqual(score.beats_per_measure, 4.0)

    def test_example_notes(self):
        score = load_score(EXAMPLE)
        sopran = score.parts[0]
        self.assertEqual(len(sopran.notes), 4)
        self.assertEqual(sopran.notes[0].midi, 64)
        self.assertEqual(sopran.notes[0].duration, 4.0)
        self.assertEqual([n.midi for n in score.parts[3].notes], [48, 53, 43, 48])

    def test_multi_voice_split(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".musicxml", delete=False) as fh:
            fh.write(MULTI_VOICE)
            path = fh.name
        try:
            score = load_score(path)
            self.assertEqual(len(score.parts), 2)
            self.assertEqual(score.parts[0].voice, "1")
            self.assertEqual(score.parts[1].voice, "2")
            self.assertEqual(score.parts[0].notes[1].midi, 74)
            self.assertEqual(score.parts[1].notes[0].midi, 64)
        finally:
            os.unlink(path)

    def test_generic_four_parts_get_satb_order(self):
        parts = [
            VoicePart(part_id=f"P{i + 1}", part_name="Voice", voice="1")
            for i in range(4)
        ]
        for part, midi in zip(parts, (64, 60, 55, 48)):
            part.notes.append(NoteEvent(onset=0.0, duration=1.0, midi=midi))
        score = Score(parts=parts, tempo_bpm=100.0, beats_per_measure=4.0)
        guess_generic_voices(score)
        self.assertEqual(
            [p.guessed_voice for p in score.parts],
            ["Sopran", "Alt", "Tenor", "Bass"],
        )

    def test_generic_single_part_uses_range(self):
        part = VoicePart(part_id="P1", part_name="Voice", voice="1")
        part.notes.append(NoteEvent(onset=0.0, duration=1.0, midi=41))
        score = Score(parts=[part], tempo_bpm=100.0, beats_per_measure=4.0)
        guess_generic_voices(score)
        self.assertEqual(score.parts[0].guessed_voice, "Bass")

    def test_merge_preserves_voice_guess(self):
        def page_score():
            part = VoicePart(part_id="P1", part_name="Voice", voice="1")
            part.notes.append(NoteEvent(onset=0.0, duration=1.0, midi=55))
            return Score(parts=[part], tempo_bpm=100.0, beats_per_measure=4.0)

        merged = merge_scores([page_score(), page_score()])
        self.assertEqual(merged.parts[0].guessed_voice, "Alt")
        self.assertEqual(len(merged.parts[0].notes), 2)

    def test_tied_notes_merged(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".musicxml", delete=False) as fh:
            fh.write(TIED)
            path = fh.name
        try:
            score = load_score(path)
            self.assertEqual(len(score.parts[0].notes), 1)
            self.assertEqual(score.parts[0].notes[0].duration, 4.0)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
