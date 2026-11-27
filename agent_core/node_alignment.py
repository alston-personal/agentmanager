from __future__ import annotations

import json
import os
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_core.realm_fabric import RealmFabricStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class NodeAlignmentEngine:
    """AgentOS 全域跨節點校準引擎 (Node Alignment Engine).

    依據身心合一與分散式治理守則，負責校準：
    1. 連線與心跳時效 (Transport & Heartbeat Freshness)
    2. 版本與代碼同步 (Code & Version Parity)
    3. 能力邊界與執行表面 (Capability & Surface Alignment)
    """

    def __init__(self, fabric_store: Optional[RealmFabricStore] = None):
        self.fabric_store = fabric_store or RealmFabricStore()
        self.repo_root = Path(__file__).resolve().parent.parent

    def get_central_head_commit(self) -> str:
        """取得 Central ONE 本地倉庫的 HEAD Commit Hash."""
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            return res.stdout.strip()
        except Exception:
            return "unknown"

    def audit_all_nodes(self, max_stale_seconds: int = 300) -> Dict[str, Any]:
        """對所有註冊節點執行身心合一校準稽核."""
        fabric_data = self.fabric_store.load()
        nodes = fabric_data.get("nodes", {})
        now = datetime.now(timezone.utc)
        central_commit = self.get_central_head_commit()

        report: Dict[str, Any] = {
            "schema": "agentos.node-alignment-receipt/v1",
            "aligned_at": _utc_now(),
            "central_commit": central_commit,
            "total_nodes": len(nodes),
            "nodes": {},
            "summary": {
                "live": 0,
                "stale": 0,
                "offline": 0,
            },
            "anomalies": [],
        }

        for node_id, node_info in nodes.items():
            last_seen = node_info.get("last_seen_at")
            seconds_ago = None
            status = "offline"

            if last_seen:
                try:
                    last_seen_dt = _parse_utc(last_seen)
                    seconds_ago = (now - last_seen_dt).total_seconds()
                    if seconds_ago <= max_stale_seconds:
                        status = "live"
                    else:
                        status = "stale"
                except Exception:
                    status = "malformed_heartbeat"

            if status == "live":
                report["summary"]["live"] += 1
            elif status == "stale":
                report["summary"]["stale"] += 1
                report["anomalies"].append({
                    "node_id": node_id,
                    "kind": "HEARTBEAT_STALE",
                    "seconds_ago": seconds_ago,
                    "remediation": f"請確認 {node_id} 之 Thin Client 守護進程是否維持運行",
                })
            else:
                report["summary"]["offline"] += 1
                report["anomalies"].append({
                    "node_id": node_id,
                    "kind": "NODE_OFFLINE",
                    "remediation": f"節點 {node_id} 處於離線狀態，若已棄用請自 Fabric 清理，若需恢復請執行 /join",
                })

            capabilities = list(node_info.get("capabilities", []))
            node_platform = node_info.get("platform") or "unknown"

            # 平台與能力常規檢驗
            if "vopc" in node_id.lower() or "win" in node_platform.lower():
                platform_type = "windows"
            elif "mbp" in node_id.lower() or "darwin" in node_platform.lower():
                platform_type = "macos"
            else:
                platform_type = "linux"

            report["nodes"][node_id] = {
                "node_id": node_id,
                "status": status,
                "platform_type": platform_type,
                "last_seen_at": last_seen,
                "seconds_ago": round(seconds_ago, 1) if seconds_ago is not None else None,
                "capabilities": capabilities,
                "token_registered": bool(node_info.get("token_hash")),
            }

        return report

    def dispatch_surface_alignment_probe(self, node_id: str) -> Dict[str, Any]:
        """向特定節點委派表面探測與環境校準任務."""
        task_id = f"align-probe-{int(datetime.now(timezone.utc).timestamp())}"
        task = {
            "schema": "agentos.node-task/v0.1",
            "task_id": task_id,
            "action": "agent.surface.inspect",
            "params": {},
        }
        return self.fabric_store.queue_task(node_id, task)


if __name__ == "__main__":
    engine = NodeAlignmentEngine()
    result = engine.audit_all_nodes()
    print(json.dumps(result, indent=2, ensure_ascii=False))
