#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Direct script execution sets sys.path[0] to scripts/. Keep this fresh-checkout
# safe rather than relying on an editable install or caller PYTHONPATH.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.master_blind_trial import build_blind_trial, hidden_json, public_json, validate_trial_pair


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--material-actions", type=int, default=24)
    parser.add_argument("--public-output", required=True)
    parser.add_argument("--hidden-output", required=True)
    args = parser.parse_args()

    trial, key = build_blind_trial(args.seed, material_actions=args.material_actions)
    validate_trial_pair(trial, key)
    public_path = Path(args.public_output)
    hidden_path = Path(args.hidden_output)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    hidden_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(public_json(trial) + "\n", encoding="utf-8")
    hidden_path.write_text(hidden_json(key) + "\n", encoding="utf-8")
    print(f"trial_id={trial.trial_id}")
    print(f"public={public_path}")
    print(f"hidden={hidden_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
