import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from choir_audio import voices
from choir_audio.musicxml import NoteEvent, Score, VoicePart


def _part(name, midis, guessed=None):
    part = VoicePart(part_id="P1", part_name=name, voice="1")
    part.guessed_voice = guessed
    part.notes = [NoteEvent(float(i), 1.0, m) for i, m in enumerate(midis)]
    return part


class TestDetectVoiceType(unittest.TestCase):
    def test_german_names(self):
        self.assertEqual(voices.detect_voice_type(_part("Sopran", [64])), "soprano")
        self.assertEqual(voices.detect_voice_type(_part("Alt", [60])), "alto")
        self.assertEqual(voices.detect_voice_type(_part("Tenor", [55])), "tenor")
        self.assertEqual(voices.detect_voice_type(_part("Bass", [48])), "bass")

    def test_english_and_short_names(self):
        self.assertEqual(voices.detect_voice_type(_part("Soprano", [64])), "soprano")
        self.assertEqual(voices.detect_voice_type(_part("Alto", [60])), "alto")
        self.assertEqual(voices.detect_voice_type(_part("B", [48])), "bass")

    def test_range_guess_fallback(self):
        self.assertEqual(
            voices.detect_voice_type(_part("Voice", [64], guessed="Sopran")),
            "soprano",
        )
        self.assertIsNone(voices.detect_voice_type(_part("Voice", [64])))


class TestFitOctaves(unittest.TestCase):
    def test_tenor_misread_octave_shifted_down(self):
        notes = [NoteEvent(float(i), 4.0, m) for i, m in enumerate([67, 69, 65, 67])]
        fitted = voices.fit_octaves(notes, "tenor")
        self.assertEqual([n.midi for n in fitted], [55, 57, 53, 55])

    def test_correct_range_untouched(self):
        notes = [NoteEvent(float(i), 4.0, m) for i, m in enumerate([60, 62, 64, 62])]
        fitted = voices.fit_octaves(notes, "alto")
        self.assertEqual([n.midi for n in fitted], [60, 62, 64, 62])

    def test_too_low_shifted_up(self):
        notes = [NoteEvent(float(i), 4.0, m) for i, m in enumerate([36, 38, 40, 36])]
        fitted = voices.fit_octaves(notes, "bass")
        self.assertEqual([n.midi for n in fitted], [48, 50, 52, 48])

    def test_in_range_untouched(self):
        notes = [NoteEvent(float(i), 4.0, m) for i, m in enumerate([45, 47, 48, 45])]
        fitted = voices.fit_octaves(notes, "bass")
        self.assertEqual([n.midi for n in fitted], [45, 47, 48, 45])

    def test_apply_voice_ranges_keeps_unknown(self):
        part = _part("Sopran", [64, 65, 62, 64])
        score = Score(parts=[part], tempo_bpm=90.0, beats_per_measure=4.0)
        adjusted = voices.apply_voice_ranges(score)
        self.assertEqual([n.midi for n in adjusted.parts[0].notes], [64, 65, 62, 64])


class TestSyllables(unittest.TestCase):
    def test_simple_vowels(self):
        self.assertEqual(voices.syllable_to_vowels("Herrn"), ["e"])
        self.assertEqual(voices.syllable_to_vowels("dem"), ["e"])
        self.assertEqual(voices.syllable_to_vowels("Bus"), ["u"])

    def test_diphthongs(self):
        self.assertEqual(voices.syllable_to_vowels("eins"), ["a", "e"])
        self.assertEqual(voices.syllable_to_vowels("Haus"), ["a", "u"])
        self.assertEqual(voices.syllable_to_vowels("Freund"), ["o", "e"])

    def test_umlauts(self):
        self.assertEqual(voices.syllable_to_vowels("spät"), ["e"])
        self.assertEqual(voices.syllable_to_vowels("schön"), ["ö"])
        self.assertEqual(voices.syllable_to_vowels("Tür"), ["ü"])

    def test_no_vowels_falls_back(self):
        self.assertEqual(voices.syllable_to_vowels("psst"), ["a"])

    def test_onset_consonants(self):
        self.assertEqual(voices.onset_consonant("Sin"), "frikativ")
        self.assertEqual(voices.onset_consonant("get"), "plosiv")
        self.assertEqual(voices.onset_consonant("dem"), "plosiv")
        self.assertEqual(voices.onset_consonant("Herrn"), "frikativ")
        self.assertEqual(voices.onset_consonant("Alt"), None)

    def test_split_syllables(self):
        self.assertEqual(voices.split_syllables("Sin-get dem Herrn"), ["Sin", "get", "dem", "Herrn"])
        self.assertEqual(voices.split_syllables("Hal-le-lu-jah"), ["Hal", "le", "lu", "jah"])
        self.assertEqual(voices.split_syllables("f"), [])


class TestLyricParsing(unittest.TestCase):
    def test_musicxml_lyrics_loaded(self):
        from choir_audio.musicxml import load_score

        score = load_score(
            os.path.join(
                os.path.dirname(__file__), "..", "examples", "chorale.musicxml"
            )
        )
        sopran = score.parts[0]
        self.assertEqual(
            [n.syllable for n in sopran.notes], ["Sin", "get", "dem", "Herrn"]
        )


if __name__ == "__main__":
    unittest.main()
