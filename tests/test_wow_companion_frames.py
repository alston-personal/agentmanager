import copy
import unittest

from scripts.wow_companion_frames import (
    CHUNK_SIZE, FrameError, decode_pixel_frame, decode_question_frames,
    encode_pixel_frame, encode_question
)


class CompanionFrameTests(unittest.TestCase):
    SESSION = bytes.fromhex("0102030405060708")

    def test_one_frame_roundtrip(self):
        result = decode_question_frames(encode_question(self.SESSION, 17, "Hello"))
        self.assertEqual(result, {
            "action": "ai.ask", "session": self.SESSION.hex(),
            "request_id": "ask-17", "question": "Hello"
        })

    def test_multi_frame_chinese_roundtrip(self):
        question = "法師在哪裡補秘法智慧？" * 12
        frames = encode_question(self.SESSION, 18, question)
        self.assertGreater(len(frames), 1)
        self.assertTrue(all(len(frame) <= 200 for frame in frames))
        result = decode_question_frames(frames)
        self.assertEqual(result["question"], question)

    def test_maximum_encoded_byte_question(self):
        question = "x" * 500
        frames = encode_question(self.SESSION, 19, question)
        self.assertEqual(decode_question_frames(frames)["question"], question)

    def test_reject_missing_part(self):
        frames = encode_question(self.SESSION, 20, "x" * (CHUNK_SIZE + 1))
        with self.assertRaises(FrameError):
            decode_question_frames(frames[:-1])

    def test_reject_reordered_parts(self):
        frames = encode_question(self.SESSION, 21, "x" * (CHUNK_SIZE + 1))
        with self.assertRaises(FrameError):
            decode_question_frames(frames[::-1])

    def test_reject_mixed_sessions(self):
        frames = encode_question(self.SESSION, 22, "x" * (CHUNK_SIZE + 1))
        other = encode_question(b"87654321", 22, "x" * (CHUNK_SIZE + 1))
        with self.assertRaises(FrameError):
            decode_question_frames([frames[0], other[1]])

    def test_reject_checksum_tamper(self):
        cells = encode_pixel_frame(31, b"hello")
        corrupt = cells[:]
        corrupt[20] = (corrupt[20] + 1) % 8
        with self.assertRaises(FrameError):
            decode_pixel_frame(corrupt)

    def test_accept_full_capture_zero_padding(self):
        cells = encode_pixel_frame(32, b"hello")
        self.assertEqual(decode_pixel_frame(cells + [0] * (200 - len(cells))),
                         (32, b"hello"))

    def test_reject_nonzero_data_after_frame(self):
        cells = encode_pixel_frame(32, b"hello")
        with self.assertRaises(FrameError):
            decode_pixel_frame(cells + [0, 0, 1])

    def test_question_must_fit_byte_bound(self):
        with self.assertRaises(FrameError):
            encode_question(self.SESSION, 33, "法" * 200)

    def test_forbid_game_commands_in_question(self):
        with self.assertRaises(FrameError):
            encode_question(self.SESSION, 34, "|Hitem:123|hClick|h")

    def test_no_authentication_implied(self):
        frames = encode_question(self.SESSION, 35, "Can I teleport?")
        result = decode_question_frames(frames)
        self.assertNotIn("authorized", result)
        self.assertNotIn("api_key", result)


if __name__ == "__main__":
    unittest.main()
