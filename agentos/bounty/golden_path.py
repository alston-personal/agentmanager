import json
import os
from datetime import datetime, timezone

class BountyGoldenPath:
    def __init__(self, ledger_path="agentos/bounty/ledger.json"):
        self.ledger_path = ledger_path
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)

    def evaluate_candidate(self, issue):
        """
        Evaluates a bounty candidate in read-only mode against governance rules:
        - Excludes formally assigned or crowded issues.
        - Validates sponsor terms.
        - Computes ONE/IR readiness qualification.
        """
        issue_id = issue.get("id")
        title = issue.get("title", "")
        assignee = issue.get("assignee")
        state = issue.get("state", "open")
        crowded = issue.get("crowded", False)
        sponsor = issue.get("sponsor", "")
        reward_usd = issue.get("reward_usd", 0)

        # Rule 1: Must be open and unassigned
        if state != "open" or assignee is not None:
            return {
                "issue_id": issue_id,
                "qualified": False,
                "reason": "Issue is closed or formally assigned to another contributor."
            }

        # Rule 2: Exclude crowded or disputed issues without proven claimability
        if crowded:
            return {
                "issue_id": issue_id,
                "qualified": False,
                "reason": "Issue is crowded with competing claims; not yet proven claimable."
            }

        # Rule 3: Sponsor terms check
        if sponsor.lower() == "tenstorrent" and issue.get("ai_assisted_prohibited", False):
            return {
                "issue_id": issue_id,
                "qualified": False,
                "reason": "AI-assisted contributions are prohibited by sponsor terms."
            }

        # Qualification Passed
        receipt = {
            "schema": "agentos.bounty-qualification/v1",
            "issue_id": issue_id,
            "sponsor": sponsor,
            "reward_usd": reward_usd,
            "qualified_at": datetime.now(timezone.utc).isoformat(),
            "status": "qualified_read_only"
        }
        self._persist_receipt(receipt)
        return {
            "issue_id": issue_id,
            "qualified": True,
            "receipt": receipt
        }

    def _persist_receipt(self, receipt):
        ledger = []
        if os.path.exists(self.ledger_path):
            try:
                with open(self.ledger_path, "r", encoding="utf-8") as f:
                    ledger = json.load(f)
            except Exception:
                ledger = []
        ledger.append(receipt)
        with open(self.ledger_path, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=2)
