#!/usr/bin/env python3
"""Pure source-generation and fail-closed acknowledgement contract for ONE.
No delivery, Git mutation, deployment, or authority is performed here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

EVENT="agentos.version-convergence-event/v1"
ACK="agentos.version-convergence-ack/v1"
SHA=re.compile(r"^[0-9a-f]{40}$")
ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
STATES={"NOTIFIED","SOURCE_CONVERGED","RUNTIME_DEPLOYED","TASK_RESUMED","BLOCKED"}

def stamp(value):
    if not isinstance(value,str): raise ValueError("invalid_timestamp")
    try: t=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as e: raise ValueError("invalid_timestamp") from e
    if not t.tzinfo: raise ValueError("timezone_required")
    return t.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def sha(value):
    if not isinstance(value,str) or not SHA.fullmatch(value): raise ValueError("invalid_sha")
    return value

def paths_valid(paths):
    if not isinstance(paths,list) or not 0<len(paths)<=1000: raise ValueError("invalid_paths")
    for p in paths:
        if not isinstance(p,str) or not 0<len(p)<=256 or p.startswith("/") or "\\" in p:
            raise ValueError("invalid_path")
        if any(x in ("", ".", "..") for x in p.split("/")) or any(ord(c)<32 for c in p):
            raise ValueError("invalid_path")
    return sorted(set(paths))

def affected_domains(paths):
    domains=set()
    for p in paths_valid(paths):
        if p.startswith(("agent_core/","runtime_core/","agentos_node/")): d="core"
        elif p.startswith((".github/workflows/","scripts/deploy_","scripts/install_")): d="release"
        elif p.startswith(("scripts/","tests/")): d="application"
        elif p.startswith(("docs/","governance/",".agentos/",".agent/")): d="governance"
        else: d="unclassified"
        domains.add(d)
    return sorted(domains)

def make_event(*,repository,main_sha,previous_sha,changed_paths,published_at,pr_number=None):
    if repository!="alston-personal/agentmanager": raise ValueError("repository_not_authorized")
    sha(main_sha); sha(previous_sha)
    if main_sha==previous_sha: raise ValueError("generation_not_advanced")
    if pr_number is not None and (type(pr_number)!=int or pr_number<1): raise ValueError("invalid_pr")
    paths=paths_valid(changed_paths)
    eid=hashlib.sha256((repository+"|"+main_sha).encode()).hexdigest()[:24]
    return {"schema":EVENT,"event_id":"main-"+eid,"repository":repository,
            "target_main_sha":main_sha,"previous_main_sha":previous_sha,
            "merged_pr":pr_number,"changed_paths":paths,"affected_domains":affected_domains(paths),
            "published_at":stamp(published_at),"authority":"protected_main_readback",
            "effect":"notify_only","execution_authorized":False}

def validate_ack(event,ack):
    """Validate shape, NOT issuer identity or actual Git/runtime provenance.
    ONE must independently attest both before accepting the claim.
    """
    if not isinstance(event,dict) or event.get("schema")!=EVENT or event.get("effect")!="notify_only":
        raise ValueError("invalid_event")
    if not isinstance(ack,dict) or ack.get("schema")!=ACK: raise ValueError("invalid_ack")
    if ack.get("event_id")!=event.get("event_id") or ack.get("target_main_sha")!=event.get("target_main_sha"):
        raise ValueError("event_mismatch")
    for key in ("executor_id","task_id"):
        if not isinstance(ack.get(key),str) or not ID.fullmatch(ack[key]):
            raise ValueError("invalid_identity")
    state=ack.get("state")
    if state not in STATES: raise ValueError("invalid_state")
    observed=ack.get("observed_base_sha")
    deployed=ack.get("deployed_source_sha")
    if observed is not None: sha(observed)
    if deployed is not None: sha(deployed)
    stamp(ack.get("acknowledged_at"))
    if ack.get("dirty_worktree_preserved") is not True: raise ValueError("unsafe_worktree")
    if ack.get("write_authorized") is not False: raise ValueError("ack_cannot_grant_write")
    if state in ("SOURCE_CONVERGED","RUNTIME_DEPLOYED","TASK_RESUMED") and observed!=event["target_main_sha"]:
        raise ValueError("source_not_converged")
    if state=="RUNTIME_DEPLOYED" and deployed!=event["target_main_sha"]:
        raise ValueError("runtime_not_attested")
    if state=="BLOCKED" and not isinstance(ack.get("reason"),str):
        raise ValueError("missing_block_reason")
    return dict(ack)

# A transport hint is NOT an install instruction.  This pure contract deliberately
# performs no network calls or code execution; ONE-owned bootstrap must validate
# identity, catalog signatures, policy, and provenance independently.
from urllib.parse import urlsplit

ADAPTER_HINT = "agentos.adapter-invalidation-hint/v1"
ADAPTER_PLAN = "agentos.adapter-reconciliation-plan/v1"
ADAPTER_ID = re.compile(r"^[a-z][a-z0-9._-]{0,95}$")
ADAPTER_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _adapter_version(value):
    if not isinstance(value, str) or not ADAPTER_VERSION.fullmatch(value):
        raise ValueError("invalid_adapter_version")
    return tuple(int(part) for part in value.split("."))


def validate_adapter_hint(hint, *, trusted_one_origin):
    """Validate untrusted locator shape, never grant download/install authority."""
    if not isinstance(hint, dict) or set(hint) != {
        "schema", "notice_epoch", "adapter_id", "adapter_url",
        "adapter_version", "adapter_sha256",
    } or hint.get("schema") != ADAPTER_HINT:
        raise ValueError("invalid_adapter_hint")
    if type(hint["notice_epoch"]) is not int or hint["notice_epoch"] < 1:
        raise ValueError("invalid_notice_epoch")
    if not isinstance(hint["adapter_id"], str) or not ADAPTER_ID.fullmatch(hint["adapter_id"]):
        raise ValueError("invalid_adapter_id")
    _adapter_version(hint["adapter_version"])
    if not isinstance(hint["adapter_sha256"], str) or not DIGEST.fullmatch(hint["adapter_sha256"]):
        raise ValueError("invalid_adapter_digest")
    origin = urlsplit(trusted_one_origin)
    target = urlsplit(str(hint["adapter_url"]))
    if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
            or origin.query or origin.fragment or origin.path not in ("", "/")):
        raise ValueError("invalid_trusted_one_origin")
    if (target.scheme != "https" or not target.hostname or target.username or target.password
            or target.query or target.fragment or not target.path.startswith("/")):
        raise ValueError("invalid_adapter_url")
    if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
        raise ValueError("untrusted_adapter_origin")
    if "%2f" in target.path.lower() or "/../" in target.path or "/./" in target.path:
        raise ValueError("unsafe_adapter_path")
    return dict(hint)


def plan_adapter_reconciliation(*, hint, trusted_one_origin, authoritative_manifest,
                                installed_version=None, installed_sha256=None):
    """Return a bounded plan; caller must fetch/attest ONE manifest independently.

    This method cannot approve install, download, or launch an adapter.
    """
    hint = validate_adapter_hint(hint, trusted_one_origin=trusted_one_origin)
    if not isinstance(authoritative_manifest, dict):
        raise ValueError("missing_one_adapter_manifest")
    required = {"adapter_id", "adapter_version", "adapter_url", "adapter_sha256", "approved"}
    if set(authoritative_manifest) != required or authoritative_manifest["approved"] is not True:
        raise ValueError("unapproved_one_adapter_manifest")
    for key in ("adapter_id", "adapter_version", "adapter_url", "adapter_sha256"):
        if authoritative_manifest[key] != hint[key]:
            raise ValueError("adapter_manifest_mismatch")
    newest = _adapter_version(hint["adapter_version"])
    current = _adapter_version(installed_version) if installed_version is not None else None
    if installed_sha256 is not None and (
            not isinstance(installed_sha256, str) or not DIGEST.fullmatch(installed_sha256)):
        raise ValueError("invalid_installed_digest")
    if current is not None and current > newest:
        action = "KEEP_NEWER_LOCAL_AND_VERIFY_COMPATIBILITY"
    elif current == newest and installed_sha256 == hint["adapter_sha256"]:
        action = "HANDLE_EVENT"
    else:
        action = "REQUEST_GOVERNED_ADAPTER_UPDATE"
    return {
        "schema": ADAPTER_PLAN, "adapter_id": hint["adapter_id"],
        "target_adapter_version": hint["adapter_version"],
        "notice_epoch": hint["notice_epoch"],
        "action": action, "installation_authorized": False,
        "handler_execution_authorized": False,
    }



# This pure contract cannot install or restart software.  Runtime preflight and
# recovery evidence MUST be independently attested by a trusted host authority.
ADAPTER_PREFLIGHT = "agentos.adapter-preflight-attestation/v1"
ADAPTER_INSTALL_PLAN = "agentos.adapter-install-gate/v1"
PREFLIGHT_CHECKS = frozenset({
    "signature", "digest", "provenance", "schema_compatibility",
    "platform_compatibility", "sandbox_smoke", "permissions",
    "recovery_independence", "rollback_snapshot",
})


def gate_adapter_install(*, plan, attestation, recovery):
    """Fail closed on missing preflight, unhealthy rescue lane, or stale plan.

    Result is advisory: the authorized OTA owner must independently validate
    the trusted attestations, install policy and live source/runtime evidence.
    """
    if not isinstance(plan, dict) or plan.get("schema") != ADAPTER_PLAN:
        raise ValueError("invalid_adapter_plan")
    if plan.get("action") != "REQUEST_GOVERNED_ADAPTER_UPDATE":
        raise ValueError("adapter_update_not_needed")
    if plan.get("installation_authorized") is not False:
        raise ValueError("invalid_install_authority")
    if not isinstance(attestation, dict) or attestation.get("schema") != ADAPTER_PREFLIGHT:
        raise ValueError("invalid_preflight_attestation")
    if (attestation.get("adapter_id"), attestation.get("adapter_version"),
            attestation.get("notice_epoch")) != (
            plan.get("adapter_id"), plan.get("target_adapter_version"),
            plan.get("notice_epoch")):
        raise ValueError("preflight_plan_mismatch")
    if attestation.get("trusted_source_attested") is not True:
        raise ValueError("preflight_untrusted_source")
    checks = attestation.get("checks")
    if (not isinstance(checks, dict) or set(checks) != PREFLIGHT_CHECKS
            or any(checks[name] is not True for name in PREFLIGHT_CHECKS)):
        raise ValueError("preflight_failed")
    if (not isinstance(recovery, dict)
            or recovery.get("independent_process") is not True
            or recovery.get("protected_from_adapter_update") is not True
            or recovery.get("one_handshake_verified") is not True
            or recovery.get("last_known_good_verified") is not True
            or recovery.get("rollback_ready") is not True):
        raise ValueError("recovery_lane_unavailable")
    return {
        "schema": ADAPTER_INSTALL_PLAN, "adapter_id": plan["adapter_id"],
        "adapter_version": plan["target_adapter_version"],
        "notice_epoch": plan["notice_epoch"],
        "action": "REQUEST_AUTHORIZED_STAGED_INSTALL",
        "installation_authorized": False, "activation_authorized": False,
        "recovery_preservation_required": True,
    }



# Deterministic update ordering guard. Durable locking, source attestation, and
# activation are ONLY performed by the independently authorized ONE runtime.
CHANNEL_STATE = "agentos.dual-channel-update-state/v1"
CHANNELS = frozenset({"normal", "recovery"})
PHASES = frozenset({"IDLE", "STAGED", "ACTIVATED", "ROLLBACK_REQUIRED", "HUMAN_REQUIRED"})
STAGES = frozenset({"BEGIN", "STAGED", "ACTIVATE", "VERIFY", "FAIL", "ROLLBACK_OK", "ROLLBACK_FAILED"})


def initial_channel_state(*, generation=0):
    if type(generation) is not int or generation < 0:
        raise ValueError("invalid_channel_generation")
    return {"schema": CHANNEL_STATE, "generation": generation,
            "active_lane": None, "phase": "IDLE", "operation_id": None,
            "last_verified_lane": None}


def reconcile_channel_update(*, state, stage, lane, operation_id, observed=None,
                             expected_generation):
    """Pure compare-and-swap transition for a single Participant.

    Observations are verified booleans provided by the host; this cannot
    authenticate observers, persist locks, restart a service or install code.
    """
    if not isinstance(state, dict) or set(state) != {
            "schema", "generation", "active_lane", "phase", "operation_id",
            "last_verified_lane"} or state.get("schema") != CHANNEL_STATE:
        raise ValueError("invalid_channel_state")
    if (type(state["generation"]) is not int or state["generation"] < 0
            or type(expected_generation) is not int
            or expected_generation != state["generation"]):
        raise ValueError("stale_channel_generation")
    if state["phase"] not in PHASES or stage not in STAGES or lane not in CHANNELS:
        raise ValueError("invalid_channel_transition")
    if (not isinstance(operation_id, str) or not ID.fullmatch(operation_id)):
        raise ValueError("invalid_channel_operation")
    if stage == "BEGIN":
        if state["phase"] != "IDLE" or state["active_lane"] is not None:
            raise ValueError("channel_update_busy")
        if not isinstance(observed, dict):
            raise ValueError("missing_channel_observations")
        # Updating normal requires a working independent rescue path.
        # Updating recovery requires both a working normal path AND a
        # protected previous rescue image throughout the switch.
        required = (
            ("recovery_one_handshake", "recovery_signed_manifest",
             "recovery_rollback_ready")
            if lane == "normal" else
            ("normal_one_handshake", "normal_recovery_download",
             "protected_recovery_slot_ready")
        )
        if any(observed.get(k) is not True for k in required):
            raise ValueError("fallback_lane_not_verified")
        return {**state, "generation": state["generation"] + 1,
                "active_lane": lane, "phase": "STAGED",
                "operation_id": operation_id}
    if state["active_lane"] != lane or state["operation_id"] != operation_id:
        raise ValueError("channel_operation_mismatch")
    phase = state["phase"]
    if stage == "STAGED":
        if phase != "STAGED" or not isinstance(observed, dict) or (
            observed.get("preflight_passed") is not True
            or observed.get("fallback_still_healthy") is not True):
            raise ValueError("channel_preflight_not_proven")
        # Stage confirmation does not give activation authority.
        return {**state, "generation": state["generation"] + 1}
    if stage == "ACTIVATE":
        if phase != "STAGED" or not isinstance(observed, dict) or (
            observed.get("preflight_passed") is not True
            or observed.get("fallback_still_healthy") is not True
            or observed.get("activation_separately_authorized") is not True):
            raise ValueError("activation_not_authorized_or_safe")
        return {**state, "generation": state["generation"] + 1,
                "phase": "ACTIVATED"}
    if stage == "VERIFY":
        if phase != "ACTIVATED" or not isinstance(observed, dict) or (
            observed.get("updated_lane_one_handshake") is not True
            or observed.get("updated_lane_signed_manifest") is not True
            or observed.get("fallback_still_healthy") is not True
            or observed.get("one_receipt_attested") is not True):
            raise ValueError("post_update_health_not_proven")
        return {**state, "generation": state["generation"] + 1,
                "phase": "IDLE", "active_lane": None, "operation_id": None,
                "last_verified_lane": lane}
    if stage == "FAIL":
        if phase not in ("STAGED", "ACTIVATED"):
            raise ValueError("invalid_failure_transition")
        return {**state, "generation": state["generation"] + 1,
                "phase": "ROLLBACK_REQUIRED"}
    if stage == "ROLLBACK_OK":
        if phase != "ROLLBACK_REQUIRED" or not isinstance(observed, dict) or (
            observed.get("fallback_still_healthy") is not True
            or observed.get("restored_lane_one_handshake") is not True
            or observed.get("one_rollback_receipt_attested") is not True):
            raise ValueError("rollback_not_verified")
        return {**state, "generation": state["generation"] + 1,
                "phase": "IDLE", "active_lane": None, "operation_id": None}
    if stage == "ROLLBACK_FAILED":
        if phase != "ROLLBACK_REQUIRED":
            raise ValueError("invalid_rollback_failure")
        return {**state, "generation": state["generation"] + 1,
                "phase": "HUMAN_REQUIRED"}
    raise ValueError("channel_update_blocked")


# Serialized, crash-persistent gate for a single-node ONE maintenance owner.
# This store does not authorize callers or produce trusted live observations.
import sqlite3


class DurableChannelUpdateStore:
    """SQLite compare-and-swap channel transitions; a crash never clears a lock.

    The ONE controller must authenticate the participant, independently verify
    evidence, and use a single shared database path for all update writers.
    """

    def __init__(self, database_path):
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("durable_update_store_required")
        parent = Path(self.database_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS dual_channel_updates ("
                "participant_id TEXT PRIMARY KEY, generation INTEGER NOT NULL,"
                "state_json TEXT NOT NULL)"
            )

    def _connect(self):
        conn = sqlite3.connect(self.database_path, timeout=30.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @staticmethod
    def _participant(participant_id):
        if not isinstance(participant_id, str) or not ID.fullmatch(participant_id):
            raise ValueError("invalid_participant_id")
        return participant_id

    def _get_or_initialize(self, conn, participant_id):
        row = conn.execute(
            "SELECT state_json FROM dual_channel_updates WHERE participant_id = ?",
            (participant_id,),
        ).fetchone()
        if row is None:
            initial = initial_channel_state()
            conn.execute(
                "INSERT INTO dual_channel_updates(participant_id,generation,state_json)"
                " VALUES (?,?,?)",
                (participant_id, 0, json.dumps(initial, sort_keys=True)),
            )
            return initial
        return json.loads(row[0])

    def inspect(self, *, participant_id):
        participant_id = self._participant(participant_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                state = self._get_or_initialize(conn, participant_id)
                conn.execute("COMMIT")
                return state
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def transition(self, *, participant_id, stage, lane, operation_id,
                   expected_generation, observed=None):
        participant_id = self._participant(participant_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                state = self._get_or_initialize(conn, participant_id)
                updated = reconcile_channel_update(
                    state=state, stage=stage, lane=lane,
                    operation_id=operation_id, observed=observed,
                    expected_generation=expected_generation,
                )
                conn.execute(
                    "UPDATE dual_channel_updates SET generation=?,state_json=?"
                    " WHERE participant_id=? AND generation=?",
                    (updated["generation"], json.dumps(updated, sort_keys=True),
                     participant_id, expected_generation),
                )
                if conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ValueError("stale_channel_generation")
                conn.execute("COMMIT")
                return updated
            except BaseException:
                conn.execute("ROLLBACK")
                raise


def main():
    parser=argparse.ArgumentParser()
    for name in ("main-sha","previous-sha","paths-file","published-at","output"):
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--pr-number",type=int)
    args=parser.parse_args()
    event=make_event(repository="alston-personal/agentmanager",main_sha=args.main_sha,
                     previous_sha=args.previous_sha,
                     changed_paths=Path(args.paths_file).read_text(encoding="utf-8").splitlines(),
                     published_at=args.published_at,pr_number=args.pr_number)
    Path(args.output).write_text(json.dumps(event,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"event_id":event["event_id"],"state":"CREATED_NOT_DELIVERED",
                      "target_main_sha":event["target_main_sha"],
                      "affected_domains":event["affected_domains"]},sort_keys=True))

if __name__=="__main__": main()
