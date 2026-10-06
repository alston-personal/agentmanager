from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class NormalFormGame:
    players: tuple[str, str]
    actions: Mapping[str, tuple[str, ...]]
    payoffs: Mapping[tuple[str, str], tuple[float, float]]

    def __post_init__(self) -> None:
        a, b = self.players
        if a == b:
            raise ValueError("players must be distinct")
        for aa in self.actions.get(a, ()):
            for bb in self.actions.get(b, ()):
                if (aa, bb) not in self.payoffs:
                    raise ValueError(f"missing payoff for action pair {(aa, bb)}")


@dataclass(frozen=True)
class NashCandidate:
    actions: tuple[str, str]
    payoffs: tuple[float, float]


def best_responses(game: NormalFormGame, player: str, opponent_action: str) -> tuple[str, ...]:
    p0, p1 = game.players
    if player not in game.players:
        raise ValueError("unknown player")

    if player == p0:
        scored = [(action, game.payoffs[(action, opponent_action)][0]) for action in game.actions[p0]]
    else:
        scored = [(action, game.payoffs[(opponent_action, action)][1]) for action in game.actions[p1]]

    best = max(score for _, score in scored)
    return tuple(action for action, score in scored if score == best)


def pure_nash_candidates(game: NormalFormGame) -> tuple[NashCandidate, ...]:
    p0, p1 = game.players
    out = []
    for a0 in game.actions[p0]:
        for a1 in game.actions[p1]:
            if a0 in best_responses(game, p0, a1) and a1 in best_responses(game, p1, a0):
                out.append(NashCandidate(actions=(a0, a1), payoffs=game.payoffs[(a0, a1)]))
    return tuple(out)


def classify_prisoners_dilemma(
    game: NormalFormGame,
    *,
    cooperate_action: str,
    defect_action: str,
) -> bool:
    p0, p1 = game.players
    if tuple(game.actions[p0]) != tuple(game.actions[p1]):
        return False
    if cooperate_action not in game.actions[p0] or defect_action not in game.actions[p0]:
        return False

    cc = game.payoffs[(cooperate_action, cooperate_action)]
    dc = game.payoffs[(defect_action, cooperate_action)]
    cd = game.payoffs[(cooperate_action, defect_action)]
    dd = game.payoffs[(defect_action, defect_action)]

    # Symmetric ordinal Prisoner's Dilemma:
    # Temptation > Reward > Punishment > Sucker.
    return (
        dc[0] > cc[0] > dd[0] > cd[0]
        and cd[1] > cc[1] > dd[1] > dc[1]
    )
