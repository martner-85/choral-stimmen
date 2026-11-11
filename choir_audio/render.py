from __future__ import annotations

import os
import wave
from dataclasses import dataclass

import numpy as np

from . import synth
from .musicxml import Score, VoicePart

MODE_LABELS = {
    "gesang-solo": "Gesang solo",
    "gesang-klavier": "Gesang + Klavier",
}

AUTO_VOWELS = ("a", "o", "e", "u")

VOCAL_PEAK = 0.6
PIANO_PEAK = 0.5


@dataclass
class RenderOptions:
    tempo_scale: float = 1.0
    bpm_override: float | None = None
    a4: float = 440.0
    count_in: bool = True
    others_gain: float = 0.35
    vowel: str = "auto"
    modes: tuple[str, ...] = ("gesang-solo", "gesang-klavier", "klavier")
    midi: bool = True
    sr: int = synth.SAMPLE_RATE


def _sanitize(name: str) -> str:
    for ch in '\\/:*?"<>|+':
        name = name.replace(ch, "_")
    return name.strip() or "Stimme"


def effective_tempo(score: Score, options: RenderOptions) -> float:
    bpm = options.bpm_override if options.bpm_override else score.tempo_bpm
    return max(20.0, min(300.0, bpm * options.tempo_scale))


def total_beats_of(score: Score) -> float:
    from math import ceil

    end = max((p.end for p in score.parts), default=0.0)
    measure = score.beats_per_measure
    return max(measure, ceil(end / measure) * measure)


def vowel_for_part(index: int, options: RenderOptions) -> str:
    if options.vowel != "auto":
        return options.vowel
    return AUTO_VOWELS[index % len(AUTO_VOWELS)]


def _place(audio: np.ndarray, n_total: int, offset_sec: float, sr: int) -> np.ndarray:
    padded = np.zeros(n_total)
    start = int(round(offset_sec * sr))
    end = min(n_total, start + len(audio))
    if end > start:
        padded[start:end] = audio[: end - start]
    return padded


def render_all(score: Score, options: RenderOptions) -> dict[str, np.ndarray]:
    bpm = effective_tempo(score, options)
    total_beats = total_beats_of(score)
    count_in_beats = score.beats_per_measure if options.count_in else 0.0
    count_in_sec = synth.beats_to_sec(count_in_beats, bpm)
    total_sec = synth.beats_to_sec(total_beats + count_in_beats, bpm)
    n_total = int(round(total_sec * options.sr))

    vocal_audio: list[tuple[VoicePart, np.ndarray]] = []
    piano_audio: list[tuple[VoicePart, np.ndarray]] = []
    for index, part in enumerate(score.parts):
        vowel = vowel_for_part(index, options)
        vocal = synth.render_vocal(
            part.notes, bpm, total_beats, options.sr, options.a4, vowel
        )
        vocal = synth.normalize(vocal, VOCAL_PEAK)
        vocal_audio.append((part, _place(vocal, n_total, count_in_sec, options.sr)))

        piano = synth.render_piano(part.notes, bpm, total_beats, options.sr, options.a4)
        piano = synth.normalize(piano, PIANO_PEAK)
        piano_audio.append((part, _place(piano, n_total, count_in_sec, options.sr)))

    clicks = synth.click_track(
        count_in_beats if options.count_in else 0.0,
        score.beats_per_measure,
        bpm,
        options.sr,
    )

    def with_clicks(mix: np.ndarray) -> np.ndarray:
        if options.count_in and len(clicks) == len(mix):
            return mix + clicks
        return mix

    outputs: dict[str, np.ndarray] = {}
    n_voices = len(vocal_audio)
    for index, (part, vocal) in enumerate(vocal_audio, start=1):
        label = _sanitize(part.label)
        for mode in options.modes:
            if mode == "gesang-solo":
                mix = vocal.copy()
            elif mode == "gesang-klavier":
                mix = vocal.copy()
                for other, piano in piano_audio:
                    if other is not part:
                        mix = mix + options.others_gain * piano
            else:
                continue
            outputs[f"{index:02d} {label} ({MODE_LABELS[mode]}).wav"] = synth.limit_peak(
                with_clicks(mix)
            )

    if "klavier" in options.modes:
        mix = sum(p for _, p in piano_audio)
        if n_voices > 1:
            mix = mix / np.sqrt(n_voices)
        outputs["00 Klavier (alle Stimmen).wav"] = synth.limit_peak(with_clicks(mix))

    return outputs


def write_wav(path: str, data: np.ndarray, sr: int = synth.SAMPLE_RATE) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    pcm = np.clip(data, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
