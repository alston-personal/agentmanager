from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'repair_antigravity_relay_user.sh'


def _text() -> str:
    return SCRIPT.read_text(encoding='utf-8')


def test_repair_is_branch_aware_and_allowlisted():
    text = _text()
    assert 'SOURCE_REF="${AGENTOS_REF:-main}"' in text
    assert 'main|feature/realm-node-fabric-readiness' in text
    assert 'git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"' in text
    assert 'SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)' in text
    assert 'origin/main:' not in text


def test_repair_materializes_join_bootstrap_generation():
    text = _text()
    assert 'show_source agent_core/node_bootstrap.py' in text
    assert 'install -m 0664 "$TMPDIR/node_bootstrap.py" "$REALM_RUNTIME/agent_core/node_bootstrap.py"' in text
    assert 'realm_fabric_bootstrap_route=PASS' in text
    assert 'realm_fabric_benchmark_route=PASS' in text


def test_relay_boundary_uses_authorized_agentos_group_before_worker_start():
    text = _text()
    assert "ExecStart=/usr/bin/sg agentos -c '/usr/bin/python3 -m agentos_node.antigravity_relay_worker" in text
    unit_section = text.split('cat > "$UNIT" <<EOF', 1)[1].split('EOF', 1)[0]
    assert 'NoNewPrivileges=true' not in unit_section
    assert 'UMask=0007' in unit_section
