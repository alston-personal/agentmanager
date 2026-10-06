from __future__ import annotations

import unittest

from strategic_interaction import (
    ActionEvent,
    Belief,
    Incentive,
    InteractionState,
    Participant,
)


class StrategicInteractionCoreTests(unittest.TestCase):
    def test_market_and_negotiation_share_the_same_interaction_contract(self) -> None:
        market = InteractionState(
            interaction_type="financial-market",
            observed_at="2026-10-06T13:30:00+08:00",
            participants=(
                Participant("buyers", "aggregate-demand"),
                Participant("sellers", "aggregate-supply"),
            ),
            environment={"instrument": "TWSE:2454", "price": 4950},
            beliefs=(Belief("system", "buyers", "dip-buying-active", 0.62),),
            incentives=(Incentive("buyers", "maximize-risk-adjusted-return"),),
            history=(ActionEvent(0, "sellers", "sell-pressure", {"strength": 0.8}),),
        )

        negotiation = InteractionState(
            interaction_type="bilateral-negotiation",
            observed_at="2026-10-06T13:30:00+08:00",
            participants=(
                Participant("buyer", "buyer"),
                Participant("seller", "seller"),
            ),
            environment={"asset_type": "real-estate", "listing_price": 15800000},
            beliefs=(Belief("buyer", "seller", "reservation-price-below-1490", 0.7),),
            incentives=(Incentive("buyer", "minimize-price-subject-to-close"),),
            history=(ActionEvent(0, "buyer", "offer", {"price": 14300000}),),
        )

        self.assertEqual(market.schema, negotiation.schema)
        self.assertNotEqual(market.interaction_id, negotiation.interaction_id)

    def test_interaction_id_is_deterministic(self) -> None:
        kwargs = dict(
            interaction_type="bilateral-negotiation",
            observed_at="2026-01-01T00:00:00Z",
            participants=(Participant("a", "buyer"), Participant("b", "seller")),
            environment={"listing_price": 100},
        )
        self.assertEqual(InteractionState(**kwargs).interaction_id, InteractionState(**kwargs).interaction_id)


if __name__ == "__main__":
    unittest.main()
