from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

STEP_TO_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

DEFAULT_TEMPO_BPM = 100.0
DEFAULT_BEATS_PER_MEASURE = 4.0


@dataclass
class NoteEvent:
    onset: float
    duration: float
    midi: int


@dataclass
class VoicePart:
    part_id: str
    part_name: str
    voice: str
    notes: list[NoteEvent] = field(default_factory=list)
    guessed_voice: str | None = None

    @property
    def label(self) -> str:
        if self.guessed_voice:
            return f"{self.part_name} ({self.guessed_voice})"
        return self.part_name

    @property
    def end(self) -> float:
        if not self.notes:
            return 0.0
        return max(n.onset + n.duration for n in self.notes)


@dataclass
class Score:
    parts: list[VoicePart]
    tempo_bpm: float
    beats_per_measure: float


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(elem: ET.Element, name: str) -> ET.Element | None:
    for c in elem:
        if _local(c.tag) == name:
            return c
    return None


def _findtext(elem: ET.Element, path: str) -> str | None:
    cur = elem
    for name in path.split("/"):
        cur = _child(cur, name)
        if cur is None:
            return None
    return cur.text.strip() if cur.text else None


def _read_xml(path: str) -> bytes:
    if path.lower().endswith(".mxl"):
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            rootfile = None
            if "META-INF/container.xml" in names:
                container = ET.fromstring(zf.read("META-INF/container.xml"))
                for rf in container.iter():
                    if _local(rf.tag) == "rootfile" and rf.get("full-path"):
                        rootfile = rf.get("full-path")
                        break
            if rootfile is None:
                rootfile = next(
                    n for n in names
                    if n.lower().endswith((".xml", ".musicxml"))
                    and not n.startswith("META-INF/")
                )
            return zf.read(rootfile)
    with open(path, "rb") as fh:
        return fh.read()


def _pitch_to_midi(note: ET.Element) -> int | None:
    step_text = _findtext(note, "pitch/step")
    if step_text is None:
        return None
    step = STEP_TO_SEMITONE.get(step_text.upper())
    if step is None:
        return None
    octave = int(_findtext(note, "pitch/octave") or 4)
    alter = int(float(_findtext(note, "pitch/alter") or 0))
    return (octave + 1) * 12 + step + alter


def _guess_voice_from_range(notes: list[NoteEvent]) -> str | None:
    if not notes:
        return None
    midis = sorted(n.midi for n in notes)
    median = midis[len(midis) // 2]
    if median >= 62:
        return "Sopran"
    if median >= 55:
        return "Alt"
    if median >= 48:
        return "Tenor"
    return "Bass"


_GENERIC_NAME = ("part", "stimme", "voice", "p", "instrument")


def _is_generic_name(name: str) -> bool:
    lowered = name.strip().lower()
    if not lowered:
        return True
    parts = lowered.replace("-", " ").split()
    return parts[0] in _GENERIC_NAME


def load_score(path: str) -> Score:
    root = ET.fromstring(_read_xml(path))
    part_names: dict[str, str] = {}
    part_list = _child(root, "part-list")
    if part_list is not None:
        for sp in part_list:
            if _local(sp.tag) != "score-part":
                continue
            pid = sp.get("id") or ""
            name = _findtext(sp, "part-name") or pid
            part_names[pid] = name.strip()

    voices: dict[tuple[str, str], VoicePart] = {}
    order: list[tuple[str, str]] = []
    score_tempo = DEFAULT_TEMPO_BPM
    score_beats = DEFAULT_BEATS_PER_MEASURE

    for part in root:
        if _local(part.tag) != "part":
            continue
        part_id = part.get("id") or ""
        part_name = part_names.get(part_id, part_id or "Part")
        divisions = 1.0
        beats_per_measure = DEFAULT_BEATS_PER_MEASURE
        tempo_bpm: float | None = None
        cursor = 0.0
        prev_onset = 0.0
        open_ties: dict[tuple[str, int], NoteEvent] = {}

        for measure in part:
            if _local(measure.tag) != "measure":
                continue
            for elem in measure:
                tag = _local(elem.tag)
                if tag == "attributes":
                    div_text = _findtext(elem, "divisions")
                    if div_text:
                        divisions = float(div_text)
                    beats = _findtext(elem, "time/beats")
                    if beats:
                        beat_type = _findtext(elem, "time/beat-type") or "4"
                        beats_per_measure = 4.0 * float(beats) / float(beat_type)
                elif tag == "direction":
                    if tempo_bpm is None:
                        sound = _child(elem, "sound")
                        if sound is not None and sound.get("tempo"):
                            tempo_bpm = float(sound.get("tempo"))
                        else:
                            per_min = _findtext(elem, "metronome/per-minute")
                            if per_min:
                                try:
                                    tempo_bpm = float(per_min)
                                except ValueError:
                                    pass
                elif tag == "backup":
                    dur = float(_findtext(elem, "duration") or 0)
                    cursor -= dur / divisions
                elif tag == "forward":
                    dur = float(_findtext(elem, "duration") or 0)
                    cursor += dur / divisions
                elif tag == "note":
                    if _child(elem, "grace") is not None:
                        continue
                    dur_div = float(_findtext(elem, "duration") or 0)
                    dur_beats = dur_div / divisions
                    voice = _findtext(elem, "voice") or "1"
                    is_chord = _child(elem, "chord") is not None
                    if is_chord:
                        onset = prev_onset
                    else:
                        onset = cursor
                        prev_onset = onset
                        cursor += dur_beats
                    if _child(elem, "rest") is not None or dur_beats <= 0:
                        continue
                    midi = _pitch_to_midi(elem)
                    if midi is None:
                        continue

                    tie_types = {
                        t.get("type")
                        for t in elem
                        if _local(t.tag) == "tie" and t.get("type")
                    }
                    key = (voice, midi)
                    if "stop" in tie_types and key in open_ties:
                        held = open_ties[key]
                        held.duration = max(held.duration, onset + dur_beats - held.onset)
                        if "start" not in tie_types:
                            del open_ties[key]
                        continue

                    note_event = NoteEvent(onset=onset, duration=dur_beats, midi=midi)
                    vkey = (part_id, voice)
                    vp = voices.get(vkey)
                    if vp is None:
                        vp = VoicePart(part_id=part_id, part_name=part_name, voice=voice)
                        voices[vkey] = vp
                        order.append(vkey)
                    vp.notes.append(note_event)
                    if "start" in tie_types:
                        open_ties[key] = note_event

        if tempo_bpm is not None:
            score_tempo = tempo_bpm
            score_beats = beats_per_measure

    parts = [voices[k] for k in order]
    for vp in parts:
        if _is_generic_name(vp.part_name):
            vp.guessed_voice = _guess_voice_from_range(vp.notes)
        vp.notes.sort(key=lambda n: (n.onset, n.midi))

    return Score(
        parts=parts,
        tempo_bpm=score_tempo if parts else DEFAULT_TEMPO_BPM,
        beats_per_measure=score_beats if parts else DEFAULT_BEATS_PER_MEASURE,
    )
