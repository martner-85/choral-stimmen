import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from choir_audio.cli import main

EXAMPLE = os.path.join(
    os.path.dirname(__file__), "..", "examples", "chorale.musicxml"
)


class TestCli(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "audio")
            rc = main([EXAMPLE, "--out-dir", out_dir])
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
            rc = main([EXAMPLE, "--out-dir", out_dir, "--modes", "gesang-solo", "--no-midi"])
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
