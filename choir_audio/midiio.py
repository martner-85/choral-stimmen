from __future__ import annotations

import struct


TPQ = 480


def _varlen(value: int) -> bytes:
    value = max(0, int(value))
    buffer = value & 0x7F
    result = bytearray()
    while True:
        result.append(buffer)
        value >>= 7
        if value == 0:
            break
        buffer = (value & 0x7F) | 0x80
    return bytes(reversed(result))


def write_midi(
    path: str,
    notes,
    tempo_bpm: float,
    count_in_beats: float = 0.0,
    tpq: int = TPQ,
) -> None:
    events: list[tuple[int, int, bool]] = []
    for note in notes:
        on_tick = int(round((count_in_beats + note.onset) * tpq))
        off_tick = int(round((count_in_beats + note.onset + note.duration) * tpq))
        off_tick = max(off_tick, on_tick + 1)
        events.append((on_tick, note.midi, True))
        events.append((off_tick, note.midi, False))
    events.sort(key=lambda e: (e[0], e[2]))

    track = bytearray()
    us_per_quarter = int(round(60_000_000 / tempo_bpm))
    track += b"\x00\xff\x51\x03" + struct.pack(">I", us_per_quarter)[1:]
    track += b"\x00\xff\x58\x04" + bytes([4, 2, 24, 8])

    last_tick = 0
    for tick, midi, is_on in events:
        track += _varlen(tick - last_tick)
        status = 0x90 if is_on else 0x80
        track += bytes([status, max(0, min(127, midi)), 90 if is_on else 0])
        last_tick = tick
    track += _varlen(1) + b"\xff\x2f\x00"

    data = bytearray()
    data += b"MThd" + struct.pack(">IHHH", 6, 0, 1, tpq)
    data += b"MTrk" + struct.pack(">I", len(track)) + track
    with open(path, "wb") as fh:
        fh.write(bytes(data))
