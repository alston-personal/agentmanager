"""Import already verified Oracle public-post observations into Mio PDCA evidence inbox.

Read-only toward Threads; no IR mutation or interaction permission. Each source
must pass a strict schema/provenance/URL/author/content check.
"""
import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import re

SCHEMA = "agentos.mio-external-public-observation/v1"
URL = re.compile(r"^/@([A-Za-z0-9._]{1,40})/post/[A-Za-z0-9_-]{1,40}$")
SHARE_URL = re.compile(r"^/share/[A-Za-z0-9_-]{1,80}/?$")


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
    if not isinstance(observed, str) or not re.fullmatch(r"20\d\d-[01]\d-[0-3]\dT.{8,40}Z", observed):
        return None
    return {"schema": SCHEMA, "source": obj["source"], "source_url": raw, "author": author,
            "text": body.strip(), "observed_at": observed, "decision": "UNDECIDED",
            "reply_allowed": False, "ir_adoption_allowed": False, "write_performed": False}



def _vendor_resolve_public(url):
    """Read existing localhost Vendor public Reader; never invoke social writes."""
    request = urllib.request.Request(
        "http://127.0.0.1:18766/v1/threads/resolve",
        data=json.dumps({"url": url}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=18) as response:
        return json.loads(response.read(65536).decode("utf-8"))


def observe_intel_urls(intel_file, source_dir, limit=2, resolver=None):
    """Reuse human-fed/trend URLs as read-only observations for the existing PDCA Inbox.

    Never treat a shortcode-derived intelligence candidate id as a provider
    parent id. Persist only independently read, public, bounded content.
    """
    result = {"schema": "agentos.mio-intel-url-observer/v1", "status": "PASS",
              "observed": 0, "already_seen": 0, "rejected": 0,
              "write_performed": False, "reply_allowed": False}
    try:
        loaded = json.loads(Path(intel_file).read_text(encoding="utf-8"))
        candidates = loaded.get("candidates") if isinstance(loaded, dict) else None
        if not isinstance(candidates, list) or len(candidates) > 500:
            raise ValueError("invalid intelligence queue")
    except FileNotFoundError:
        result.update(status="UNAVAILABLE", reason="INTEL_QUEUE_MISSING")
        return result
    except (OSError, ValueError, TypeError):
        result.update(status="BLOCKED", reason="INTEL_QUEUE_INVALID")
        return result
    if not isinstance(limit, int) or not 1 <= limit <= 5:
        raise ValueError("bounded observation limit required")
    resolver = resolver or _vendor_resolve_public
    output = Path(source_dir)
    visited = 0
    for item in candidates:
        if visited >= limit:
            break
        if not isinstance(item, dict) or item.get("status") != "pending_review":
            continue
        url = item.get("url")
        if not isinstance(url, str) or len(url) > 240:
            result["rejected"] += 1
            continue
        parsed = urlsplit(url)
        match = URL.fullmatch(parsed.path)
        share = SHARE_URL.fullmatch(parsed.path)
        if (parsed.scheme != "https" or parsed.netloc not in
                ("www.threads.com", "threads.com", "www.threads.net", "threads.net")
                or parsed.query or parsed.fragment or (not match and not share)):
            result["rejected"] += 1
            continue
        if match and match.group(1).casefold() == "mio.milkcat":
            result["rejected"] += 1
            continue
        request_url = "https://www.threads.com" + (
            parsed.path.rstrip("/") + "/" if share else parsed.path.rstrip("/"))
        if match:
            digest = hashlib.sha256(request_url.encode()).hexdigest()[:24]
            if (output / (digest + ".json")).exists():
                result["already_seen"] += 1
                continue
        visited += 1
        try:
            response = resolver(request_url)
            if (not isinstance(response, dict) or
                    response.get("schema") != "agentos.social.threads.public-post/v1" or
                    response.get("login_bypass_used") is not False or
                    response.get("anti_bot_bypass_used") is not False):
                raise ValueError("reader provenance invalid")
            source = response.get("source")
            if not isinstance(source, dict):
                raise ValueError("reader source missing")
            canonical = source.get("url")
            if not isinstance(canonical, str) or len(canonical) > 240:
                raise ValueError("reader canonical URL invalid")
            target_parts = urlsplit(canonical)
            resolved = URL.fullmatch(target_parts.path)
            if (target_parts.scheme != "https" or target_parts.netloc != "www.threads.com"
                    or target_parts.query or target_parts.fragment or not resolved):
                raise ValueError("reader canonical URL invalid")
            username = resolved.group(1)
            if (username.casefold() == "mio.milkcat"
                    or str(source.get("username") or "").casefold() != username.casefold()
                    or (match and (request_url != canonical or
                                  match.group(1).casefold() != username.casefold()))):
                raise ValueError("reader identity mismatch")
            digest = hashlib.sha256(canonical.encode()).hexdigest()[:24]
            target = output / (digest + ".json")
            if target.exists():
                result["already_seen"] += 1
                continue
            record = {"schema": SCHEMA, "source": "vendor-public-threads-reader",
                      "source_url": canonical, "author": username,
                      "text": source.get("text"),
                      "observed_at": datetime.now(timezone.utc).replace(
                          microsecond=0).isoformat().replace("+00:00", "Z"),
                      "decision": "UNDECIDED", "reply_allowed": False,
                      "ir_adoption_allowed": False, "write_performed": False}
            valid = validate(record)
            if valid is None:
                raise ValueError("source observation invalid")
            output.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as handle:
                json.dump(valid, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
            result["observed"] += 1
        except FileExistsError:
            result["already_seen"] += 1
        except (OSError, ValueError, TypeError, KeyError):
            result["rejected"] += 1
    return result


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
                f.write("\n")
            result["imported"] += 1
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            result["rejected"] += 1
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-dir", required=True)
    parser.add_argument("--persona-dir", required=True)
    parser.add_argument("--intel-file")
    args = parser.parse_args()
    if args.intel_file:
        print("mio_intel_url_observation_receipt=" + json.dumps(
            observe_intel_urls(args.intel_file, args.oracle_dir), sort_keys=True))
    print("mio_pdca_external_inbox_receipt=" + json.dumps(ingest(args.oracle_dir, args.persona_dir), sort_keys=True))


if __name__ == "__main__":
    main()
