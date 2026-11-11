from __future__ import annotations

import numpy as np

SAMPLE_RATE = 44100

ATTACK_SEC = 0.025
RELEASE_SEC = 0.09

HARMONICS = ((1, 1.0), (2, 0.45), (3, 0.22), (4, 0.12), (5, 0.07), (6, 0.04))

VOWEL_FORMANTS = {
    "a": ((800.0, 80.0, 1.0), (1150.0, 90.0, 0.6), (2800.0, 120.0, 0.25)),
    "e": ((550.0, 80.0, 1.0), (1900.0, 120.0, 0.5), (2550.0, 140.0, 0.25)),
    "i": ((280.0, 60.0, 1.0), (2250.0, 110.0, 0.5), (2890.0, 140.0, 0.25)),
    "o": ((450.0, 70.0, 1.0), (850.0, 80.0, 0.55), (2830.0, 120.0, 0.2)),
    "u": ((325.0, 60.0, 1.0), (700.0, 90.0, 0.5), (2530.0, 140.0, 0.15)),
    "ö": ((370.0, 70.0, 1.0), (1900.0, 120.0, 0.35), (2500.0, 140.0, 0.2)),
    "ü": ((300.0, 60.0, 1.0), (1650.0, 120.0, 0.35), (2400.0, 140.0, 0.15)),
}

VIBRATO_HZ = 5.3
VIBRATO_DEPTH = 0.006


def midi_to_freq(midi: int, a4: float = 440.0) -> float:
    return a4 * 2.0 ** ((midi - 69) / 12.0)


def beats_to_sec(beats: float, tempo_bpm: float) -> float:
    return beats * 60.0 / tempo_bpm


def _envelope(n: int, sr: int) -> np.ndarray:
    env = np.ones(n)
    na = min(n, int(ATTACK_SEC * sr))
    if na > 0:
        env[:na] = np.linspace(0.0, 1.0, na)
    nr = min(n - na, int(RELEASE_SEC * sr))
    if nr > 0:
        env[n - nr:] *= np.linspace(1.0, 0.0, nr) ** 1.5
    return env


def _tone(freq: float, dur_sec: float, sr: int, a4: float) -> np.ndarray:
    n = int(round(dur_sec * sr))
    if n <= 0:
        return np.zeros(0)
    t = np.arange(n) / sr
    vib_depth = 0.005 * np.minimum(1.0, t / 0.25)
    f_inst = freq * (1.0 + vib_depth * np.sin(2.0 * np.pi * 5.2 * t))
    phase = 2.0 * np.pi * np.cumsum(f_inst) / sr
    wave = np.zeros(n)
    for k, amp in HARMONICS:
        wave += amp * np.sin(k * phase)
    env = _envelope(n, sr)
    decay = 0.85 + 0.15 * np.exp(-3.0 * t)
    return wave * env * decay * 0.3


def render_voice(
    notes,
    tempo_bpm: float,
    total_beats: float,
    sr: int = SAMPLE_RATE,
    a4: float = 440.0,
) -> np.ndarray:
    total_sec = beats_to_sec(total_beats, tempo_bpm)
    buf = np.zeros(int(round(total_sec * sr)) + sr // 10)
    for note in notes:
        freq = midi_to_freq(note.midi, a4)
        dur_sec = beats_to_sec(note.duration, tempo_bpm)
        tone = _tone(freq, dur_sec, sr, a4)
        start = int(round(beats_to_sec(note.onset, tempo_bpm) * sr))
        end = min(len(buf), start + len(tone))
        if end > start:
            buf[start:end] += tone[: end - start]
    return buf[: int(round(total_sec * sr))]


def _formant_gain(freqs: np.ndarray, vowel: str, shift: float) -> np.ndarray:
    gain = np.zeros_like(freqs)
    for f_center, bandwidth, amp in VOWEL_FORMANTS.get(vowel, VOWEL_FORMANTS["a"]):
        gain += amp * np.exp(-0.5 * ((freqs - f_center * shift) / bandwidth) ** 2)
    gain = np.maximum(gain, 0.02)
    return gain


def _vocal_tone(
    f0: float,
    dur_sec: float,
    sr: int,
    vowels: list[str],
    consonant: str | None,
    rng,
    formant_shift: float = 1.0,
) -> np.ndarray:
    n = int(round(dur_sec * sr))
    if n <= 0:
        return np.zeros(0)
    t = np.arange(n) / sr

    vib = (
        VIBRATO_DEPTH
        * np.sin(2.0 * np.pi * VIBRATO_HZ * t + rng.uniform(0.0, 2.0 * np.pi))
        * np.minimum(1.0, t / 0.35)
    )
    jitter_pts = rng.standard_normal(max(2, int(dur_sec / 0.05) + 2)) * 0.004
    jitter = np.interp(t, np.arange(len(jitter_pts)) * 0.05, jitter_pts)
    f_inst = f0 * (1.0 + vib + jitter)

    phase = 2.0 * np.pi * np.cumsum(f_inst) / sr
    k_max = max(1, min(60, int(0.5 * sr / f0)))
    source = np.zeros(n)
    for k in range(1, k_max + 1):
        source += np.sin(k * phase) / k
    breath = rng.standard_normal(n) * 0.012
    source = source + breath

    spec = np.fft.rfft(source)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)

    vowel_list = vowels or ["a"]
    filtered_layers = []
    for vowel in vowel_list:
        gain = _formant_gain(freqs, vowel, formant_shift)
        gain += 0.7 * np.exp(-0.5 * ((freqs - f0) / 70.0) ** 2)
        filtered_layers.append(np.fft.irfft(spec * gain, n))

    if len(filtered_layers) == 1:
        filtered = filtered_layers[0]
    else:
        filtered = np.zeros(n)
        fade = max(1, int(0.02 * sr))
        edges = [round(i * n / len(filtered_layers)) for i in range(len(filtered_layers) + 1)]
        for idx in range(len(filtered_layers)):
            start = max(0, edges[idx] - (fade if idx > 0 else 0))
            end = min(n, edges[idx + 1] + (fade if idx < len(filtered_layers) - 1 else 0))
            if end <= start:
                continue
            weight = np.ones(end - start)
            if idx > 0:
                ramp = np.linspace(0.0, 1.0, min(fade, end - start))
                weight[: len(ramp)] *= ramp
            if idx < len(filtered_layers) - 1:
                ramp = np.linspace(1.0, 0.0, min(fade, end - start))
                weight[-len(ramp):] *= ramp
            filtered[start:end] += filtered_layers[idx][start:end] * weight

    if consonant == "frikativ":
        n_cons = min(n, int(0.05 * sr))
        if n_cons > 0:
            tc = np.arange(n_cons) / sr
            noise = rng.standard_normal(n_cons)
            noise -= np.convolve(noise, np.ones(32) / 32, mode="same")
            filtered[:n_cons] = (
                filtered[:n_cons] * 0.2 + noise * np.exp(-tc * 40.0) * 0.35
            )
    elif consonant == "plosiv":
        n_gap = min(n, int(0.03 * sr))
        n_burst = min(n - n_gap, int(0.02 * sr))
        if n_gap > 0:
            filtered[:n_gap] *= 0.05
        if n_burst > 0:
            tb = np.arange(n_burst) / sr
            noise = rng.standard_normal(n_burst)
            filtered[n_gap:n_gap + n_burst] = (
                filtered[n_gap:n_gap + n_burst] * 0.4
                + noise * np.exp(-tb * 180.0) * 0.3
            )

    env = np.ones(n)
    na = min(n, int(0.08 * sr))
    if na > 0:
        env[:na] = 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / na)
    nr = min(n - na, int(0.12 * sr))
    if nr > 0:
        env[n - nr:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(nr) / nr)
    env *= 0.9 + 0.1 * np.exp(-t * 0.5)
    return filtered * env


def render_vocal(
    notes,
    tempo_bpm: float,
    total_beats: float,
    sr: int = SAMPLE_RATE,
    a4: float = 440.0,
    vowel: str = "a",
    voice_type: str | None = None,
    formant_shift: float | None = None,
) -> np.ndarray:
    from . import voices

    if formant_shift is None:
        formant_shift = voices.VOICE_FORMANT_SHIFT.get(voice_type, 1.0)
    total_sec = beats_to_sec(total_beats, tempo_bpm)
    buf = np.zeros(int(round(total_sec * sr)) + sr // 5)
    rng = np.random.default_rng(42)
    for note in notes:
        f0 = midi_to_freq(note.midi, a4)
        dur_sec = beats_to_sec(note.duration, tempo_bpm)
        syllable = getattr(note, "syllable", None)
        if syllable:
            note_vowels = voices.syllable_to_vowels(syllable)
            consonant = voices.onset_consonant(syllable)
        else:
            note_vowels = [vowel]
            consonant = None
        tone = _vocal_tone(f0, dur_sec, sr, note_vowels, consonant, rng, formant_shift)
        start = int(round(beats_to_sec(note.onset, tempo_bpm) * sr))
        end = min(len(buf), start + len(tone))
        if end > start:
            buf[start:end] += tone[: end - start]
    return buf[: int(round(total_sec * sr))]


def _piano_tone(f0: float, dur_sec: float, sr: int, rng) -> np.ndarray:
    n = int(round(dur_sec * sr))
    if n <= 0:
        return np.zeros(0)
    t = np.arange(n) / sr
    inharmonicity = 0.00015
    wave = np.zeros(n)
    k_max = max(1, min(12, int(0.45 * sr / f0)))
    for k in range(1, k_max + 1):
        f_k = k * f0 * np.sqrt(1.0 + inharmonicity * k * k)
        amp = (1.0 / k ** 1.3) * np.exp(-k * 0.25)
        decay = np.exp(-t * (0.9 + f0 / 900.0 + 0.9 * k))
        wave += amp * np.sin(2.0 * np.pi * f_k * t + rng.uniform(0.0, 2.0 * np.pi)) * decay
    nh = min(n, int(0.02 * sr))
    if nh > 0:
        th = np.arange(nh) / sr
        wave[:nh] += rng.standard_normal(nh) * np.exp(-th * 250.0) * 0.25
    na = min(n, int(0.006 * sr))
    if na > 0:
        wave[:na] *= np.linspace(0.0, 1.0, na)
    return wave * 0.35


def render_piano(
    notes,
    tempo_bpm: float,
    total_beats: float,
    sr: int = SAMPLE_RATE,
    a4: float = 440.0,
) -> np.ndarray:
    total_sec = beats_to_sec(total_beats, tempo_bpm)
    buf = np.zeros(int(round(total_sec * sr)) + sr // 5)
    rng = np.random.default_rng(7)
    for note in notes:
        f0 = midi_to_freq(note.midi, a4)
        dur_sec = beats_to_sec(note.duration, tempo_bpm)
        tone = _piano_tone(f0, dur_sec, sr, rng)
        start = int(round(beats_to_sec(note.onset, tempo_bpm) * sr))
        end = min(len(buf), start + len(tone))
        if end > start:
            buf[start:end] += tone[: end - start]
    return buf[: int(round(total_sec * sr))]


def click_track(
    total_beats: float,
    beats_per_measure: float,
    tempo_bpm: float,
    sr: int = SAMPLE_RATE,
) -> np.ndarray:
    total_sec = beats_to_sec(total_beats, tempo_bpm)
    buf = np.zeros(int(round(total_sec * sr)))
    beat_sec = 60.0 / tempo_bpm
    n_click = int(round(0.04 * sr))
    t = np.arange(n_click) / sr
    click_hi = np.sin(2.0 * np.pi * 1200.0 * t) * np.exp(-t * 90.0) * 0.6
    click_lo = np.sin(2.0 * np.pi * 800.0 * t) * np.exp(-t * 90.0) * 0.4
    beat = 0
    while beat < int(round(total_beats)):
        start = int(round(beat * beat_sec * sr))
        click = click_hi if beat % int(round(beats_per_measure)) == 0 else click_lo
        end = min(len(buf), start + len(click))
        if end > start:
            buf[start:end] += click[: end - start]
        beat += 1
    return buf


def normalize(data: np.ndarray, peak: float = 0.89) -> np.ndarray:
    maximum = np.max(np.abs(data)) if data.size else 0.0
    if maximum < 1e-9:
        return data
    return data * (peak / maximum)


def limit_peak(data: np.ndarray, peak: float = 0.89) -> np.ndarray:
    maximum = np.max(np.abs(data)) if data.size else 0.0
    if maximum <= peak:
        return data
    return data * (peak / maximum)
