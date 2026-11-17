import unittest

from scripts.wow_companion_frames import encode_question
from scripts.wow_companion_receiver import QuestionFrameReceiver


class QuestionReceiverTests(unittest.TestCase):
    SESSION = b"abcdefgh"

    def _frames(self, question, number=41):
        return [cells + [0] * (200 - len(cells))
                for cells in encode_question(self.SESSION, number, question)]

    def test_single_frame_200_cell_capture(self):
        receiver = QuestionFrameReceiver()
        result = receiver.accept(self._frames("Mage buff?")[0])
        self.assertEqual(result["status"], "QUESTION_REASSEMBLED")
        self.assertEqual(result["request"]["question"], "Mage buff?")
        self.assertEqual(result["request"]["request_id"], "ask-41")

    def test_incremental_chinese_capture(self):
        receiver = QuestionFrameReceiver()
        frames = self._frames("法師技能怎麼加？" * 20)
        for index, frame in enumerate(frames):
            result = receiver.accept(frame)
            if index < len(frames) - 1:
                self.assertEqual(result, {
                    "status": "PART_CAPTURED", "index": index, "total": len(frames)
                })
        self.assertEqual(result["status"], "QUESTION_REASSEMBLED")
        self.assertEqual(result["request"]["question"], "法師技能怎麼加？" * 20)

    def test_missing_first_frame_denied(self):
        receiver = QuestionFrameReceiver()
        frames = self._frames("x" * 80)
        self.assertEqual(receiver.accept(frames[1])["status"], "REJECTED")

    def test_duplicate_frame_resets_partial_group(self):
        receiver = QuestionFrameReceiver()
        frames = self._frames("x" * 80)
        self.assertEqual(receiver.accept(frames[0])["status"], "PART_CAPTURED")
        self.assertEqual(receiver.accept(frames[0])["status"], "REJECTED")
        self.assertEqual(receiver.accept(frames[1])["status"], "REJECTED")

    def test_corrupted_frame_resets(self):
        receiver = QuestionFrameReceiver()
        frames = self._frames("x" * 80)
        receiver.accept(frames[0])
        damaged = frames[1][:]
        damaged[-1] = 1
        self.assertEqual(receiver.accept(damaged)["status"], "REJECTED")
        self.assertEqual(receiver.accept(frames[1])["status"], "REJECTED")

    def test_timeout_fails_closed(self):
        now = [0]
        receiver = QuestionFrameReceiver(max_age_seconds=5, clock=lambda: now[0])
        frames = self._frames("x" * 80)
        receiver.accept(frames[0])
        now[0] = 6
        self.assertEqual(receiver.accept(frames[1])["status"], "REJECTED")
        self.assertEqual(receiver.accept(frames[1])["status"], "REJECTED")

    def test_mixed_session_rejected(self):
        receiver = QuestionFrameReceiver()
        first = self._frames("x" * 80)
        second = [cells + [0] * (200 - len(cells))
                  for cells in encode_question(b"12345678", 41, "x" * 80)]
        receiver.accept(first[0])
        self.assertEqual(receiver.accept(second[1])["status"], "REJECTED")

    def test_capture_progress_is_not_bridge_authorization(self):
        frames = self._frames("x" * 80)
        state = QuestionFrameReceiver().accept(frames[0])
        self.assertEqual(state["status"], "PART_CAPTURED")
        self.assertNotIn("authorized", state)
        self.assertNotIn("sent", state)


if __name__ == "__main__":
    unittest.main()
