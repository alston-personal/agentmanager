from pathlib import Path

import pytest

from agent_core.credit_ledger import CreditLedger


def test_grant_reserve_commit_release_refund_flow(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    ledger.grant("acct", 100, "grant-1")
    reserve = ledger.reserve("acct", 60, "reserve-1", metadata={"execution_id": "job-1"})

    assert ledger.summary("acct") == {
        "accountId": "acct",
        "balance": 100,
        "reserved": 60,
        "available": 40,
    }

    ledger.commit(reserve["entryId"], "commit-1", 45)
    ledger.release(reserve["entryId"], "release-1")
    assert ledger.summary("acct") == {
        "accountId": "acct",
        "balance": 55,
        "reserved": 0,
        "available": 55,
    }

    ledger.refund(reserve["entryId"], "refund-1", 20)
    assert ledger.summary("acct") == {
        "accountId": "acct",
        "balance": 75,
        "reserved": 0,
        "available": 75,
    }
    assert [entry["operation"] for entry in ledger.entries("acct")] == [
        "grant", "reserve", "commit", "release", "refund"
    ]


def test_same_idempotency_key_never_double_posts(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    first = ledger.grant("acct", 100, "same-key")
    second = ledger.grant("acct", 100, "same-key")
    assert first == second
    assert ledger.summary("acct")["balance"] == 100
    assert len(ledger.entries("acct")) == 1


def test_idempotency_key_conflict_is_rejected(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    ledger.grant("acct", 100, "same-key")
    with pytest.raises(ValueError, match="idempotency key"):
        ledger.grant("acct", 101, "same-key")


def test_reserve_cannot_overdraw_available_balance(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    ledger.grant("acct", 50, "grant")
    ledger.reserve("acct", 40, "reserve")
    with pytest.raises(ValueError, match="insufficient"):
        ledger.reserve("acct", 11, "reserve-too-much")


def test_commit_and_release_cannot_exceed_reservation(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    ledger.grant("acct", 100, "grant")
    reserve = ledger.reserve("acct", 40, "reserve")
    ledger.commit(reserve["entryId"], "commit", 25)
    with pytest.raises(ValueError, match="exceeds remaining"):
        ledger.release(reserve["entryId"], "release-too-much", 16)
    with pytest.raises(ValueError, match="exceeds remaining"):
        ledger.commit(reserve["entryId"], "commit-too-much", 16)


def test_refund_cannot_exceed_committed_amount(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    ledger.grant("acct", 100, "grant")
    reserve = ledger.reserve("acct", 40, "reserve")
    ledger.commit(reserve["entryId"], "commit", 30)
    ledger.refund(reserve["entryId"], "refund", 20)
    with pytest.raises(ValueError, match="exceeds committed"):
        ledger.refund(reserve["entryId"], "refund-too-much", 11)


def test_amounts_must_be_positive_integers(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "credits.sqlite3")
    for invalid in (0, -1, 1.5, True):
        with pytest.raises(ValueError, match="positive integer"):
            ledger.grant("acct", invalid, f"invalid-{invalid}")
