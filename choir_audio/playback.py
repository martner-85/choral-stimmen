from __future__ import annotations

import os
import shutil
import subprocess
import sys

_PLAYERS_LINUX = ("paplay", "ffplay", "aplay", "play")


def play_wav(path: str, timeout_sec: float = 120.0) -> bool:
    if not os.path.isfile(path):
        return False
    if sys.platform.startswith("win"):
        try:
            os.startfile(path)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        if shutil.which("afplay"):
            return _run(["afplay", path], timeout_sec)
        return False
    for player in _PLAYERS_LINUX:
        resolved = shutil.which(player)
        if resolved:
            command = [resolved, path]
            if player == "ffplay":
                command = [
                    resolved,
                    "-nodisp",
                    "-autoexit",
                    "-loglevel",
                    "quiet",
                    path,
                ]
            return _run(command, timeout_sec)
    return False


def _run(command: list[str], timeout_sec: float) -> bool:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_sec,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
