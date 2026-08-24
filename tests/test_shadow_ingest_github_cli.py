import io
import json
import sys

from scripts.shadow_ingest_github import main


def test_shadow_cli_converts_pr_snapshot_without_credentials(monkeypatch, capsys):
    row = {
        "type": "pull_request",
        "data": {
            "number": 3,
            "title": "State Kernel v2 foundation",
            "body": "read-only shadow sample",
            "state": "open",
            "draft": True,
            "merged": False,
            "mergeable": True,
            "head": "feature/state-kernel-v2",
            "head_sha": "abc",
            "updated_at": "2026-08-21T12:00:00Z",
            "url": "https://github.com/alston-personal/agentmanager/pull/3",
            "user": {"login": "alstonhuang"},
            "token": "must-never-be-emitted",
        },
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(row) + "\n"))
    rc = main(["--project", "agentmanager", "--repository", "alston-personal/agentmanager"])
    assert rc == 0
    output = capsys.readouterr().out.strip()
    event = json.loads(output)
    assert event["project_id"] == "agentmanager"
    assert event["source_kind"] == "github"
    assert event["source_ref"] == "github:alston-personal/agentmanager:pull_request:3"
    assert "State Kernel v2 foundation" in event["content"]
    assert "must-never-be-emitted" not in output


def test_shadow_cli_fails_closed_on_bad_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("{bad json}\n"))
    rc = main(["--project", "p", "--repository", "o/r"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "line 1" in captured.err
    assert captured.out == ""


def test_shadow_cli_supports_multiple_records_and_stable_event_ids(monkeypatch, capsys):
    rows = [
        {
            "type": "record",
            "data": {
                "kind": "issue_comment",
                "id": "1",
                "occurred_at": "2026-08-21T12:00:00Z",
                "actor": "a",
                "content": "first",
            },
        },
        {
            "type": "record",
            "data": {
                "kind": "review",
                "id": "2",
                "occurred_at": "2026-08-21T12:01:00Z",
                "actor": "b",
                "content": "second",
            },
        },
    ]
    raw = "".join(json.dumps(item) + "\n" for item in rows)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    assert main(["--project", "p", "--repository", "o/r"]) == 0
    first_output = capsys.readouterr().out.strip().splitlines()
    assert len(first_output) == 2
    ids1 = [json.loads(item)["event_id"] for item in first_output]

    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    assert main(["--project", "p", "--repository", "o/r"]) == 0
    second_output = capsys.readouterr().out.strip().splitlines()
    ids2 = [json.loads(item)["event_id"] for item in second_output]
    assert ids1 == ids2
