from __future__ import annotations

import unittest

from strategic_interaction.game_theory import (
    NormalFormGame,
    best_responses,
    classify_prisoners_dilemma,
    pure_nash_candidates,
)


class GameTheoryTests(unittest.TestCase):
    def prisoner_game(self) -> NormalFormGame:
        return NormalFormGame(
            players=("a", "b"),
            actions={"a": ("C", "D"), "b": ("C", "D")},
            payoffs={
                ("C", "C"): (3, 3),
                ("D", "C"): (5, 0),
                ("C", "D"): (0, 5),
                ("D", "D"): (1, 1),
            },
        )

    def test_prisoners_dilemma_and_nash(self) -> None:
        game = self.prisoner_game()
        self.assertTrue(classify_prisoners_dilemma(game, cooperate_action="C", defect_action="D"))
        self.assertEqual(best_responses(game, "a", "C"), ("D",))
        nash = pure_nash_candidates(game)
        self.assertEqual(len(nash), 1)
        self.assertEqual(nash[0].actions, ("D", "D"))

    def test_non_pd_is_not_forced_into_pd_label(self) -> None:
        coordination = NormalFormGame(
            players=("a", "b"),
            actions={"a": ("L", "R"), "b": ("L", "R")},
            payoffs={
                ("L", "L"): (2, 2),
                ("L", "R"): (0, 0),
                ("R", "L"): (0, 0),
                ("R", "R"): (1, 1),
            },
        )
        self.assertFalse(classify_prisoners_dilemma(coordination, cooperate_action="L", defect_action="R"))
        self.assertEqual(len(pure_nash_candidates(coordination)), 2)


if __name__ == "__main__":
    unittest.main()
