"""Release inspector regression for AgentOS public sign-in and privileged UI."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.inspect_distributed_control_plane import probe


def test_release_inspector_requires_signin_shell_and_oauth_session():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/dashboard/api/auth/session" and self.headers.get("Host") != "agentos.milkcat.org":
                self.send_response(400)
                self.end_headers()
                return
            self.send_response(401 if self.path in ("/v1/account/realm-request", "/v1/platform/realm-requests", "/platform", "/v1/account/virtual-one", "/my-one") else 200)
            self.send_header("Content-Type", "application/json" if self.path.endswith("/session") else "text/html")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            if self.path == "/":
                self.wfile.write("AgentOS 以 Google 登入".encode())
            elif self.path == "/welcome":
                from agent_core.companion_web import render_welcome_html
                self.wfile.write(render_welcome_html().encode())
            elif self.path in ("/v1/account/realm-request", "/v1/account/virtual-one", "/my-one"):
                self.wfile.write(json.dumps({"ok": False, "error": "signin_required"}).encode())
            elif self.path == "/v1/platform/realm-requests":
                self.wfile.write(json.dumps({"ok": False, "error": "signin_required"}).encode())
            elif self.path == "/platform":
                self.wfile.write("需要使用已獲授權的平台管理者帳號登入 returnTo=%2Fplatform".encode())
            elif self.path == "/companion":
                self.wfile.write(b"AgentOS Console: Node Map")
            else:
                self.wfile.write(json.dumps({"loggedIn": False, "providers": {"google": True}}).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert probe(base + "/", "test-secret", kind="shell")["ok"]
        assert probe(base + "/welcome", "test-secret", kind="welcome")["ok"]
        assert probe(base + "/v1/account/realm-request", "test-secret", kind="account_anon")["ok"]
        assert probe(base + "/v1/account/virtual-one", "test-secret", kind="virtual_one_anon")["ok"]
        assert probe(base + "/my-one", "test-secret", kind="my_one_anon")["ok"]
        assert probe(base + "/v1/platform/realm-requests", "test-secret", kind="platform_anon")["ok"]
        assert probe(base + "/platform", "test-secret", kind="platform_page_anon")["ok"]
        assert probe(base + "/companion", "test-secret", kind="companion")["ok"]
        assert probe(base + "/dashboard/api/auth/session", "test-secret", kind="auth_session")["ok"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_release_inspector_rejects_legacy_root_console_and_broken_auth_session():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            if self.path == "/":
                self.wfile.write(b"Node Map")
            else:
                self.wfile.write(json.dumps({"loggedIn": True, "providers": {}}).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert not probe(base + "/", "test-secret", kind="shell")["ok"]
        assert not probe(base + "/dashboard/api/auth/session", "test-secret", kind="auth_session")["ok"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_oauth_origin_probe_rejects_studio_and_accepts_agentos():
    from scripts.inspect_distributed_control_plane import probe_oauth_origin
    from urllib.parse import urlsplit

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            provider = urlsplit(self.path).path.rsplit("/", 1)[-1]
            if provider == "facebook":
                target = "https://studio.milkcat.org"
            else:
                target = "https://agentos.milkcat.org"
            callback = target + "/dashboard/api/auth/callback/" + provider
            from urllib.parse import urlencode
            location = "https://example.org/oauth/authorize?" + urlencode({
                "redirect_uri": callback, "state": "12345",
            })
            self.send_response(307)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        for provider in ("google", "github", "line"):
            receipt = probe_oauth_origin(base, provider, local=True)
            assert receipt["ok"], (provider, receipt)
            assert receipt["agentos_callback"]
        receipt = probe_oauth_origin(base, "facebook", local=True)
        assert receipt["ok"] is False
        assert receipt["agentos_callback"] is False
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_welcome_inspector_rejects_stale_production_copy(monkeypatch):
    import io
    class Response(io.BytesIO):
        def __init__(self, status, body):
            super().__init__(body)
            self.status = status
            self.headers = {}
    old = ('登入狀態；管理者 Console 不會自動開放 ' +
           'id="create-realm" /v1/account/realm-request').encode()
    monkeypatch.setattr('scripts.inspect_distributed_control_plane.urlopen',
                        lambda *a, **k: Response(200, old))
    result = probe('http://test/welcome', 'test-secret', kind='welcome')
    assert result['ok'] is False
    assert result['obsolete_copy_absent'] is False
    assert result['account_header'] is False


def test_auto_release_receipt_reports_to_original_issue_without_deployment_secrets():
    """The existing Distributed Control Plane CI executes this test."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / ".github/workflows/oracle-agentos-login-control-plane-release.yml").read_text(encoding="utf-8")
    assert "report-release-receipt:" in source
    assert "needs: [deploy]" in source
    assert "if: ${{ always() }}" in source
    assert "DEPLOY_RESULT: ${{ needs.deploy.result }}" in source
    assert "const issue_number = 2198;" in source
    assert "context.runId" in source and "context.sha" in source
    assert "github.rest.issues.createComment" in source
    assert "github.rest.issues.updateComment" in source
    assert "agentos-control-plane-release:" in source
    reporter = source.split("\n  report-release-receipt:", 1)[1]
    assert "issues: write" in reporter
    assert "ssh-private-key:" not in reporter
    assert "DEPLOY_USER" not in reporter
    assert "authenticated admin/tenant sessions remain separate acceptance gates" in reporter.lower()
    assert "not established" in reporter.lower()


def test_active_blue_green_admin_attestation_is_read_only_and_not_a_login_proof(tmp_path):
    import os
    import stat
    from scripts.inspect_dashboard_admin_identity_user import (
        safe_private_identities, process_pids_on_port,
    )
    folder = tmp_path / ".config" / "milkcat"
    folder.mkdir(parents=True)
    owner_file = folder / "admin-identities"
    owner_file.write_text("google:username:register@milkcat.org\n", encoding="utf-8")
    owner_file.chmod(0o600)
    entries, verdict = safe_private_identities(tmp_path, os.getuid())
    assert verdict == "PASS"
    assert "google:username:register@milkcat.org" in entries
    owner_file.chmod(0o644)
    assert safe_private_identities(tmp_path, os.getuid())[1] == "REJECTED"
    assert process_pids_on_port(3040, 'users:(("next-server",pid=4201,fd=22))') == {4201}

    from pathlib import Path
    wf = (Path(__file__).resolve().parents[1] /
          ".github/workflows/oracle-agentos-login-control-plane-release.yml").read_text(encoding="utf-8")
    assert "id: admin_attestation" in wf
    assert "admin_configured: ${{ steps.admin_attestation.outputs.admin_configured }}" in wf
    assert "ADMIN_CONFIGURED: ${{ needs.deploy.outputs.admin_configured }}" in wf
    assert "session role not attested" in wf.lower()
    assert "git -C \"$REPO\" show \"$SOURCE_SHA:scripts/inspect_dashboard_admin_identity_user.py\"" in wf
    assert "needs: [deploy]" in wf


def test_oracle_readonly_control_plane_audit_parses_proc_nul_and_redacts_owners():
    """Prevent the earlier escaped-NUL bug that misclassified push switches."""
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              ".github/workflows/oracle-core-service-runtime-audit.yml"
              ).read_text(encoding="utf-8")
    assert 'replace(bytes([0]), b" ")' in source
    assert '.split(chr(0))' in source
    assert 'target_kind_counts' in source
    assert 'submitted_task_classes' in source
    assert 'submitted_inventory_reconciles' in source
    assert 'PRAGMA query_only=ON' in source
    assert 'service restart' not in source.split("  control-plane-readonly:", 1)[1].lower()


def test_teams_immutable_core_install_contract_fail_closed():
    """The observed 2026-11-15 Teams drift must not silently pass convergence."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    installer = (root / "scripts/install_systemd_user.sh").read_text(encoding="utf-8")
    convergence = (
        root / ".github/workflows/oracle-core-bundle-immutable-runtime-convergence.yml"
    ).read_text(encoding="utf-8")
    assert 'TEAMS_BRIDGE_AVAILABLE=0' in installer
    assert '[ -f "$LOGIC_ROOT/scripts/teams_bridge.py" ]' in installer
    assert 'ExecStart=$PYTHON_BIN scripts/teams_bridge.py' in installer
    assert 'systemctl --user is-active --quiet teams-commander.service' in installer
    assert 'systemctl --user restart teams-commander.service' in installer
    assert 'FAIL_MISSING_BRIDGE' in convergence
    assert 'teams-commander.service cat-ink-syncer.service agentos-core-supervisor.service' in convergence
    assert 'core_bundle_teams_workdir=EXACT_IMMUTABLE_RELEASE' in convergence
def test_teams_live_cutover_is_scoped_fail_closed_and_shell_valid():
    from pathlib import Path
    import subprocess

    root = Path(__file__).resolve().parents[1]
    script = root / "scripts/converge_teams_immutable_user.sh"
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0
    content = script.read_text(encoding="utf-8")
    assert 'test "$(id -un)" = ubuntu' in content
    assert 'SOURCE_SHA' in content
    assert 'test "$pid_after" != "$pid_before"' in content
    assert 'teams_cutover_pid_cwd=EXACT_IMMUTABLE_RELEASE' in content
    assert 'teams_cutover_rollback=BEGIN' in content
    assert 'teams_cutover_other_core_units=UNTOUCHED' in content
    assert 'git -C "$REPO" worktree add --detach "$RELEASE" "$SOURCE_SHA"' in content
    assert 'systemctl --user restart "$SERVICE"' in content
    assert 'systemctl --user restart os-chronos.service' not in content
    assert 'ln -sfn "$RELEASE" "$CURRENT"' not in content


def test_teams_live_cutover_requires_explicit_existing_operator_dispatch():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/oracle-core-bundle-immutable-runtime-convergence.yml").read_text(encoding="utf-8")
    assert "branches: [core/integration]" in workflow
    assert "teams_only:" in workflow
    assert "teams-immutable-cutover:" in workflow
    assert "inputs.teams_only == true" in workflow
    assert "github.ref_name == 'main'" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "bash -s -- \"$GITHUB_SHA\" <<'REMOTE'" in workflow
    assert "governance/release-intents/teams-immutable-20261115.json" not in workflow
    assert "teams-release-intent:" not in workflow


def test_teams_rollback_is_armed_before_atomic_unit_replacement():
    from pathlib import Path
    import subprocess

    source = (Path(__file__).resolve().parents[1] /
              "scripts/converge_teams_immutable_user.sh")
    text = source.read_text(encoding="utf-8")
    assert subprocess.run(["bash", "-n", str(source)], capture_output=True).returncode == 0
    assert text.index("trap finish EXIT") < text.index("changed=1")
    assert text.index("changed=1") < text.index('python3 - "$UNIT" "$ORIGINAL_WD" "$RELEASE"')
    assert 'teams_cutover_rollback=RESTORED_PREVIOUS_OWNER' in text
    assert 'teams_cutover_rollback=FAILED_TO_VERIFY_PREVIOUS_OWNER' in text
    assert '[ "$rollback_wd" = "$ORIGINAL_WD" ]' in text
    assert '[ "$rollback_cwd" = "$ORIGINAL_WD" ]' in text
