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
    for consumed_index, cell in enumerate(cells):
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
                    # A screen capture may pad the final frame with zero cells.
                    # Reject hidden nonzero data after the declared frame, and
                    # reject nonzero residual bits in the partial 3-bit cell.
                    if accumulator != 0:
                        raise ProtocolError("invalid_frame_padding")
                    tail = cells[(consumed_index + 1):]
                    if any(type(extra) is not int or extra != 0 for extra in tail):
                        raise ProtocolError("unexpected_trailing_cells")
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


class NodeBoundStatusGateway:
    """Opt-in host-side status boundary; NEVER authenticates via pixel data.

    The host must supply a fresh, independently verified Node/Realm authorization
    probe. Both callbacks are trusted local Node-side interfaces, not values
    supplied by the game, its SavedVariables, or the pixel packet.
    No production transport or Node/ONE binding is installed here.
    """

    def __init__(self, authorization_probe, node_adapter, *, max_seen=128):
        if not callable(authorization_probe) or not callable(node_adapter):
            raise TypeError("trusted_host_callbacks_required")
        if not 1 <= max_seen <= 1024:
            raise ValueError("invalid_replay_capacity")
        self._authorization_probe = authorization_probe
        self._node_adapter = node_adapter
        self._seen = set()
        self._max_seen = max_seen

    def accept(self, cells: list[int]) -> dict:
        request_id, session = decode_request(cells)
        key = (session, request_id)
        if key in self._seen:
            return {"status": "UNAVAILABLE", "reason": "DUPLICATE_REQUEST"}
        # Do not discard replay history to make room: fail closed until a new,
        # independently provisioned host session / gateway instance exists.
        if len(self._seen) >= self._max_seen:
            return {"status": "UNAVAILABLE", "reason": "REPLAY_CAPACITY_EXHAUSTED"}
        self._seen.add(key)
        try:
            authorized = self._authorization_probe()
        except Exception:
            return {"status": "UNAVAILABLE", "reason": "NODE_AUTH_UNAVAILABLE"}
        # Require exact True; a truthy error string is not an authorization.
        if authorized is not True:
            return {"status": "UNAVAILABLE", "reason": "NODE_AUTH_UNAVAILABLE"}
        try:
            # The trusted adapter must be the read-only WoWControlAdapter;
            # caller-supplied session never becomes an execution argument.
            result = self._node_adapter({"action": "wow.control.status"})
        except Exception:
            return {"status": "UNAVAILABLE", "reason": "NODE_READER_UNAVAILABLE"}
        if not isinstance(result, dict):
            return {"status": "UNAVAILABLE", "reason": "NODE_READER_UNAVAILABLE"}
        if result.get("status") != "OK":
            return {"status": "UNAVAILABLE", "reason": "NODE_READER_UNAVAILABLE"}
        # Re-check the game-facing projection even if an unexpected adapter
        # implementation is provided. Never surface arbitrary Node responses.
        from agentos_node.wow_control_adapter import _safe_snapshot
        try:
            snapshot = _safe_snapshot(result.get("snapshot"))
        except (TypeError, ValueError):
            return {"status": "UNAVAILABLE", "reason": "UNSAFE_NODE_RESPONSE"}
        return {"status": "OK", "request_id": request_id, "snapshot": snapshot}
