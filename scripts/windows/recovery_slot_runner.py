#!/usr/bin/env python3
"""Independent, minimal Recovery A/B probe launcher (stdlib only).

Normal installs bootstrap slot A once. This runner never downloads, installs
or upgrades code, and never trusts instructions returned by ONE. Installing a
candidate in B and promoting it will require a separate governed updater.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCHEMA = "agentos.recovery-slots/v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
SLOTS = ("A", "B")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".recovery-state-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(document, out, sort_keys=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _strict_slot_path(root, slot):
    if slot not in SLOTS:
        raise ValueError("invalid_recovery_slot")
    root = Path(root).resolve()
    return root / ("slot-" + slot) / "recovery_one_probe.py"


def validate_state(root, state):
    if not isinstance(state, dict) or set(state) != {
            "schema", "active", "last_known_good", "pending", "digests"}:
        raise ValueError("invalid_recovery_slots_state")
    if state["schema"] != SCHEMA or state["active"] not in SLOTS:
        raise ValueError("invalid_recovery_slots_state")
    if state["last_known_good"] not in SLOTS:
        raise ValueError("invalid_recovery_lkg")
    if state["pending"] not in (None, "A", "B"):
        raise ValueError("invalid_recovery_pending")
    if not isinstance(state["digests"], dict):
        raise ValueError("invalid_recovery_digests")
    if not all(slot in SLOTS and isinstance(value, str) and HEX.fullmatch(value)
               for slot, value in state["digests"].items()):
        raise ValueError("invalid_recovery_digests")
    if not {state["active"], state["last_known_good"]} <= state["digests"].keys():
        raise ValueError("missing_recovery_slot_digest")
    if state["pending"] is not None and state["pending"] != state["active"]:
        raise ValueError("invalid_pending_activation")
    if state["pending"] is not None and state["pending"] == state["last_known_good"]:
        raise ValueError("unprotected_recovery_lkg")
    return state


def load_state(root):
    doc = json.loads((Path(root) / "slots.json").read_text(encoding="utf-8"))
    return validate_state(root, doc)


def valid_slot(root, state, slot):
    expected = state["digests"].get(slot)
    path = _strict_slot_path(root, slot)
    return bool(expected and path.is_file() and not path.is_symlink()
                and path.resolve().is_relative_to(Path(root).resolve())
                and digest(path) == expected)


def bootstrap(root, source):
    """Initial slot A only; never replace existing Recovery state."""
    root = Path(root)
    source = Path(source)
    if not source.is_file():
        raise ValueError("missing_recovery_bootstrap")
    state_path = root / "slots.json"
    if state_path.exists():
        state = load_state(root)
        if not valid_slot(root, state, state["last_known_good"]):
            raise ValueError("existing_recovery_slot_corrupt")
        return state
    # A pre-existing slot with no state is not safe to overwrite/reclaim.
    for slot in SLOTS:
        if _strict_slot_path(root, slot).exists():
            raise ValueError("unmanaged_recovery_slot_exists")
    path = _strict_slot_path(root, "A")
    path.parent.mkdir(parents=True, exist_ok=False)
    exclusive = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(exclusive, "wb") as out, source.open("rb") as inp:
            for chunk in iter(lambda: inp.read(65536), b""):
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    state = {"schema": SCHEMA, "active": "A", "last_known_good": "A",
             "pending": None, "digests": {"A": digest(path)}}
    atomic_json(state_path, state)
    return state


def run(root, config, status, *, interpreter=None):
    """Fail closed on invalid primary; fallback ONLY for pending candidate.

    Network outages alone must not silently switch a verified stable slot.
    """
    root = Path(root)
    state = load_state(root)
    chosen = state["active"]
    if not valid_slot(root, state, chosen):
        if state["pending"] != chosen or not valid_slot(root, state, state["last_known_good"]):
            raise RuntimeError("recovery_active_corrupt_or_unrecoverable")
        chosen = state["last_known_good"]
        atomic_json(root / "slots.json", {
            **state, "active": chosen, "pending": None
        })
    return subprocess.run(
        [interpreter or sys.executable, "-I",
         str(_strict_slot_path(root, chosen)), "--config", str(config),
         "--status", str(status)],
        check=False, timeout=30,
    ).returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--config")
    parser.add_argument("--status")
    parser.add_argument("--bootstrap-from")
    args = parser.parse_args()
    if args.bootstrap_from:
        if args.config or args.status:
            parser.error("bootstrap does not accept probe arguments")
        bootstrap(args.root, args.bootstrap_from)
        return
    if not args.config or not args.status:
        parser.error("run requires config and status")
    raise SystemExit(run(args.root, args.config, args.status))


if __name__ == "__main__":
    main()
