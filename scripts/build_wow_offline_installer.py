"""Build a self-contained, allowlisted WoW offline Addon installer ZIP.

Not a signed/approved production release. Does not include Node credentials or
run any Bridge, game, or installer process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

FILES = (
    "scripts/WoW-AgentOS-Setup.cmd",
    "scripts/wow_agentos_install.ps1",
    "scripts/wow_agentos_installer_preflight.ps1",
    "integrations/wow/AgentOSWoW/AgentOSWoW.toc",
    "integrations/wow/AgentOSWoW/AgentOSWoW.lua",
    "integrations/wow/AgentOSWoW_R001/AgentOSWoW_R001.toc",
    "integrations/wow/AgentOSWoW_R001/Reply.lua",
)
PACKAGE_ROOT = "AgentOS-WoW-V1-preview"


def build(repo: Path, output: Path) -> tuple[Path, str]:
    repo = repo.resolve()
    output = output.resolve()
    records = {}
    content = {}
    for relative in FILES:
        path = repo / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("source_missing_or_symlink")
        data = path.read_bytes()
        if not data or len(data) > 1024 * 1024:
            raise ValueError("source_empty_or_oversized")
        content[relative] = data
        records[relative] = hashlib.sha256(data).hexdigest()
    manifest = {
        "schema": "agentos.wow.offline-installer-preview/v1",
        "release_status": "UNVERIFIED_PREVIEW_NOT_OFFICIAL",
        "files_sha256": records,
    }
    content["manifest.json"] = (json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ) + "\n").encode("ascii")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, data in sorted(content.items()):
            name = PACKAGE_ROOT + "/" + relative
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (output.parent / (output.name + ".sha256")).write_text(
        digest + "  " + output.name + "\n", encoding="ascii",
    )
    return output, digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, digest = build(args.repo, args.output)
    print("OFFLINE_PREVIEW_ZIP=" + str(output))
    print("SHA256=" + digest)


if __name__ == "__main__":
    main()
