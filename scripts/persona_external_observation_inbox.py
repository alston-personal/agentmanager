"""Import already verified Oracle public-post observations into Mio PDCA evidence inbox.

Read-only toward Threads; no IR mutation or interaction permission. Each source
must pass a strict schema/provenance/URL/author/content check.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import re

SCHEMA = "agentos.mio-external-public-observation/v1"
URL = re.compile(r"^/@([A-Za-z0-9._]{1,40})/post/[A-Za-z0-9_-]{1,40}$")


def validate(obj):
    if not isinstance(obj, dict) or obj.get("schema") != SCHEMA:
        return None
    if (obj.get("source") != "vendor-public-threads-reader" or
        obj.get("decision") != "UNDECIDED" or
        obj.get("reply_allowed") is not False or
        obj.get("ir_adoption_allowed") is not False or
        obj.get("write_performed") is not False):
        return None
    raw = obj.get("source_url")
    if not isinstance(raw, str) or len(raw) > 240:
        return None
    p = urlsplit(raw)
    m = URL.fullmatch(p.path)
    if p.scheme != "https" or p.netloc != "www.threads.com" or p.query or p.fragment or not m:
        return None
    author = obj.get("author")
    if not isinstance(author, str) or author.lower() != m.group(1).lower() or author.lower() == "mio.milkcat":
        return None
    body = obj.get("text")
    if not isinstance(body, str) or not 0 < len(body.strip()) <= 12000:
        return None
    observed = obj.get("observed_at")
    if not isinstance(observed, str) or not re.fullmatch(r"20\\d\\d-[01]\\d-[0-3]\\dT.{8,40}Z", observed):
        return None
    return {"schema": SCHEMA, "source": obj["source"], "source_url": raw, "author": author,
            "text": body.strip(), "observed_at": observed, "decision": "UNDECIDED",
            "reply_allowed": False, "ir_adoption_allowed": False, "write_performed": False}


def ingest(source_dir, persona_dir, limit=20):
    src, dst = Path(source_dir), Path(persona_dir) / "pdca" / "external_observation_inbox"
    result = {"schema": "agentos.mio-pdca-external-inbox/v1", "status": "PASS",
              "imported": 0, "already_seen": 0, "rejected": 0,
              "reply_allowed": False, "ir_adoption_allowed": False}
    if not src.is_dir():
        result["status"], result["reason"] = "BLOCKED", "SOURCE_DIRECTORY_MISSING"
        return result
    inputs = sorted(src.glob("*.json"))
    if len(inputs) > 500:
        result["status"], result["reason"] = "BLOCKED", "UNBOUNDED_SOURCE"
        return result
    for file in inputs[:limit]:
        try:
            if file.is_symlink() or file.stat().st_size > 16000:
                raise ValueError("invalid source file")
            data = validate(json.loads(file.read_text(encoding="utf-8")))
            if data is None:
                raise ValueError("unverified observation")
            digest = hashlib.sha256(data["source_url"].encode()).hexdigest()[:24]
            if file.stem != digest:
                raise ValueError("source filename mismatch")
            dst.mkdir(parents=True, exist_ok=True)
            target = dst / (digest + ".json")
            if target.exists():
                result["already_seen"] += 1
                continue
            with target.open("x", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, sort_keys=True)
                f.write("\\n")
            result["imported"] += 1
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            result["rejected"] += 1
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-dir", required=True)
    parser.add_argument("--persona-dir", required=True)
    args = parser.parse_args()
    print("mio_pdca_external_inbox_receipt=" + json.dumps(ingest(args.oracle_dir, args.persona_dir), sort_keys=True))


if __name__ == "__main__":
    main()
