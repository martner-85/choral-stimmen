import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from choir_audio import midiio, render, synth

EXAMPLE = os.path.join(
    os.path.dirname(__file__), "..", "examples", "chorale.musicxml"
)


def _score():
    from choir_audio.musicxml import load_score

    return load_score(EXAMPLE)


class TestSynth(unittest.TestCase):
    def test_midi_to_freq(self):
        self.assertAlmostEqual(synth.midi_to_freq(69), 440.0, places=6)
        self.assertAlmostEqual(synth.midi_to_freq(60), 261.6256, places=3)

    def test_render_vocal(self):
        score = _score()
        audio = synth.render_vocal(score.parts[0].notes, 90.0, 16.0, vowel="a")
        self.assertEqual(len(audio), int(round(16.0 * 60.0 / 90.0 * 44100)))
        self.assertTrue(np.all(np.isfinite(audio)))
        self.assertGreater(np.max(np.abs(audio)), 0.01)

    def test_vowels_differ(self):
        score = _score()
        a = synth.render_vocal(score.parts[0].notes, 90.0, 16.0, vowel="a")
        u = synth.render_vocal(score.parts[0].notes, 90.0, 16.0, vowel="u")
        self.assertGreater(np.max(np.abs(a - u)), 0.01)

    def test_vocal_pitch_is_dominant(self):
        score = _score()
        options = render.RenderOptions(count_in=False, midi=False)
        data = render.render_all(score, options)["01 Sopran (Gesang solo).wav"]
        sr = options.sr
        seg = data[0 : int(2 * 60.0 / 90.0 * sr)]
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        freqs = np.fft.rfftfreq(len(seg), 1.0 / sr)
        peak = freqs[np.argmax(spec)]
        self.assertAlmostEqual(peak, synth.midi_to_freq(64), delta=5.0)

    def test_render_piano(self):
        score = _score()
        audio = synth.render_piano(score.parts[0].notes, 90.0, 16.0)
        self.assertTrue(np.all(np.isfinite(audio)))
        self.assertGreater(np.max(np.abs(audio)), 0.01)
        self.assertGreater(audio[-100:].std(), 0)

    def test_click_track(self):
        clicks = synth.click_track(8.0, 4.0, 120.0)
        self.assertEqual(len(clicks), int(round(4.0 * 44100)))
        self.assertGreater(np.max(np.abs(clicks)), 0.1)

    def test_normalize(self):
        data = synth.normalize(np.array([0.5, -0.25]))
        self.assertAlmostEqual(np.max(np.abs(data)), 0.89)


class TestRender(unittest.TestCase):
    def test_render_all_modes(self):
        options = render.RenderOptions(midi=False)
        outputs = render.render_all(_score(), options)
        names = sorted(outputs)
        self.assertEqual(len(names), 9)
        self.assertIn("00 Klavier (alle Stimmen).wav", names)
        self.assertIn("01 Sopran (Gesang solo).wav", names)
        self.assertIn("01 Sopran (Gesang + Klavier).wav", names)
        for data in outputs.values():
            self.assertLessEqual(np.max(np.abs(data)), 0.9)

    def test_accompaniment_is_quieter_than_voice(self):
        options = render.RenderOptions(midi=False)
        outputs = render.render_all(_score(), options)
        solo = outputs["01 Sopran (Gesang solo).wav"]
        with_acc = outputs["01 Sopran (Gesang + Klavier).wav"]
        tail = slice(int(3.2 * 44100), int(3.7 * 44100))
        self.assertGreater(
            np.sqrt(np.mean(with_acc[tail] ** 2)),
            np.sqrt(np.mean(solo[tail] ** 2)) * 0.99,
        )

    def test_tempo_scale_changes_length(self):
        fast = render.RenderOptions(tempo_scale=2.0, midi=False)
        slow = render.RenderOptions(tempo_scale=1.0, midi=False)
        self.assertLess(
            len(render.render_all(_score(), fast)["01 Sopran (Gesang solo).wav"]),
            len(render.render_all(_score(), slow)["01 Sopran (Gesang solo).wav"]),
        )

    def test_vowel_override(self):
        options = render.RenderOptions(vowel="u", midi=False)
        outputs = render.render_all(_score(), options)
        self.assertIn("01 Sopran (Gesang solo).wav", outputs)

    def test_write_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.wav")
            render.write_wav(path, np.array([0.0, 0.5, -0.5, 0.1]))
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(4), b"RIFF")


class TestMidi(unittest.TestCase):
    def test_write_midi_header(self):
        from choir_audio.musicxml import NoteEvent, VoicePart

        part = VoicePart(part_id="P1", part_name="Sopran", voice="1")
        part.notes = [NoteEvent(0.0, 4.0, 64)]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.mid")
            midiio.write_midi(path, part.notes, 90.0, count_in_beats=4.0)
            with open(path, "rb") as fh:
                data = fh.read()
        self.assertTrue(data.startswith(b"MThd"))
        self.assertIn(b"MTrk", data)


if __name__ == "__main__":
    unittest.main()
