import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from choir_audio import playback, render


class TestPlayback(unittest.TestCase):
    def _snippet_wav(self, tmp):
        import numpy as np

        path = os.path.join(tmp, "test.wav")
        render.write_wav(path, np.zeros(1000))
        return path

    def test_missing_file(self):
        self.assertFalse(playback.play_wav("gibt_es_nicht.wav"))

    def test_no_player_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._snippet_wav(tmp)
            with mock.patch.object(playback.shutil, "which", return_value=None):
                self.assertFalse(playback.play_wav(path))

    def test_fake_player(self):
        with tempfile.TemporaryDirectory() as tmp:
            player = os.path.join(tmp, "fakeplayer")
            with open(player, "w") as fh:
                fh.write("#!/bin/sh\nexit 0\n")
            os.chmod(player, os.stat(player).st_mode | stat.S_IEXEC)
            path = self._snippet_wav(tmp)
            with mock.patch.object(
                playback.shutil, "which", side_effect=lambda name: player
            ):
                self.assertTrue(playback.play_wav(path))

    def test_failing_player(self):
        with tempfile.TemporaryDirectory() as tmp:
            player = os.path.join(tmp, "fakeplayer")
            with open(player, "w") as fh:
                fh.write("#!/bin/sh\nexit 1\n")
            os.chmod(player, os.stat(player).st_mode | stat.S_IEXEC)
            path = self._snippet_wav(tmp)
            with mock.patch.object(
                playback.shutil, "which", side_effect=lambda name: player
            ):
                self.assertFalse(playback.play_wav(path))


if __name__ == "__main__":
    unittest.main()
