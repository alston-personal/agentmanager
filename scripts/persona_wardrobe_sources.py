#!/usr/bin/env python3
"""Read-only adapter to the existing Mio garment owner; no catalog promotion."""
import hashlib
import json
import os
import re
import stat
from pathlib import Path

PERSONA_ID = "sunlake-milkcat-ai-001"
LOCATOR = "projects/dressup-simulator/garments/{seeded,imported}"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_registry():
    configured = os.environ.get("AGENTOS_MIO_GARMENT_DATA_ROOT")
    source = Path(configured) / "projects/dressup-simulator/garments" if configured else None
    records, record_digests, fingerprints, issues = {}, {}, [], set()
    counts = {"unscoped_records": 0, "other_persona_records": 0}
    directories = 0

    def no_symlinks(path):
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError("SYMLINK_SOURCE")

    def read_record(path):
        no_symlinks(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 131072:
                raise ValueError("INVALID_RECORD")
            data = stream.read(131073)
        if len(data) > 131072:
            raise ValueError("INVALID_RECORD")
        row = json.loads(data)
        if not isinstance(row, dict):
            raise ValueError("INVALID_RECORD")
        return row, digest(data)

    try:
        if source is None:
            raise ValueError("SOURCE_NOT_CONFIGURED")
        no_symlinks(source)
        for folder in ("seeded", "imported"):
            directory = source / folder
            no_symlinks(directory)
            if not directory.exists():
                continue
            if not directory.is_dir():
                issues.add("INVALID_DIRECTORY")
                continue
            directories += 1
            with os.scandir(directory) as entries:
                selected = []
                for entry in entries:
                    if len(selected) == 128:
                        issues.add("SOURCE_LIMIT")
                        break
                    selected.append(Path(entry.path))
            seen = set()
            for path in sorted(selected):
                if path.suffix != ".json":
                    continue
                try:
                    row, sha = read_record(path)
                    fingerprints.append((folder, path.name, sha))
                    key = row.get("garmentId") or row.get("garment_id")
                    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", key):
                        raise ValueError("INVALID_RECORD")
                    character = row.get("characterId") or row.get("character_id")
                    if not character:
                        counts["unscoped_records"] += 1
                        continue
                    if character != PERSONA_ID:
                        counts["other_persona_records"] += 1
                        continue
                    if key in seen:
                        issues.add("DUPLICATE_GARMENT_ID")
                    seen.add(key)
                    records[key], record_digests[key] = row, sha
                except (OSError, ValueError, TypeError):
                    issues.add("INVALID_RECORD")
    except (OSError, ValueError):
        issues.add("SOURCE_NOT_CONFIGURED" if source is None else "SOURCE_UNREADABLE")
    return {"locator": LOCATOR,
            "status": "NOT_CONFIGURED" if source is None else "PARTIAL" if issues else "OBSERVED" if directories else "DIRECTORIES_ABSENT",
            "issues": sorted(issues), **counts, "records": records, "record_digests": record_digests,
            "snapshot_sha256": digest(json.dumps(sorted(fingerprints), separators=(",", ":")).encode())}


def clean_label(value):
    if not isinstance(value, str):
        return None
    return "".join(c for c in value if c.isprintable()).strip()[:160] or None


def planning_sources(root, registry=None):
    """A bounded candidate projection, never an alternate truth catalog.

    An explicitly configured store wins even when empty/unreadable. Legacy
    compatibility applies only when no live store was configured at all.
    """
    registry = read_registry() if registry is None else registry
    result = {"schema": "agentos.persona-wardrobe-planning-sources/v1",
              "source_owner": "dressup-simulator", "registry_status": registry["status"],
              "source_snapshot_sha256": registry["snapshot_sha256"],
              "source_adapter_sha256": digest(Path(__file__).read_bytes()),
              "publication_allowed": False, "planning_only": True, "items": []}
    if registry["status"] == "NOT_CONFIGURED":
        result.update(source_owner="legacy_persona_catalog", status="LEGACY_ONLY")
        try:
            data = (Path(root) / "wardrobe/catalog.json").read_bytes()
            catalog = json.loads(data)
            items = catalog.get("items")
            if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
                raise ValueError("INVALID_CATALOG")
            result["source_snapshot_sha256"] = digest(data)
            for item in items:
                key = item.get("item_id")
                if (isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,200}", key)
                        and item.get("state") in ("candidate", "approved", "owned")
                        and clean_label(item.get("label"))):
                    result["items"].append({"item_id": key, "category": clean_label(item.get("category")) or "other",
                                            "label": clean_label(item["label"]), "state": item["state"]})
        except (OSError, ValueError, TypeError, AttributeError):
            result.update(status="HELD", items=[])
    elif registry["status"] == "OBSERVED":
        result["status"] = "OBSERVED"
        categories = {"upper_inner": "innerwear", "upper_main": "top", "upper_body": "top",
                      "upper_outer": "outerwear", "outerwear": "outerwear", "lower_main": "bottom",
                      "lower_body": "bottom", "onepiece": "dress", "dress": "dress", "shoes": "shoes",
                      "bag": "bag", "socks": "socks", "accessory_1": "accessories", "accessory_2": "accessories"}
        for key, row in sorted(registry["records"].items()):
            label = clean_label(row.get("name"))
            if not label:
                continue
            layer = row.get("layer") or row.get("slot")
            layer = layer if isinstance(layer, str) else "unknown"
            category = categories.get(layer, "other")
            result["items"].append({"item_id": key, "garment_id": key, "category": category,
                                    "layer": layer if layer in categories else "unknown", "label": label,
                                    "state": "candidate", "planning_only": True,
                                    "publication_source_eligible": False,
                                    "source_owner": "dressup-simulator",
                                    "record_sha256": registry["record_digests"][key]})
    else:
        result["status"] = "HELD"
    result["item_count"] = len(result["items"])
    result["items_truncated"] = len(result["items"]) > 24
    result["items"] = result["items"][:24]
    return result


def source_binding(projection):
    """Safe receipt provenance, without copying retailer URLs or raw metadata."""
    return {key: projection[key] for key in (
        "source_owner", "status", "registry_status", "source_snapshot_sha256",
        "source_adapter_sha256", "planning_only", "publication_allowed",
        "item_count", "items_truncated")}
