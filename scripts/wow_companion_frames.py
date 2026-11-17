"""Candidate multi-frame AI question transport over the existing WoW 200-cell RGB strip.

A transport format, not an authorization or live screen-capture implementation.
Each chunk is encapsulated in the original 0xC7 0x1A frame/checksum layout.
The Bridge must capture *all* frames and independently verify a local session
before calling the provider. Packet checksums are NOT signatures.
"""
from __future__ import annotations

import json

MAGIC = b"\xc7\x1a"
MAX_CELLS = 200
MAX_FRAME_BYTES = 75
HEADER_BYTES = 8  # magic, numeric frame ID, payload length, 2 checksum bytes
MAX_PAYLOAD = MAX_FRAME_BYTES - HEADER_BYTES
PART_MARKER = 0xA1
PART_HEADER = 13  # marker + 8-byte session + 2-byte question ID + index + total
CHUNK_SIZE = MAX_PAYLOAD - PART_HEADER
MAX_PARTS = 16
MAX_QUESTION_BYTES = 500


class FrameError(ValueError):
    pass


def _checksum(body):
    a = b = 0
    for byte in body:
        a = (a + byte) % 255
        b = (b + a) % 255
    return bytes((a, b))


def encode_pixel_frame(frame_id: int, payload: bytes) -> list[int]:
    if type(frame_id) is not int or not 1 <= frame_id <= 65535:
        raise FrameError("INVALID_FRAME_ID")
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_PAYLOAD:
        raise FrameError("INVALID_FRAME_PAYLOAD")
    body = frame_id.to_bytes(2, "big") + len(payload).to_bytes(2, "big") + payload
    encoded = MAGIC + body + _checksum(body)
    bits = 0
    accumulator = 0
    cells = []
    for byte in encoded:
        accumulator = (accumulator << 8) | byte
        bits += 8
        while bits >= 3:
            bits -= 3
            cells.append((accumulator >> bits) & 7)
            accumulator &= (1 << bits) - 1
    if bits:
        cells.append((accumulator << (3 - bits)) & 7)
    if len(cells) > MAX_CELLS:
        raise FrameError("FRAME_EXCEEDS_STRIP")
    return cells


def decode_pixel_frame(cells: list[int]) -> tuple[int, bytes]:
    if not isinstance(cells, list) or not 1 <= len(cells) <= MAX_CELLS:
        raise FrameError("INVALID_CELL_COUNT")
    raw = bytearray()
    acc = count = 0
    expected = None
    for cell in cells:
        if type(cell) is not int or not 0 <= cell <= 7:
            raise FrameError("INVALID_PIXEL")
        acc = (acc << 3) | cell
        count += 3
        while count >= 8:
            count -= 8
            raw.append((acc >> count) & 255)
            acc &= (1 << count) - 1
            if len(raw) == 2 and raw != MAGIC:
                raise FrameError("INVALID_MAGIC")
            if len(raw) == 6:
                length = int.from_bytes(raw[4:6], "big")
                if not 1 <= length <= MAX_PAYLOAD:
                    raise FrameError("INVALID_LENGTH")
                expected = 8 + length
            if expected and len(raw) > expected:
                raise FrameError("TRAILING_DATA")
    if expected is None or len(raw) != expected or acc != 0:
        raise FrameError("INCOMPLETE_FRAME")
    body = bytes(raw[2:-2])
    if _checksum(body) != raw[-2:]:
        raise FrameError("BAD_CHECKSUM")
    return int.from_bytes(raw[2:4], "big"), bytes(raw[6:-2])


def encode_question(session: bytes, question_id: int, question: str) -> list[list[int]]:
    if not isinstance(session, bytes) or len(session) != 8:
        raise FrameError("INVALID_SESSION")
    if type(question_id) is not int or not 1 <= question_id <= 65535:
        raise FrameError("INVALID_QUESTION_ID")
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 500:
        raise FrameError("INVALID_QUESTION")
    if "|" in question or any(ord(ch) < 32 and ch not in "\t\n" for ch in question):
        raise FrameError("INVALID_QUESTION")
    data = question.strip().encode("utf-8")
    if len(data) > MAX_QUESTION_BYTES:
        raise FrameError("QUESTION_TOO_LONG_IN_BYTES")
    pieces = [data[i:i + CHUNK_SIZE] for i in range(0, len(data), CHUNK_SIZE)]
    if len(pieces) > MAX_PARTS:
        raise FrameError("TOO_MANY_PARTS")
    return [
        encode_pixel_frame(question_id, bytes((PART_MARKER,)) + session
                           + question_id.to_bytes(2, "big") + bytes((idx, len(pieces))) + piece)
        for idx, piece in enumerate(pieces)
    ]


def decode_question_frames(frames: list[list[int]]) -> dict:
    """All parts must be complete, ordered and from the same question/session."""
    if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_PARTS:
        raise FrameError("INVALID_FRAME_GROUP")
    parts = []
    session = question_id = total = None
    for idx, cells in enumerate(frames):
        frame_id, payload = decode_pixel_frame(cells)
        if len(payload) < PART_HEADER or payload[0] != PART_MARKER:
            raise FrameError("INVALID_PART")
        part_session = payload[1:9]
        part_id = int.from_bytes(payload[9:11], "big")
        part_idx, part_total = payload[11], payload[12]
        if not 1 <= part_total <= MAX_PARTS or part_idx != idx:
            raise FrameError("OUT_OF_ORDER")
        if idx == 0:
            session, question_id, total = part_session, part_id, part_total
        if part_session != session or part_id != question_id or frame_id != part_id or part_total != total:
            raise FrameError("MIXED_REQUEST")
        parts.append(payload[13:])
    if len(frames) != total:
        raise FrameError("INCOMPLETE_QUESTION")
    data = b"".join(parts)
    if not 1 <= len(data) <= MAX_QUESTION_BYTES:
        raise FrameError("INVALID_QUESTION_SIZE")
    try:
        question = data.decode("utf-8")
    except UnicodeError:
        raise FrameError("INVALID_UTF8") from None
    # Delegate meaning / policy validation to the existing typed ingress.
    from scripts.wow_companion_ingress import validate_question
    return validate_question({
        "action": "ai.ask", "session": session.hex(),
        "request_id": "ask-" + str(question_id), "question": question
    })
