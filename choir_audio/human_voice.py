from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

import numpy as np

from .synth import beats_to_sec, midi_to_freq

DEFAULT_VOICE = "de_DE-thorsten-medium"

FEMALE_VOICE = "de_DE-kerstin-medium"
MALE_VOICE = "de_DE-thorsten-medium"

VOICE_FOR_TYPE = {
    "soprano": FEMALE_VOICE,
    "alto": FEMALE_VOICE,
    "tenor": MALE_VOICE,
    "bass": MALE_VOICE,
}

_MIN_NOTE_SEC = 0.12
_F0_MIN = 60.0
_F0_MAX = 500.0


def tts_available() -> bool:
    try:
        import piper

        return True
    except ImportError:
        return False


def voices_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".cache", "choir_audio", "piper")


def ensure_voice(name: str, download: bool = True) -> str | None:
    path = os.path.join(voices_dir(), name + ".onnx")
    if os.path.isfile(path):
        return path
    if not download or not tts_available():
        return None
    try:
        from piper.download_voices import download_voice

        os.makedirs(voices_dir(), exist_ok=True)
        download_voice(name, download_dir=pathlib.Path(voices_dir()))
    except Exception:
        return None
    return path if os.path.isfile(path) else None


@dataclass
class PreparedSyllable:
    audio: np.ndarray
    sample_rate: int
    f0: float | None
    loop_start: int
    loop_len: int


class HumanVoice:
    def __init__(self, model_path: str):
        from piper import PiperVoice

        self._voice = PiperVoice.load(model_path)
        self.sample_rate = int(self._voice.config.sample_rate)
        self._cache: dict[str, PreparedSyllable | None] = {}

    def prepare(self, text: str) -> PreparedSyllable | None:
        key = text.strip().lower()
        if key in self._cache:
            return self._cache[key]
        prepared = self._prepare(text.strip())
        self._cache[key] = prepared
        return prepared

    def _prepare(self, text: str) -> PreparedSyllable | None:
        if not text:
            return None
        try:
            chunks = list(self._voice.synthesize(text))
        except Exception:
            return None
        if not chunks:
            return None
        parts = [
            np.frombuffer(c.audio_int16_bytes, dtype=np.int16).astype(np.float32)
            / 32768.0
            for c in chunks
        ]
        audio = trim_silence(np.concatenate(parts), self.sample_rate)
        if audio.size == 0:
            return None
        f0 = estimate_f0(audio, self.sample_rate)
        loop_start, loop_len = 0, 0
        if f0 and _F0_MIN <= f0 <= _F0_MAX:
            loop = _extract_loop(audio, self.sample_rate, f0)
            if loop is not None:
                loop_start, loop_len = loop
        return PreparedSyllable(audio, self.sample_rate, f0, loop_start, loop_len)


_VOICE_CACHE: dict[str, HumanVoice | None] = {}


def get_human_voice(name: str = DEFAULT_VOICE) -> HumanVoice | None:
    if name in _VOICE_CACHE:
        return _VOICE_CACHE[name]
    voice = None
    if tts_available():
        model_path = ensure_voice(name)
        if model_path:
            try:
                voice = HumanVoice(model_path)
            except Exception:
                voice = None
    _VOICE_CACHE[name] = voice
    return voice


def trim_silence(audio: np.ndarray, sr: int, threshold: float = 0.01) -> np.ndarray:
    if audio.size == 0:
        return audio
    peak = float(np.max(np.abs(audio)))
    if peak <= 0:
        return audio
    indices = np.where(np.abs(audio) > threshold * peak)[0]
    if not len(indices):
        return audio
    pad = int(0.02 * sr)
    start = max(0, int(indices[0]) - pad)
    end = min(len(audio), int(indices[-1]) + pad)
    return audio[start:end].copy()


def estimate_f0(audio: np.ndarray, sr: int) -> float | None:
    frame = 1024
    hop = frame // 2
    lag_low = max(2, int(sr / _F0_MAX))
    lag_high = min(int(sr / _F0_MIN), frame - 1)
    if lag_high <= lag_low:
        return None
    estimates = []
    for start in range(0, len(audio) - frame, hop):
        seg = audio[start:start + frame]
        if float(np.sqrt(np.mean(seg ** 2))) < 0.02:
            continue
        seg = seg - seg.mean()
        corr = np.correlate(seg, seg, mode="full")[frame - 1:]
        lag = lag_low + int(np.argmax(corr[lag_low:lag_high]))
        if corr[lag] > 0.3 * corr[0]:
            estimates.append(sr / lag)
    if not estimates:
        return None
    return float(np.median(estimates))


def _extract_loop(audio: np.ndarray, sr: int, f0: float) -> tuple[int, int] | None:
    period = int(round(sr / f0))
    span = 2 * period
    if len(audio) < span + period:
        return None
    best_start = 0
    best_score = -1.0
    step = max(1, period // 2)
    for start in range(0, len(audio) - span, step):
        seg = audio[start:start + span]
        rms = float(np.sqrt(np.mean(seg ** 2)))
        p1 = seg[:period]
        p2 = seg[period:span]
        denom = float(np.sqrt(np.sum(p1 ** 2) * np.sum(p2 ** 2))) + 1e-12
        periodicity = float(np.sum(p1 * p2) / denom)
        score = rms * max(0.0, periodicity)
        if score > best_score:
            best_score = score
            best_start = start
    return best_start, span


def pitch_shift(audio: np.ndarray, factor: float) -> np.ndarray:
    if audio.size == 0 or abs(factor - 1.0) < 1e-3:
        return audio
    return _resample_linear(audio, 1.0 / factor)


def _resample_linear(audio: np.ndarray, ratio: float) -> np.ndarray:
    if audio.size == 0 or abs(ratio - 1.0) < 1e-3:
        return audio
    n_out = max(1, int(round(len(audio) * ratio)))
    idx = np.arange(n_out) / ratio
    idx0 = np.floor(idx).astype(int)
    frac = idx - idx0
    idx1 = np.minimum(idx0 + 1, len(audio) - 1)
    return audio[idx0] * (1.0 - frac) + audio[idx1] * frac


def resample_to(audio: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to or audio.size == 0:
        return audio
    return _resample_linear(audio, sr_to / sr_from)


def _loop_sustain(period: np.ndarray, target_len: int) -> np.ndarray:
    half_period = len(period) // 2
    if half_period < 2 or target_len <= 0:
        return np.zeros(max(0, target_len))
    grain = 2 * half_period
    period = period[:grain]
    window = np.hanning(grain)
    out = np.zeros(target_len + grain)
    norm = np.zeros(target_len + grain)
    pos = 0
    while pos < target_len:
        out[pos:pos + grain] += period * window
        norm[pos:pos + grain] += window
        pos += half_period
    norm[norm < 1e-6] = 1.0
    return out[:target_len] / norm[:target_len]


def _loop_extend(audio: np.ndarray, target_len: int, sr: int) -> np.ndarray:
    if audio.size == 0 or target_len <= 0:
        return audio[:target_len] if target_len > 0 else np.zeros(0)
    if target_len <= len(audio):
        return audio[:target_len]
    fade = max(1, min(int(0.015 * sr), len(audio) // 4))
    ramp = np.linspace(0.0, 1.0, fade)
    out = np.zeros(target_len)
    out[:len(audio)] = audio
    pos = len(audio) - fade
    while pos < target_len:
        end = min(target_len, pos + len(audio))
        chunk = audio[:end - pos]
        weight = np.ones(len(chunk))
        k = min(fade, len(chunk))
        weight[:k] *= ramp[:k]
        out[pos:end] += chunk * weight
        pos += len(audio) - fade
    return out


def fit_to_note(
    prepared: PreparedSyllable,
    target_sr: int,
    target_f0: float,
    target_dur_sec: float,
) -> np.ndarray:
    audio = prepared.audio
    n_target = max(1, int(round(target_dur_sec * target_sr)))
    factor = 1.0
    if prepared.f0 and prepared.f0 > 0:
        factor = float(np.clip(target_f0 / prepared.f0, 0.25, 4.0))

    if prepared.loop_len > 0:
        onset = pitch_shift(audio[:prepared.loop_start], factor)
        onset = resample_to(onset, prepared.sample_rate, target_sr)
        period = audio[prepared.loop_start:prepared.loop_start + prepared.loop_len]
        target_period_len = int(round(2.0 * target_sr / target_f0))
        period = _resample_linear(period, target_period_len / len(period))
        take = min(len(onset), n_target)
        out = np.zeros(n_target)
        out[:take] = onset[:take]
        if take < n_target:
            fade = max(1, min(int(0.015 * target_sr), take, n_target - take))
            start = take - fade
            sustain = _loop_sustain(period, n_target - start)
            weight = np.ones(len(sustain))
            k = min(fade, len(sustain))
            weight[:k] *= np.linspace(0.0, 1.0, k)
            out[start:start + len(sustain)] += sustain * weight
    else:
        shifted = pitch_shift(audio, factor)
        shifted = resample_to(shifted, prepared.sample_rate, target_sr)
        out = _loop_extend(shifted, n_target, target_sr)

    attack = max(1, min(int(0.015 * target_sr), n_target // 4))
    out[:attack] *= np.linspace(0.0, 1.0, attack)
    release = max(1, min(int(0.08 * target_sr), n_target // 3))
    out[-release:] *= np.linspace(1.0, 0.0, release)
    peak = float(np.max(np.abs(out)))
    if peak > 1.0:
        out = out * (0.9 / peak)
    return out


def render_human_vocal(
    notes,
    tempo_bpm: float,
    total_beats: float,
    sr: int,
    a4: float,
    voice: HumanVoice,
) -> np.ndarray:
    total_sec = beats_to_sec(total_beats, tempo_bpm)
    buf = np.zeros(int(round(total_sec * sr)) + sr // 5)
    last_prepared: PreparedSyllable | None = None
    for note in notes:
        target_dur = max(_MIN_NOTE_SEC, beats_to_sec(note.duration, tempo_bpm))
        prepared = None
        syllable = getattr(note, "syllable", None)
        if syllable:
            prepared = voice.prepare(syllable)
        if prepared is not None:
            last_prepared = prepared
        else:
            prepared = last_prepared
        if prepared is None:
            continue
        processed = fit_to_note(
            prepared,
            sr,
            midi_to_freq(note.midi, a4),
            target_dur,
        )
        start = int(round(beats_to_sec(note.onset, tempo_bpm) * sr))
        end = min(len(buf), start + len(processed))
        if end > start:
            buf[start:end] += processed[:end - start]
        if syllable:
            last_prepared = prepared
    return buf[:int(round(total_sec * sr))]
