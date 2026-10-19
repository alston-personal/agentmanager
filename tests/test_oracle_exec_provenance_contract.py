from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_oracle_exec_installer_pins_snapshot_provenance():
    installer = (ROOT / "scripts/install_thin_client_linux_oracle.sh").read_text()
    thin_client = (ROOT / "agentos_node/thin_client.py").read_text()
    assert 'PROVENANCE="$RUNTIME/runtime-provenance.json"' in installer
    assert '"schema": "agentos.thin-client-runtime/v0.1"' in installer
    assert '"status": "observed"' in installer
    assert '"source_commit": os.environ["AGENTOS_PINNED_SHA"]' in installer
    assert '"source_ref": os.environ["AGENTOS_PINNED_REF"]' in installer
    assert 'tmp.replace(target)' in installer
    assert 'agentos_oracle_exec_runtime_provenance=PASS' in installer
    assert "Path(__file__).resolve().parent.parent / 'runtime-provenance.json'" in thin_client
    assert "runtime = dict(data)" in thin_client


def test_oracle_exec_restores_pinned_launcher_after_generic_supervisor():
    source = (ROOT / "scripts/install_thin_client_linux_oracle.sh").read_text()
    lifecycle = source.index("install_linux_node_supervisor()")
    restored = source.index("install_pinned_launcher", lifecycle)
    restart = source.index("systemctl --user restart agentos-thin-client.service", restored)
    heartbeat = source.index('"$LAUNCHER" once', restart)
    assert lifecycle < restored < restart < heartbeat
    assert 'export PYTHONPATH="$ROOT/current"' in source
    assert 'export AGENTOS_CLIENT_HOME="$STATE"' in source
    assert '\n#!/bin/bash\nexport AGENTOS_CLIENT_HOME="$STATE"' in source
    assert '\nEOF\nchmod 700 "$LAUNCHER"' in source
