"""Bounded WoW pixel frame protocol; NO live bridge, authority or transport."""
from __future__ import annotations
import json

MAGIC = b"\xc7\x1a"
MAX_PAYLOAD = 512

class ProtocolError(ValueError):
    pass

def checksum(data: bytes) -> bytes:
    a = b = 0
    for item in data:
        a = (a + item) % 255
        b = (b + a) % 255
    return bytes([a, b])

def encode(request_id: int, payload: bytes) -> list[int]:
    if not 1 <= request_id <= 65535 or not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD:
        raise ProtocolError("invalid_frame")
    body = request_id.to_bytes(2, "big") + len(payload).to_bytes(2, "big") + payload
    packet = MAGIC + body + checksum(body)
    cells, accumulator, count = [], 0, 0
    for byte in packet:
        accumulator = (accumulator << 8) | byte
        count += 8
        while count >= 3:
            count -= 3
            cells.append((accumulator >> count) & 7)
            accumulator &= (1 << count) - 1
    if count:
        cells.append((accumulator << (3 - count)) & 7)
    return cells

def decode(cells: list[int]) -> tuple[int, bytes]:
    raw = bytearray()
    accumulator = count = 0
    for cell in cells:
        if type(cell) is not int or not 0 <= cell <= 7:
            raise ProtocolError("invalid_cell")
        accumulator = (accumulator << 3) | cell
        count += 3
        while count >= 8:
            count -= 8
            raw.append((accumulator >> count) & 255)
            accumulator &= (1 << count) - 1
            if len(raw) == 2 and bytes(raw) != MAGIC:
                raise ProtocolError("invalid_magic")
            if len(raw) == 6 and int.from_bytes(raw[4:6], "big") > MAX_PAYLOAD:
                raise ProtocolError("oversized_frame")
            if len(raw) >= 8:
                length = int.from_bytes(raw[4:6], "big")
                if len(raw) == 8 + length:
                    body = bytes(raw[2:6 + length])
                    if checksum(body) != bytes(raw[-2:]):
                        raise ProtocolError("checksum_failure")
                    return int.from_bytes(raw[2:4], "big"), bytes(raw[6:6 + length])
    raise ProtocolError("incomplete_frame")

def decode_request(cells: list[int]) -> tuple[int, str]:
    request_id, raw = decode(cells)
    try:
        request = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError("invalid_json") from exc
    if not isinstance(request, dict) or set(request) != {"action", "session"}:
        raise ProtocolError("invalid_request_shape")
    if request["action"] != "wow.control.status":
        raise ProtocolError("action_not_allowed")
    session = request["session"]
    if not isinstance(session, str) or not 8 <= len(session) <= 64 or not session.isascii() or not session.isalnum():
        raise ProtocolError("invalid_session")
    return request_id, session

class OfflineStatusGateway:
    """Protocol boundary only. A pixel strip is not Node/ONE authentication."""
    def __init__(self):
        self._seen = set()

    def accept(self, cells: list[int]) -> dict:
        request_id, session = decode_request(cells)
        key = (session, request_id)
        if key in self._seen:
            return {"status": "UNAVAILABLE", "reason": "ONE_NOT_BOUND", "duplicate": True}
        if len(self._seen) >= 128:
            self._seen.clear()
        self._seen.add(key)
        return {"status": "UNAVAILABLE", "reason": "ONE_NOT_BOUND", "duplicate": False}
