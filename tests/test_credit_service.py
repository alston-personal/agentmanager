from pathlib import Path

import pytest

from agent_core.credit_ledger import CreditLedger
from agent_core.credit_service import CreditBilling


def _pricing(tmp_path: Path) -> Path:
    path = tmp_path / "pricing.json"
    path.write_text(
        '{"schema":"milkcat.credit-pricing/v1","currency":"credit","actions":'
        '{"fengshui.view":0,"fengshui.analysis.generate":2}}',
        encoding="utf-8",
    )
    return path


def test_shadow_mode_records_intended_cost_without_charging(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    ledger.grant("acct", 10, "grant")
    billing = CreditBilling(
        ledger=ledger,
        pricing_path=_pricing(tmp_path),
        mode="shadow",
    )

    receipt = billing.execute(
        account_id="acct",
        action_id="fengshui.analysis.generate",
        operation_id="op-1",
        success=True,
    )

    assert receipt["quotedCost"] == 2
    assert receipt["chargedCost"] == 0
    assert receipt["status"] == "shadow_success"
    assert ledger.summary("acct")["balance"] == 10
    assert billing.usage_summary("acct")["actions"]["fengshui.analysis.generate"] == {
        "uses": 1,
        "quotedCost": 2,
        "chargedCost": 0,
    }


def test_free_action_never_reserves_credits(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    billing = CreditBilling(ledger=ledger, pricing_path=_pricing(tmp_path), mode="enforce")

    receipt = billing.execute(
        account_id="acct",
        action_id="fengshui.view",
        operation_id="op-free",
        success=True,
    )

    assert receipt["status"] == "free"
    assert receipt["quotedCost"] == 0
    assert receipt["chargedCost"] == 0
    assert ledger.entries("acct") == []


def test_enforce_mode_commits_on_success_and_releases_on_failure(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    ledger.grant("acct", 10, "grant")
    billing = CreditBilling(ledger=ledger, pricing_path=_pricing(tmp_path), mode="enforce")

    ok = billing.execute(
        account_id="acct",
        action_id="fengshui.analysis.generate",
        operation_id="op-ok",
        success=True,
    )
    failed = billing.execute(
        account_id="acct",
        action_id="fengshui.analysis.generate",
        operation_id="op-fail",
        success=False,
    )

    assert ok["chargedCost"] == 2
    assert ok["status"] == "charged"
    assert failed["chargedCost"] == 0
    assert failed["status"] == "released"
    assert ledger.summary("acct")["balance"] == 8
    assert ledger.summary("acct")["reserved"] == 0


def test_operation_id_is_idempotent_and_cannot_change_action(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    billing = CreditBilling(ledger=ledger, pricing_path=_pricing(tmp_path), mode="shadow")

    first = billing.execute(
        account_id="acct",
        action_id="fengshui.analysis.generate",
        operation_id="same-op",
        success=True,
    )
    second = billing.execute(
        account_id="acct",
        action_id="fengshui.analysis.generate",
        operation_id="same-op",
        success=False,
    )

    assert first == second
    with pytest.raises(ValueError, match="different credit action"):
        billing.execute(
            account_id="acct",
            action_id="fengshui.view",
            operation_id="same-op",
            success=True,
        )


def test_unknown_actions_are_rejected(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    billing = CreditBilling(ledger=ledger, pricing_path=_pricing(tmp_path), mode="shadow")
    with pytest.raises(KeyError, match="unknown credit action"):
        billing.quote("fengshui.unknown")
