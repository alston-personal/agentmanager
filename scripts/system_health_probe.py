#!/usr/bin/env python3
"""Unified system health, dynamic port manager and node fabric probe."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
PORT_REGISTRY = DATA_ROOT / "config" / "port_registry.json"
FABRIC_FILE = DATA_ROOT / "realm" / "fabric.json"


def check_ports_from_manager() -> tuple[bool, list[str]]:
    """Query port manager dynamically, verify active listening and L7 health where applicable."""
    findings = []
    all_ok = True

    if not PORT_REGISTRY.is_file():
        findings.append(f"⚠️ Port registry not found: {PORT_REGISTRY}")
        return True, findings

    try:
        registry = json.loads(PORT_REGISTRY.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append(f"❌ Failed to parse port registry: {exc}")
        return False, findings

    # Core critical ports that MUST be listening and healthy
    # Port -> (Project, Service Name, Optional L7 path, use_ssl, host_header)
    critical_services = {
        80: ("studio-milkcat-org", "Nginx HTTP Gateway", "/", False, "studio.milkcat.org"),
        443: ("studio-milkcat-org", "Nginx HTTPS Gateway", "/", True, "studio.milkcat.org"),
        3041: ("agentos-dashboard-green", "AgentOS Dashboard Green Slot", "/dashboard", False, "localhost"),
        8780: ("agentos-realm-fabric", "AgentOS ONE Realm Fabric", "/v1/health", False, "127.0.0.1"),
    }

    findings.append(f"📡 Port Manager: 共收錄 {len(registry)} 個登記連接埠")

    import ssl
    unverified_context = ssl._create_unverified_context()

    for port_str, info in sorted(registry.items(), key=lambda x: int(x[0])):
        port = int(port_str)
        proj = info.get("project", "unknown")

        # Check TCP connect
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            tcp_ok = (sock.connect_ex(("127.0.0.1", port)) == 0)

        if port in critical_services:
            svc_proj, svc_name, l7_path, use_ssl, host_header = critical_services[port]
            if not tcp_ok:
                findings.append(f"❌ 核心服務 :{port} ({svc_name}) TCP 連線失敗！")
                all_ok = False
                continue

            if l7_path:
                try:
                    scheme = "https" if use_ssl else "http"
                    url = f"{scheme}://127.0.0.1:{port}{l7_path}"
                    req = urllib.request.Request(url, headers={"User-Agent": "SystemHealthProbe/1.0", "Host": host_header})
                    ctx = unverified_context if use_ssl else None
                    with urllib.request.urlopen(req, timeout=2.0, context=ctx) as resp:
                        if resp.status in (200, 204, 301, 302, 308):
                            findings.append(f"✅ 核心服務 :{port} ({svc_name}) L7 業務健全 (HTTP {resp.status})")
                        else:
                            findings.append(f"❌ 核心服務 :{port} ({svc_name}) L7 響應異常: HTTP {resp.status}")
                            all_ok = False
                except Exception as exc:
                    findings.append(f"❌ 核心服務 :{port} ({svc_name}) L7 探測異常: {exc}")
                    all_ok = False
            else:
                findings.append(f"✅ 核心服務 :{port} ({svc_name}) TCP 監聽正常")
        else:
            # Non-critical registered services
            status_sym = "🟢" if tcp_ok else "⚪"
            # We don't fail for non-critical services (some might be on-demand or dev slots)

    return all_ok, findings


def check_node_heartbeats(max_idle_seconds: int = 300) -> tuple[bool, list[str]]:
    """Check heartbeat freshness of enrolled active nodes in realm fabric."""
    findings = []
    all_ok = True

    if not FABRIC_FILE.is_file():
        findings.append(f"⚠️ Realm Fabric file not found: {FABRIC_FILE}")
        return True, findings

    try:
        data = json.loads(FABRIC_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append(f"❌ Failed to parse fabric.json: {exc}")
        return False, findings

    nodes = data.get("nodes", {})
    now = datetime.now(timezone.utc)
    findings.append(f"🌐 Realm Fabric: 共收錄 {len(nodes)} 個註冊節點")

    # Nodes that are expected to be constantly online
    always_on_nodes = ["vopc5750", "dqa03backup", "dqa03restore", "oracle-exec"]

    for node_id in always_on_nodes:
        if node_id not in nodes:
            findings.append(f"⚠️ 常駐節點 [{node_id}] 未登記於 Fabric")
            continue

        node_info = nodes[node_id]
        last_seen = node_info.get("last_seen_at")
        if not last_seen:
            findings.append(f"❌ 常駐節點 [{node_id}] 從未記錄心跳！")
            all_ok = False
            continue

        try:
            dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            age_sec = (now - dt).total_seconds()
            if age_sec > max_idle_seconds:
                findings.append(f"❌ 常駐節點 [{node_id}] 心跳逾時！已失聯 {age_sec:.0f}s (> {max_idle_seconds}s)")
                all_ok = False
            else:
                findings.append(f"✅ 常駐節點 [{node_id}] 心跳正常 (最後心跳: {age_sec:.0f}s 前)")
        except Exception as exc:
            findings.append(f"❌ 常駐節點 [{node_id}] 心跳解析失敗: {exc}")
            all_ok = False

    return all_ok, findings


def main():
    parser = argparse.ArgumentParser(description="AgentOS Comprehensive System & Node Health Probe")
    parser.add_argument("--check-all", action="store_true", help="Run full L7 and heartbeat probe")
    parser.add_argument("--json", action="store_true", help="Output JSON result")
    args = parser.parse_args()

    ports_ok, port_findings = check_ports_from_manager()
    nodes_ok, node_findings = check_node_heartbeats()

    total_ok = ports_ok and nodes_ok

    if args.json:
        res = {
            "ok": total_ok,
            "ports_ok": ports_ok,
            "nodes_ok": nodes_ok,
            "port_findings": port_findings,
            "node_findings": node_findings,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("=== 🛠️ AgentOS System & Node Fabric Health Probe ===")
        for f in port_findings:
            print(f)
        print("--- 🌐 跨機心跳健康巡檢 ---")
        for f in node_findings:
            print(f)
        print("================================================")
        print(f"整體健康結論: {'PASS' if total_ok else 'FAIL'}")

    sys.exit(0 if total_ok else 1)


if __name__ == "__main__":
    main()
