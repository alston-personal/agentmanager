from types import SimpleNamespace

import pytest

from agentos_node import cli


def test_join_reference_prefers_explicit_stdin(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(readline=lambda: "AGENTOSREF1.test\n", isatty=lambda: False))
    args = SimpleNamespace(reference=None, reference_stdin=True)
    assert cli._read_join_reference(args) == "AGENTOSREF1.test"


def test_join_reference_reads_piped_stdin_without_argv(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(readline=lambda: "https://core.example/join#AGENTOSREF1.test\n", isatty=lambda: False))
    args = SimpleNamespace(reference=None, reference_stdin=False)
    assert cli._read_join_reference(args).endswith("AGENTOSREF1.test")


def test_join_reference_uses_hidden_prompt_for_interactive_input(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "AGENTOSREF1.interactive")
    args = SimpleNamespace(reference=None, reference_stdin=False)
    assert cli._read_join_reference(args) == "AGENTOSREF1.interactive"


def test_join_reference_rejects_empty_stdin(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(readline=lambda: "\n", isatty=lambda: False))
    args = SimpleNamespace(reference=None, reference_stdin=True)
    with pytest.raises(ValueError, match="no Join Reference"):
        cli._read_join_reference(args)
