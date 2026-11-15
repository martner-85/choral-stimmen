import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from choir_audio import playback, voices
from choir_audio.cli import main, resolve_uncertain_voices, _ask_voice
from choir_audio import render as render_mod
from choir_audio.musicxml import NoteEvent, Score, VoicePart

EXAMPLE = os.path.join(
    os.path.dirname(__file__), "..", "examples", "chorale.musicxml"
)


class TestCli(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "audio")
            rc = main([EXAMPLE, "--out-dir", out_dir, "--stimme", "synthetisch"])
            self.assertEqual(rc, 0)
            files = sorted(os.listdir(out_dir))
            wavs = [f for f in files if f.endswith(".wav")]
            mids = [f for f in files if f.endswith(".mid")]
            self.assertEqual(len(wavs), 9)
            self.assertEqual(len(mids), 4)
            self.assertIn("01 Sopran (Gesang solo).wav", wavs)
            self.assertIn("01 Sopran (Gesang + Klavier).wav", wavs)
            self.assertIn("00 Klavier (alle Stimmen).wav", wavs)
            self.assertIn("04 Bass (Gesang + Klavier).wav", wavs)
            self.assertTrue(
                all(
                    os.path.getsize(os.path.join(out_dir, f)) > 1000
                    for f in files
                    if f.endswith(".wav")
                )
            )
            self.assertTrue(
                all(
                    os.path.getsize(os.path.join(out_dir, f)) > 50
                    for f in files
                    if f.endswith(".mid")
                )
            )

    def test_modes_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "audio")
            rc = main([EXAMPLE, "--out-dir", out_dir, "--modes", "gesang-solo", "--no-midi", "--stimme", "synthetisch"])
            self.assertEqual(rc, 0)
            files = sorted(os.listdir(out_dir))
            self.assertEqual(
                files,
                [
                    "01 Sopran (Gesang solo).wav",
                    "02 Alt (Gesang solo).wav",
                    "03 Tenor (Gesang solo).wav",
                    "04 Bass (Gesang solo).wav",
                ],
            )

    def test_missing_file(self):
        self.assertEqual(main(["gibt_es_nicht.musicxml"]), 2)

    def test_ask_voice_answers(self):
        answers = iter(["s", " alt ", "T", "b", "x", "sopran"])
        out = []
        ask = lambda prompt: next(answers)
        self.assertEqual(_ask_voice(ask, out.append), "Sopran")
        self.assertEqual(_ask_voice(ask, out.append), "Alt")
        self.assertEqual(_ask_voice(ask, out.append), "Tenor")
        self.assertEqual(_ask_voice(ask, out.append), "Bass")
        self.assertEqual(_ask_voice(ask, out.append), "Sopran")

    def test_ask_voice_skip_and_invalid(self):
        answers = iter(["", "weiter", "q", "t"])
        out = []
        ask = lambda prompt: next(answers)
        self.assertIsNone(_ask_voice(ask, out.append))
        self.assertIsNone(_ask_voice(ask, out.append))
        self.assertEqual(_ask_voice(ask, out.append), "Tenor")

    def test_ask_voice_eof(self):
        def ask(prompt):
            raise EOFError()

        self.assertIsNone(_ask_voice(ask, lambda text: None))

    def test_resolve_uncertain_voices(self):
        uncertain = VoicePart(part_id="P2", part_name="Voice", voice="1")
        uncertain.notes = [NoteEvent(float(i), 1.0, m) for i, m in enumerate([64, 65, 67])]
        certain = VoicePart(part_id="P1", part_name="Sopran", voice="1")
        certain.notes = [NoteEvent(0.0, 1.0, 72)]
        score = Score(parts=[certain, uncertain], tempo_bpm=100.0, beats_per_measure=4.0)
        options = render_mod.RenderOptions()
        answers = iter(["t"])
        played = []

        def fake_play(path):
            played.append(os.path.isfile(path))
            return True

        resolve_uncertain_voices(
            score,
            options,
            input_fn=lambda prompt: next(answers),
            play_fn=fake_play,
            out=lambda text: None,
        )
        self.assertEqual(played, [True])
        self.assertEqual(uncertain.guessed_voice, "Tenor")
        self.assertEqual(voices.detect_voice_type(uncertain), "tenor")
        self.assertEqual(certain.guessed_voice, None)

    def test_resolve_skips_when_no_answer(self):
        uncertain = VoicePart(part_id="P1", part_name="Voice", voice="1")
        uncertain.notes = [NoteEvent(float(i), 1.0, m) for i, m in enumerate([64, 65, 67])]
        score = Score(parts=[uncertain], tempo_bpm=100.0, beats_per_measure=4.0)
        resolve_uncertain_voices(
            score,
            render_mod.RenderOptions(),
            input_fn=lambda prompt: "",
            play_fn=lambda path: True,
            out=lambda text: None,
        )
        self.assertIsNone(uncertain.guessed_voice)

    def test_end_to_end_human_voice(self):
        from choir_audio import human_voice

        model = human_voice.ensure_voice(human_voice.DEFAULT_VOICE, download=False)
        if not model or not human_voice.tts_available():
            self.skipTest("Piper oder Stimmenmodell nicht verfügbar")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "audio")
            rc = main([EXAMPLE, "--out-dir", out_dir, "--stimme", "menschlich"])
            self.assertEqual(rc, 0)
            wavs = [f for f in os.listdir(out_dir) if f.endswith(".wav")]
            self.assertEqual(len(wavs), 9)
            self.assertTrue(
                all(
                    os.path.getsize(os.path.join(out_dir, f)) > 1000
                    for f in wavs
                )
            )

    def test_module_entry(self):
        result = subprocess.run(
            [sys.executable, "-m", "choir_audio", "--help"],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("MusicXML", result.stdout)


if __name__ == "__main__":
    unittest.main()
