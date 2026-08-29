#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SERVICE_SHA = "481520bf4a6f126debd60d23d572692902b98439"
BASE = Path("/home/ubuntu/vendor-reputation-service")
SECRET = Path("/home/ubuntu/agent-data/secrets/vendor-reputation.env")
INPUT = Path("/home/ubuntu/agent-data/runtime/vendor-reputation/threads-DcWVvpwGTSh-normalized-replies.json")
ROOT = "https://www.threads.com/@nico1e.16/post/DcWVvpwGTSh"


def run(args, *, cwd=BASE, timeout=120, check=True):
    p = subprocess.run(
        args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode} stderr_length={len(p.stderr or '')}")
    return p


def psql(sql: str) -> str:
    p = run([
        "docker", "compose", "exec", "-T", "db", "psql",
        "-U", "vendor_service", "-d", "vendor_reputation", "-Atc", sql,
    ])
    return p.stdout.strip()


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=8) as r:
        return r.status, json.loads(r.read().decode())


def load_secret_env():
    if not SECRET.is_file():
        raise RuntimeError("vendor secret file missing")
    for raw in SECRET.read_text().splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        if key == "VENDOR_DB_PASSWORD":
            os.environ[key] = value.strip().strip("'\"")
    if not os.environ.get("VENDOR_DB_PASSWORD"):
        raise RuntimeError("VENDOR_DB_PASSWORD missing")


def parse_import(stdout: str) -> dict:
    for line in reversed(stdout.splitlines()):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("schema") == "milkcat.vendor-evidence-import/v1":
            return obj
    raise RuntimeError("importer output missing structured receipt")


def main() -> int:
    if not BASE.joinpath(".git").is_dir():
        raise RuntimeError("vendor service checkout missing")
    if not INPUT.is_file():
        raise RuntimeError("canonical normalized reply file missing")
    load_secret_env()

    run(["git", "fetch", "--depth=1", "origin", SERVICE_SHA], timeout=60)
    run(["git", "checkout", "--detach", SERVICE_SHA], timeout=30)
    head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    if head != SERVICE_SHA:
        raise RuntimeError("service head mismatch")

    run(["docker", "compose", "up", "-d", "--build"], timeout=240)
    healthy = False
    for _ in range(40):
        try:
            code, data = get_json("http://127.0.0.1:18765/healthz")
            if code == 200 and data.get("ok") is True:
                healthy = True
                break
        except Exception:
            pass
        time.sleep(2)
    if not healthy:
        raise RuntimeError("vendor service health check failed")

    root_sql = ROOT.replace("'", "''")
    target_where = (
        "source_type='threads_public_reply' and review_status='pending' "
        f"and provenance->>'root'='{root_sql}'"
    )
    before = int(psql(f"select count(*) from evidence where {target_where};") or 0)
    links = int(psql(
        "select count(*) from vendor_mentions m join evidence e on e.id=m.evidence_id "
        f"where e.{target_where};"
    ) or 0)
    if links != 0:
        raise RuntimeError(f"safety gate: {links} vendor mention links exist")

    deleted = int(psql(
        f"with d as (delete from evidence where {target_where} returning 1) select count(*) from d;"
    ) or 0)

    imp_run = run([
        "docker", "compose", "run", "--rm", "-T",
        "-v", f"{INPUT}:/private-evidence.json:ro",
        "api", "python", "/srv/app/scripts/import_private_threads_evidence.py", "/private-evidence.json",
    ], timeout=120)
    imp = parse_import(imp_run.stdout)

    _, status = get_json("http://127.0.0.1:18765/v1/status")
    total = int(psql(
        "select count(*) from evidence where source_type='threads_public_reply' "
        f"and provenance->>'root'='{root_sql}';"
    ) or 0)
    authors = int(psql(
        "select count(distinct provenance->>'author') from evidence "
        "where source_type='threads_public_reply' "
        f"and provenance->>'root'='{root_sql}' "
        "and coalesce(provenance->>'author','')<>'';"
    ) or 0)
    texts = int(psql(
        "select count(*) from evidence where source_type='threads_public_reply' "
        f"and provenance->>'root'='{root_sql}' and coalesce(original_text,'')<>'';"
    ) or 0)

    result = {
        "schema": "milkcat.vendor-canonical-evidence-reconcile/v1",
        "service_head": head,
        "pending_target_before": before,
        "linked_mentions_before": links,
        "deleted_pending_target": deleted,
        "import": imp,
        "status_after": status,
        "target_evidence_after": total,
        "distinct_authors_after": authors,
        "evidence_with_text_after": texts,
        "canonical_input_filename": INPUT.name,
        "expected_unique_replies": 33,
        "raw_evidence_committed": False,
        "core_modified": False,
    }
    if total != 33 or texts != 33 or imp.get("unique_permalinks") != 33:
        raise RuntimeError("canonical evidence acceptance failed: " + json.dumps(result, ensure_ascii=False))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({
            "schema": "milkcat.vendor-canonical-evidence-reconcile/v1",
            "ok": False,
            "error_type": type(exc).__name__,
            "error_length": len(str(exc)),
            "raw_evidence_committed": False,
            "core_modified": False,
        }, ensure_ascii=False, indent=2))
        raise
