import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from choir_audio import human_voice as hv
from choir_audio.musicxml import NoteEvent


def _sung_syllable(f0=200.0, dur=0.4, sr=22050, formant=700.0):
    t = np.arange(int(dur * sr)) / sr
    audio = np.zeros_like(t)
    for k in range(1, 25):
        audio += np.sin(2 * np.pi * k * f0 * t) / k
    audio += 0.3 * np.sin(2 * np.pi * formant * t) * np.exp(-t * 2)
    envelope = np.minimum(1.0, t / 0.05) * np.minimum(1.0, (dur - t) / 0.05)
    return audio * envelope * 0.5


def _prepared(audio, sr=22050):
    f0 = hv.estimate_f0(audio, sr)
    loop_start, loop_len = 0, 0
    if f0:
        loop = hv._extract_loop(audio, sr, f0)
        if loop:
            loop_start, loop_len = loop
    return hv.PreparedSyllable(audio, sr, f0, loop_start, loop_len)


def _spectral_peak(audio, sr, lo, hi):
    spec = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
    freqs = np.fft.rfftfreq(len(audio), 1.0 / sr)
    band = (freqs >= lo) & (freqs <= hi)
    if not band.any() or spec[band].max() <= 0:
        return None
    return float(freqs[band][np.argmax(spec[band])])


class TestEstimateF0(unittest.TestCase):
    def test_sine(self):
        sr = 22050
        t = np.arange(sr) / sr
        sine = 0.5 * np.sin(2 * np.pi * 200.0 * t)
        f0 = hv.estimate_f0(sine, sr)
        self.assertIsNotNone(f0)
        self.assertAlmostEqual(f0, 200.0, delta=5.0)

    def test_silence(self):
        f0 = hv.estimate_f0(np.zeros(44100), 44100)
        self.assertIsNone(f0)


class TestFitToNote(unittest.TestCase):
    def test_pitch_and_duration(self):
        prepared = _prepared(_sung_syllable())
        fitted = hv.fit_to_note(prepared, 44100, 330.0, 0.5)
        self.assertAlmostEqual(len(fitted) / 44100, 0.5, places=2)
        peak = _spectral_peak(fitted, 44100, 0.85 * 330.0, 1.2 * 330.0)
        self.assertIsNotNone(peak)
        self.assertAlmostEqual(peak, 330.0, delta=12.0)

    def test_pitch_down(self):
        prepared = _prepared(_sung_syllable(f0=200.0))
        fitted = hv.fit_to_note(prepared, 44100, 110.0, 0.6)
        peak = _spectral_peak(fitted, 44100, 90.0, 140.0)
        self.assertIsNotNone(peak)
        self.assertAlmostEqual(peak, 110.0, delta=8.0)

    def test_short_note(self):
        prepared = _prepared(_sung_syllable(dur=0.4))
        fitted = hv.fit_to_note(prepared, 44100, 262.0, 0.15)
        self.assertAlmostEqual(len(fitted) / 44100, 0.15, places=2)
        self.assertGreater(float(np.max(np.abs(fitted))), 0.05)

    def test_unvoiced_fallback(self):
        rng = np.random.default_rng(5)
        noise = (rng.standard_normal(22050) * 0.2).astype(np.float32)
        prepared = hv.PreparedSyllable(noise, 22050, None, 0, 0)
        fitted = hv.fit_to_note(prepared, 44100, 300.0, 0.4)
        self.assertAlmostEqual(len(fitted) / 44100, 0.4, places=2)
        self.assertGreater(float(np.max(np.abs(fitted))), 0.01)


class TestRenderHumanVocal(unittest.TestCase):
    class FakeVoice:
        sample_rate = 22050

        def __init__(self):
            self._prepared = _prepared(_sung_syllable())

        def prepare(self, text):
            return self._prepared

    def test_notes_are_placed(self):
        sr = 44100
        notes = [
            NoteEvent(0.0, 1.0, 67, "Sing"),
            NoteEvent(1.0, 1.0, 69, "get"),
        ]
        audio = hv.render_human_vocal(notes, 90.0, 2.0, sr, 440.0, self.FakeVoice())
        self.assertAlmostEqual(len(audio) / sr, 2.0 * 60.0 / 90.0, places=2)
        first = audio[: int(0.5 * sr)]
        second = audio[int(0.75 * sr): int(1.2 * sr)]
        self.assertGreater(float(np.max(np.abs(first))), 0.05)
        self.assertGreater(float(np.max(np.abs(second))), 0.05)

    def test_melisma_reuses_last_syllable(self):
        sr = 44100
        notes = [
            NoteEvent(0.0, 1.0, 67, "Sing"),
            NoteEvent(1.0, 1.0, 69, None),
        ]
        audio = hv.render_human_vocal(notes, 90.0, 2.0, sr, 440.0, self.FakeVoice())
        second = audio[int(0.75 * sr): int(1.25 * sr)]
        self.assertGreater(float(np.max(np.abs(second))), 0.05)


class TestPiperIntegration(unittest.TestCase):
    def setUp(self):
        self.model = hv.ensure_voice(hv.DEFAULT_VOICE, download=False)
        if not self.model or not hv.tts_available():
            self.skipTest("Piper oder Stimmenmodell nicht verfügbar")

    def test_real_syllable_pitch(self):
        voice = hv.HumanVoice(self.model)
        prepared = voice.prepare("Sing")
        self.assertIsNotNone(prepared)
        self.assertIsNotNone(prepared.f0)
        fitted = hv.fit_to_note(prepared, 44100, 262.0, 0.5)
        peak = _spectral_peak(fitted, 44100, 0.85 * 262.0, 1.2 * 262.0)
        self.assertIsNotNone(peak)
        self.assertAlmostEqual(peak, 262.0, delta=12.0)


if __name__ == "__main__":
    unittest.main()
