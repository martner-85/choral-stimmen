from __future__ import annotations

import re
from dataclasses import replace

from .musicxml import NoteEvent, Score, VoicePart

VOICE_TYPES = ("soprano", "alto", "tenor", "bass")

VOICE_RANGES = {
    "soprano": (60, 81),
    "alto": (55, 74),
    "tenor": (48, 69),
    "bass": (40, 62),
}

VOICE_MEDIAN_MAX = {
    "soprano": 74,
    "alto": 67,
    "tenor": 62,
    "bass": 55,
}

VOICE_FORMANT_SHIFT = {
    "soprano": 1.12,
    "alto": 1.03,
    "tenor": 0.88,
    "bass": 0.80,
}

VOICE_DEFAULT_VOWEL = {
    "soprano": "a",
    "alto": "o",
    "tenor": "e",
    "bass": "u",
}

_VOICE_NAME_PATTERNS = {
    "soprano": ("sopran", "soprano", "discant", "s"),
    "alto": ("alt", "alto", "viola", "a"),
    "tenor": ("tenor", "tenore", "t"),
    "bass": ("bass", "baß", "bariton", "baritone", "b"),
}

_VOWEL_CHARS = "aeiouäöü"
_DIPHTHONGS = {
    "ei": ("a", "e"),
    "ai": ("a", "e"),
    "ay": ("a", "e"),
    "eu": ("o", "e"),
    "äu": ("o", "e"),
    "au": ("a", "u"),
    "ie": ("i",),
}

_PLOSIVES = set("pbtdkg")
_FRICATIVES = set("fvsßzwchx")


def detect_voice_type(part: VoicePart) -> str | None:
    name = (part.part_name or "").strip().lower()
    if name:
        first = re.split(r"[\s\-_0-9]+", name)[0]
        for voice_type, patterns in _VOICE_NAME_PATTERNS.items():
            if name in patterns or first in patterns:
                return voice_type
    if part.guessed_voice:
        guessed = part.guessed_voice.lower()
        mapping = {"sopran": "soprano", "alt": "alto", "tenor": "tenor", "bass": "bass"}
        for key, value in mapping.items():
            if guessed.startswith(key):
                return value
    return None


def fit_octaves(notes: list[NoteEvent], voice_type: str) -> list[NoteEvent]:
    if not notes or voice_type not in VOICE_RANGES:
        return list(notes)
    low, high = VOICE_RANGES[voice_type]
    median_max = VOICE_MEDIAN_MAX[voice_type]
    midis = sorted(n.midi for n in notes)
    median = midis[len(midis) // 2]
    shift = 0
    while median + shift > median_max and median + shift - 12 >= low:
        shift -= 12
    while median + shift < low:
        shift += 12
    if shift == 0:
        return list(notes)
    return [replace(n, midi=n.midi + shift) for n in notes]


def apply_voice_ranges(score: Score) -> Score:
    parts = []
    for part in score.parts:
        voice_type = detect_voice_type(part)
        if voice_type is None:
            parts.append(part)
            continue
        fitted = fit_octaves(part.notes, voice_type)
        parts.append(replace(part, notes=fitted))
    return Score(
        parts=parts,
        tempo_bpm=score.tempo_bpm,
        beats_per_measure=score.beats_per_measure,
    )


def syllable_to_vowels(syllable: str) -> list[str]:
    text = syllable.lower().replace("é", "e").replace("è", "e")
    vowels: list[str] = []
    i = 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair in _DIPHTHONGS:
            vowels.extend(_DIPHTHONGS[pair])
            i += 2
            continue
        ch = text[i]
        if ch in _VOWEL_CHARS:
            if ch == "ä":
                vowels.append("e")
            elif ch == "ö":
                vowels.append("ö")
            elif ch == "ü":
                vowels.append("ü")
            else:
                vowels.append(ch)
        i += 1
    return vowels or ["a"]


def onset_consonant(syllable: str | None) -> str | None:
    if not syllable:
        return None
    text = syllable.lower()
    for ch in text:
        if ch in _PLOSIVES:
            return "plosiv"
        if ch in _FRICATIVES:
            return "frikativ"
        if ch in _VOWEL_CHARS:
            return None
    return None


def split_syllables(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-zÄÖÜäöüß']+", text)
    return [t for t in tokens if any(ch.lower() in _VOWEL_CHARS for ch in t)]
