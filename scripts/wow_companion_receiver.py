"""Host-local incremental decoder for WoW Companion RGB question frames.

This is a capture-side parsing helper, NOT a capture driver, trusted session
verifier, game acknowledgment channel, server or executor.
"""
from __future__ import annotations

import time

from scripts.wow_companion_frames import (
    CHUNK_SIZE, MAX_PARTS, PART_HEADER, PART_MARKER,
    FrameError, decode_pixel_frame, decode_question_frames
)


class QuestionFrameReceiver:
    """Allow one bounded in-flight question and fail closed on uncertain state.

    ACK refers ONLY to local capture of a frame. It does not prove a WoW AddOn
    received it, that a game session is authenticated, or that AI was queried.
    """

    def __init__(self, *, max_age_seconds=20, clock=None):
        if type(max_age_seconds) not in (int, float) or not 1 <= max_age_seconds <= 120:
            raise ValueError("INVALID_MAX_AGE")
        self._clock = clock if clock is not None else time.monotonic
        if not callable(self._clock):
            raise TypeError("CLOCK_REQUIRED")
        self._max_age = float(max_age_seconds)
        self._frames = []
        self._session = None
        self._question_id = None
        self._total = None
        self._started = None

    def _clear(self):
        self._frames = []
        self._session = self._question_id = self._total = self._started = None

    def accept(self, cells):
        """Return data-only local parsing status, never game/AI success."""
        try:
            now = self._clock()
            if self._started is not None and now - self._started > self._max_age:
                self._clear()
                raise FrameError("FRAME_GROUP_EXPIRED")
            frame_id, payload = decode_pixel_frame(cells)
            if len(payload) <= PART_HEADER or payload[0] != PART_MARKER:
                raise FrameError("INVALID_PART")
            session = payload[1:9]
            question_id = int.from_bytes(payload[9:11], "big")
            index = payload[11]
            total = payload[12]
            if frame_id != question_id or not 1 <= total <= MAX_PARTS:
                raise FrameError("MIXED_REQUEST")
            if not self._frames:
                if index != 0:
                    raise FrameError("FIRST_PART_MISSING")
                self._session, self._question_id = session, question_id
                self._total, self._started = total, now
            if (session != self._session or question_id != self._question_id
                    or total != self._total or index != len(self._frames)):
                raise FrameError("OUT_OF_ORDER_OR_MIXED")
            if len(payload) - PART_HEADER > CHUNK_SIZE:
                raise FrameError("PART_TOO_LONG")
            self._frames.append(list(cells))
            if len(self._frames) != total:
                return {"status": "PART_CAPTURED", "index": index, "total": total}
            question = decode_question_frames(self._frames)
            self._clear()
            return {"status": "QUESTION_REASSEMBLED", "request": question}
        except (FrameError, ValueError, TypeError):
            self._clear()
            return {"status": "REJECTED", "reason": "INVALID_OR_INCOMPLETE_CAPTURE"}
