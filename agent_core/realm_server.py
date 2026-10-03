from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import socket
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.request

from agent_core.controller_api import ControllerService as RuntimeControllerService
from agent_core.controller_service import ControllerService as LegacyControllerService
from agent_core.node_bootstrap import bootstrap_snapshot, record_join_regression
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.resolve_facade import resolve_continuation
from agent_core.active_continuation import resolve_active_continuation, active_continuation_identity
from agent_core.runtime_converge_capability import installed_core_capabilities
from agent_core.runner_window import catalog as runner_window_catalog, public_intent_for_action, resolve_intent
from agentos_node import bootstrap_control as bootstrap_control
from agentos_node.bootstrap_scheduler import policy_for as bootstrap_policy_for


_GITHUB_OIDC_ISSUER = 'https://token.actions.githubusercontent.com'
_GITHUB_OIDC_JWKS = 'https://token.actions.githubusercontent.com/.well-known/jwks'
_GITHUB_SCHEDULER_AUDIENCE = 'agentos-scheduler'
_GITHUB_SCHEDULER_REPOSITORY = 'alston-personal/agentmanager'
_GITHUB_SCHEDULER_REF = 'refs/heads/core/integration'
_GITHUB_JWKS_CACHE: dict[str, Any] = {'expires_at': 0.0, 'keys': {}}
_GITHUB_JWKS_LOCK = threading.Lock()
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex('3031300d060960864801650304020105000420')


def _b64url_decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


def _github_jwks(*, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    now = time.time()
    with _GITHUB_JWKS_LOCK:
        if not force_refresh and now < float(_GITHUB_JWKS_CACHE.get('expires_at') or 0):
            cached = _GITHUB_JWKS_CACHE.get('keys') or {}
            if cached:
                return dict(cached)
        request = urllib.request.Request(
            _GITHUB_OIDC_JWKS,
            headers={'Accept': 'application/json', 'User-Agent': 'AgentOS-ONE/0.1'},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.load(response)
        keys = {
            str(item.get('kid') or ''): item
            for item in (payload.get('keys') or [])
            if isinstance(item, dict) and item.get('kid')
        }
        if not keys:
            raise PermissionError('github oidc jwks unavailable')
        _GITHUB_JWKS_CACHE['keys'] = keys
        _GITHUB_JWKS_CACHE['expires_at'] = now + 600
        return dict(keys)


def _verify_rs256(signing_input: bytes, signature: bytes, jwk: dict[str, Any]) -> None:
    if jwk.get('kty') != 'RSA':
        raise PermissionError('github oidc key type invalid')
    try:
        n = int.from_bytes(_b64url_decode(str(jwk['n'])), 'big')
        e = int.from_bytes(_b64url_decode(str(jwk['e'])), 'big')
    except Exception as exc:
        raise PermissionError('github oidc rsa key invalid') from exc
    if n.bit_length() < 2048 or e < 3:
        raise PermissionError('github oidc rsa key too weak')
    width = (n.bit_length() + 7) // 8
    if len(signature) != width:
        raise PermissionError('github oidc signature length invalid')
    recovered = pow(int.from_bytes(signature, 'big'), e, n).to_bytes(width, 'big')
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(signing_input).digest()
    padding_len = width - len(digest_info) - 3
    if padding_len < 8:
        raise PermissionError('github oidc signature encoding invalid')
    expected = b'\x00\x01' + (b'\xff' * padding_len) + b'\x00' + digest_info
    if not secrets.compare_digest(recovered, expected):
        raise PermissionError('github oidc signature invalid')


def _validate_github_scheduler_claims(payload: dict[str, Any]) -> None:
    now = int(time.time())
    if payload.get('iss') != _GITHUB_OIDC_ISSUER:
        raise PermissionError('github oidc issuer invalid')
    audience = payload.get('aud')
    audiences = {str(audience)} if isinstance(audience, str) else {str(x) for x in (audience or [])}
    if _GITHUB_SCHEDULER_AUDIENCE not in audiences:
        raise PermissionError('github oidc audience invalid')
    if payload.get('repository') != _GITHUB_SCHEDULER_REPOSITORY:
        raise PermissionError('github oidc repository invalid')
    if payload.get('ref') != _GITHUB_SCHEDULER_REF:
        raise PermissionError('github oidc ref invalid')
    if str(payload.get('event_name') or '') not in {'push', 'workflow_dispatch', 'schedule'}:
        raise PermissionError('github oidc event invalid')
    sha = str(payload.get('sha') or '')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise PermissionError('github oidc sha invalid')
    try:
        exp = int(payload.get('exp'))
        iat = int(payload.get('iat'))
        nbf = int(payload.get('nbf', iat))
    except (TypeError, ValueError) as exc:
        raise PermissionError('github oidc time claims invalid') from exc
    if exp <= now - 10 or nbf > now + 30 or iat > now + 30:
        raise PermissionError('github oidc token outside validity window')
    if exp - iat > 900 or now - iat > 900:
        raise PermissionError('github oidc token lifetime invalid')


def _verify_github_scheduler_oidc(token: str) -> dict[str, Any]:
    parts = token.split('.')
    if len(parts) != 3:
        raise PermissionError('github oidc token malformed')
    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except Exception as exc:
        raise PermissionError('github oidc token decode failed') from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise PermissionError('github oidc token payload invalid')
    if header.get('alg') != 'RS256':
        raise PermissionError('github oidc algorithm invalid')
    kid = str(header.get('kid') or '')
    if not kid:
        raise PermissionError('github oidc kid missing')
    keys = _github_jwks()
    key = keys.get(kid)
    if key is None:
        key = _github_jwks(force_refresh=True).get(kid)
    if key is None:
        raise PermissionError('github oidc signing key unknown')
    _verify_rs256(f'{parts[0]}.{parts[1]}'.encode('ascii'), signature, key)
    _validate_github_scheduler_claims(payload)
    return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _core_node_manifest(realm_id: str) -> dict[str, Any]:
    node_id = str(os.environ.get('AGENTOS_CORE_NODE_ID') or 'oracle-core-node').strip()
    if not node_id:
        raise ValueError('AGENTOS_CORE_NODE_ID cannot be empty')
    tools = {name: bool(shutil.which(name)) for name in ('git', 'python3', 'curl', 'systemctl')}
    capabilities = ['agentos.governance.read', 'agentos.one.resolve', 'agentos.realm.fabric']
    capabilities.extend(capability for capability in installed_core_capabilities() if capability not in capabilities)
    return {
        'schema': 'agentos.node-manifest/v0.1',
        'realm_id': realm_id,
        'node_id': node_id,
        'role': 'core',
        'hostname': socket.gethostname(),
        'platform': platform.system(),
        'platform_release': platform.release(),
        'capabilities': capabilities,
        'tool_presence': tools,
        'surface_inventory': {'surfaces': []},
        'observed_at': _utc_now(),
    }


def _core_node_heartbeat(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        'schema': 'agentos.node-heartbeat/v0.1',
        'realm_id': manifest['realm_id'],
        'node_id': manifest['node_id'],
        'status': 'online',
        'observed_at': _utc_now(),
        'uptime_seconds': None,
        'surface_count': len((manifest.get('surface_inventory') or {}).get('surfaces') or []),
        'manifest': {**manifest, 'observed_at': _utc_now()},
    }


def _run_core_node_heartbeat(registry: NodeRegistry, manifest: dict[str, Any], stop: threading.Event) -> None:
    interval = max(5, int(os.environ.get('AGENTOS_CORE_HEARTBEAT_SECONDS', '10')))
    while not stop.is_set():
        try:
            registry.record_heartbeat(_core_node_heartbeat(manifest))
        except Exception:
            pass
        stop.wait(interval)


class RealmRequestHandler(BaseHTTPRequestHandler):
    server_version = 'AgentOS-ONE/0.1'

    @property
    def fabric(self) -> RealmFabricStore:
        return self.server.fabric  # type: ignore[attr-defined]

    @property
    def controller(self) -> RuntimeControllerService:
        return self.server.controller  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        return super().log_message(fmt, *args)

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length) if length else b'{}'
        try:
            payload = json.loads(raw.decode('utf-8'))
        except Exception as exc:
            raise ValueError(f'invalid JSON body: {exc}') from exc
        if not isinstance(payload, dict):
            raise ValueError('JSON body must be an object')
        return payload

    def _bearer(self) -> str:
        value = self.headers.get('Authorization') or ''
        prefix = 'Bearer '
        if not value.startswith(prefix):
            raise PermissionError('missing bearer credential')
        return value[len(prefix):].strip()

    def _authorize_controller(self) -> None:
        expected = str(getattr(self.server, 'controller_token', '') or '')  # type: ignore[attr-defined]
        if not expected:
            raise PermissionError('controller API disabled')
        supplied = self._bearer()
        if not secrets.compare_digest(supplied, expected):
            raise PermissionError('invalid controller credential')

    def _authorize_scheduler(self) -> dict[str, Any] | None:
        supplied = self._bearer()
        expected = str(getattr(self.server, 'controller_token', '') or '')  # type: ignore[attr-defined]
        if expected and secrets.compare_digest(supplied, expected):
            return None
        return _verify_github_scheduler_oidc(supplied)

    def _runner_window_submit(self, body: dict[str, Any]) -> dict[str, Any]:
        if body.get('schema') != 'agentos.runner-window-dispatch/v1':
            raise ValueError('invalid runner window dispatch schema')
        capability = str(body.get('capability') or '').strip()
        operation = str(body.get('operation') or '').strip()
        source_commit = str(body.get('source_commit') or '').strip()
        if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
            raise ValueError('source_commit must be an exact lowercase 40-hex commit SHA')
        payload = body.get('payload') or {}
        if not isinstance(payload, dict):
            raise ValueError('payload must be an object')
        intent, params = resolve_intent(
            capability,
            operation,
            source_commit=source_commit,
            payload=payload,
        )
        scheduler_body = {
            'schema': 'agentos.scheduler-submit/v1',
            'action': intent.action,
            'params': params,
        }
        request_id = str(body.get('request_id') or '').strip()
        if request_id:
            scheduler_body['request_id'] = request_id
        result = self._scheduler_submit(scheduler_body)
        scheduler = result.get('scheduler') or {}
        return {
            'ok': result.get('ok') is True,
            'state': result.get('state'),
            'request_id': result.get('request_id'),
            'dispatch': {
                'schema': 'agentos.runner-window-plan/v1',
                'capability': intent.capability,
                'operation': intent.operation,
                'role': scheduler.get('role'),
                'priority': scheduler.get('priority'),
                'requested_capabilities': scheduler.get('requested_capabilities') or [],
                'locks': scheduler.get('locks') or [],
            },
        }

    def _runner_window_status(self, request_id: str) -> dict[str, Any]:
        result = self._scheduler_status(request_id)
        receipt = result.get('receipt')
        action = str((receipt or {}).get('action') or '')
        public = public_intent_for_action(action)
        projected = {
            'ok': result.get('ok') is True,
            'state': result.get('state'),
            'request_id': result.get('request_id'),
        }
        if public is not None:
            projected['dispatch'] = {
                'schema': 'agentos.runner-window-plan/v1',
                **public,
            }
        if isinstance(receipt, dict):
            clean = dict(receipt)
            clean.pop('action', None)
            projected['receipt'] = clean
        return projected

    def _scheduler_submit(self, body: dict[str, Any]) -> dict[str, Any]:
        if body.get('schema') != 'agentos.scheduler-submit/v1':
            raise ValueError('invalid scheduler submit schema')
        action = str(body.get('action') or '').strip()
        if action not in bootstrap_control.ALLOWED_ACTIONS:
            raise ValueError('action is not allowlisted')
        params = body.get('params') or {}
        if not isinstance(params, dict):
            raise ValueError('params must be an object')
        allowed_params = {'source_commit'}
        if action == bootstrap_control.ACTION_PUBLISH_MIO_APPROVED:
            allowed_params |= {'post_key'}
        elif action == bootstrap_control.ACTION_RUN_MIO_DM_DECISION:
            allowed_params |= {'source_run_id', 'username'}
        elif action == bootstrap_control.ACTION_DEPLOY_STUDIO_WEB_MIO:
            allowed_params |= {'studio_commit'}
        elif action == bootstrap_control.ACTION_NODE_TRANSACTIONAL_OTA:
            allowed_params |= {'node_id', 'candidate_commit'}
        elif action == bootstrap_control.ACTION_EXECUTOR_JOB_SUBMIT:
            allowed_params |= {'job_type'}
        elif action == bootstrap_control.ACTION_EXECUTOR_JOB_INSPECT:
            allowed_params |= {'job_id'}
        unknown = set(params) - allowed_params
        if unknown:
            raise ValueError(f'unsupported scheduler params: {sorted(unknown)}')
        source_commit = str(params.get('source_commit') or '').strip()
        if action != bootstrap_control.ACTION_REPAIR_TRANSPORT:
            if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
                raise ValueError('source_commit must be an exact lowercase 40-hex commit SHA')
        elif source_commit and not re.fullmatch(r'[0-9a-f]{40}', source_commit):
            raise ValueError('source_commit must be an exact lowercase 40-hex commit SHA')
        request_id = str(body.get('request_id') or '').strip()
        if request_id:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,159}', request_id):
                raise ValueError('invalid request_id')
        else:
            slug = re.sub(r'[^A-Za-z0-9._-]+', '-', action).strip('-')[:80] or 'scheduler'
            request_id = f'{slug}-{int(datetime.now(timezone.utc).timestamp())}-{secrets.token_hex(4)}'
        requests, receipts, _ = bootstrap_control._ensure(bootstrap_control._root())
        receipt_path = receipts / f'{request_id}.json'
        request_path = requests / f'{request_id}.request.json'
        if receipt_path.exists():
            return {'ok': True, 'state': 'completed', 'request_id': request_id}
        if request_path.exists():
            return {'ok': True, 'state': 'queued', 'request_id': request_id}
        payload = {
            'schema': bootstrap_control.SCHEMA,
            'request_id': request_id,
            'action': action,
            'created_at': _utc_now(),
            'params': dict(params),
            'authority': {
                'source': 'realm-controller',
                'target_user': 'ubuntu',
                'arbitrary_shell': False,
            },
        }
        bootstrap_control._atomic_json(request_path, payload)
        policy = bootstrap_policy_for(action)
        return {
            'ok': True,
            'state': 'queued',
            'request_id': request_id,
            'action': action,
            'scheduler': {
                'role': policy.role,
                'priority': policy.priority_label,
                'requested_capabilities': list(policy.capabilities),
                'locks': list(policy.locks),
            },
        }

    def _scheduler_status(self, request_id: str) -> dict[str, Any]:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,159}', request_id):
            raise KeyError(request_id)
        root = bootstrap_control._root()
        requests, receipts, rejected = bootstrap_control._ensure(root)
        receipt_path = receipts / f'{request_id}.json'
        if receipt_path.exists():
            raw = json.loads(receipt_path.read_text(encoding='utf-8'))
            action = str(raw.get('action') or '')
            safe_prefixes: tuple[str, ...] = ()
            if action == bootstrap_control.ACTION_RUNNER_WINDOW_PROBE:
                safe_prefixes = ('runner_window_probe=',)
            elif action == bootstrap_control.ACTION_RELAY_RESTART:
                safe_prefixes = (
                    'relay_restart_service=',
                    'relay_restart=',
                )
            elif action == bootstrap_control.ACTION_SCHEDULER_STATUS:
                safe_prefixes = (
                    'scheduler_status_pending_count=',
                    'scheduler_status_pending_oldest_seconds=',
                    'scheduler_status_stalled_count=',
                    'scheduler_status_receipts_count=',
                    'scheduler_status_rejected_count=',
                    'scheduler_status=',
                )
            elif action == bootstrap_control.ACTION_RELAY_STATUS:
                safe_prefixes = (
                    'relay_status_antigravity_service=',
                    'relay_status_action_service=',
                    'relay_status_inbox_count=',
                    'relay_status_processing_count=',
                    'relay_status_receipts_count=',
                    'relay_status_inbox_oldest_seconds=',
                    'relay_status_processing_oldest_seconds=',
                    'relay_status=',
                )
            elif action == bootstrap_control.ACTION_NODE_TRANSACTIONAL_OTA:
                safe_prefixes = (
                    'node_ota_stage_task=',
                    'node_ota_stage_receipt=',
                    'node_ota_controller_acceptance=',
                    'node_ota_finalize_task=',
                    'node_ota_finalize_receipt=',
                    'node_ota_rollback_task=',
                    'node_ota_rollback_receipt=',
                    'node_ota_target=',
                    'node_ota_candidate_commit=',
                    'node_ota=',
                )
            elif action == bootstrap_control.ACTION_DEPLOY_SOCIAL_RUNTIME:
                safe_prefixes = (
                    'social_runtime_deploy=',
                    'social_runtime_service_identity=',
                    'social_runtime_root_privilege=',
                    'social_gateway_route_guard=',
                    'social_gateway_dashboard_build=',
                    'social_gateway_local=',
                    'social_gateway_internal_control_public=',
                    'social_gateway_public=',
                    'social_gateway_nginx_mutation=',
                    'social_runtime_source_commit=',
                )
            elif action == bootstrap_control.ACTION_PUBLISH_MIO_APPROVED:
                safe_prefixes = (
                    'galaxy_day1_username=',
                    'galaxy_day1_object_id=',
                    'galaxy_day1_permalink=',
                    'galaxy_day1_publish=',
                    'galaxy_day1_image_readback=',
                    'galaxy_day1_image_asset=',
                )
            elif action == bootstrap_control.ACTION_PROBE_PERSONA_PDCA_RUNTIME:
                safe_prefixes = (
                    'persona_pdca_heartbeat_present=',
                    'persona_pdca_heartbeat_sha256=',
                    'persona_pdca_heartbeat_generic_markers=',
                    'persona_pdca_heartbeat_legacy_mio_markers=',
                    'persona_pdca_heartbeat_oursong_markers=',
                    'persona_pdca_heartbeat_data_path_markers=',
                    'persona_pdca_runtime_unit=',
                    'persona_pdca_runtime_directive=',
                    'persona_pdca_runtime_file=',
                    'persona_pdca_runtime_sha256=',
                    'persona_pdca_runtime_units_found=',
                    'persona_pdca_runtime_probe=',
                )
            elif action == bootstrap_control.ACTION_PROBE_OURSONG_PERSONA:
                safe_prefixes = (
                    'oursong_status=',
                    'oursong_runtime_release=',
                    'oursong_runtime_source_commit=',
                    'oursong_pdca_cycle=',
                    'oursong_pdca_status=',
                    'oursong_last_tick_at=',
                    'oursong_last_action_at=',
                    'ActiveState=',
                    'UnitFileState=',
                    'LastTriggerUSec=',
                    'NextElapseUSecRealtime=',
                )
            elif action == bootstrap_control.ACTION_REPAIR_TRANSPORT:
                safe_prefixes = (
                    'antigravity_repair_stage=',
                    'antigravity_repair_exit=',
                    'antigravity_repair_line=',
                    'antigravity_repair=',
                    'agentos_source_ref=',
                    'agentos_source_commit=',
                    'action_relay_install=',
                    'action_relay_source_generation_pinned=',
                    'realm_fabric_install=',
                    'realm_fabric_runtime_closure=',
                )
            elif action == bootstrap_control.ACTION_RECONCILE_CONTENT_SOCIAL:
                safe_prefixes = (
                    'content_social_converge=',
                    'action_relay_generation=',
                    'content_social_bootstrap_status=',
                    'content_social_bootstrap_username=',
                    'content_social_product_registration=',
                    'content_social_bootstrap=',
                    'content_social_inspect_status=',
                    'content_social_username=',
                    'content_social_write_entitlement=',
                    'content_social_account_inspect=',
                    'content_social_reconcile=',
                )
            evidence: list[str] = []
            failed_steps: list[dict[str, Any]] = []
            for step in raw.get('steps') or []:
                if not isinstance(step, dict):
                    continue
                returncode = step.get('returncode')
                if isinstance(returncode, int) and returncode != 0:
                    failed_steps.append({
                        'step': str(step.get('step') or 'unknown')[:80],
                        'returncode': returncode,
                    })
            if safe_prefixes:
                for step in raw.get('steps') or []:
                    if not isinstance(step, dict):
                        continue
                    for line in str(step.get('stdout') or '').splitlines():
                        clean = line.strip()
                        if any(clean.startswith(prefix) for prefix in safe_prefixes):
                            evidence.append(clean[:1000])
            public_receipt: dict[str, Any] = {
                'schema': raw.get('schema'),
                'action': action,
                'source_commit': raw.get('source_commit'),
                'ok': raw.get('ok'),
                'failure_class': raw.get('failure_class'),
                'error': str(raw.get('error') or '')[:400] or None,
                'completed_at': raw.get('completed_at'),
                'scheduler': raw.get('scheduler'),
                'evidence': evidence[:32],
                'failed_steps': failed_steps[:8],
            }
            if action == bootstrap_control.ACTION_EXECUTOR_JOB_SUBMIT:
                submission = raw.get('executor_job')
                if isinstance(submission, dict):
                    allowed = (
                        'schema', 'ok', 'state', 'job_id', 'node_id', 'job_type',
                        'project_id', 'executor_class', 'capability', 'reused',
                        'credential_exposed',
                    )
                    public_receipt['executor_job'] = {
                        key: submission.get(key)
                        for key in allowed
                        if key in submission
                    }
            elif action == bootstrap_control.ACTION_EXECUTOR_JOB_INSPECT:
                state = raw.get('executor_job_state')
                if isinstance(state, str):
                    public_receipt['executor_job_state'] = state[:32]
                job_receipt = raw.get('executor_job_receipt')
                if isinstance(job_receipt, dict):
                    allowed = (
                        'schema', 'job_id', 'job_type', 'project_id', 'executor_class',
                        'capability', 'executor_available', 'routable', 'authorized',
                        'successful', 'credential_exposed', 'experiment_id', 'verdict',
                        'baseline_score', 'hydrated_score', 'uplift',
                        'hydration_receipt_ok', 'install_receipt_ok', 'classification',
                        'executor_returncode', 'executor_timed_out', 'executor_provider',
                        'worktree_clean', 'observed_head',
                        'claude_liveness', 'claude_state', 'claude_returncode', 'claude_timed_out',
                        'claude_ready_count', 'claude_probe_attempts',
                        'agy_liveness', 'agy_state', 'agy_returncode', 'agy_timed_out',
                        'agy_ready_count', 'agy_probe_attempts',
                        'selected_provider',
                    )
                    public_receipt['executor_job_receipt'] = {
                        key: job_receipt.get(key)
                        for key in allowed
                        if key in job_receipt
                    }
            return {
                'ok': True,
                'state': 'completed',
                'request_id': request_id,
                'receipt': public_receipt,
            }
        request_path = requests / f'{request_id}.request.json'
        if request_path.exists():
            return {'ok': True, 'state': 'queued', 'request_id': request_id}
        for inflight in ((root / 'inflight').glob(f'*/{request_id}.request.json') if (root / 'inflight').exists() else []):
            if inflight.exists():
                return {'ok': True, 'state': 'running', 'request_id': request_id}
        rejected_path = rejected / f'{request_id}.request.json'
        if rejected_path.exists():
            return {'ok': True, 'state': 'rejected', 'request_id': request_id}
        raise KeyError(request_id)

    def _send(self, status: int, payload: dict[str, Any] | list[Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, PermissionError):
            code = HTTPStatus.UNAUTHORIZED
        elif isinstance(exc, KeyError):
            code = HTTPStatus.NOT_FOUND
        elif isinstance(exc, ValueError):
            code = HTTPStatus.BAD_REQUEST
        else:
            code = HTTPStatus.INTERNAL_SERVER_ERROR
        self._send(int(code), {'ok': False, 'error': f'{type(exc).__name__}: {exc}'})

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == '/v1/health':
                data = self.fabric.load()
                self._send(200, {'ok': True, 'schema': 'agentos.one-health/v0.1', 'realm_id': data.get('realm_id')})
                return
            if parsed.path == '/v1/tasks':
                query = parse_qs(parsed.query)
                node_id = (query.get('node_id') or [''])[0]
                token = self._bearer()
                tasks = self.fabric.pull_tasks(node_id, token)
                self._send(200, {'ok': True, 'tasks': tasks})
                return
            if parsed.path == '/v1/bootstrap':
                query = parse_qs(parsed.query)
                node_id = (query.get('node_id') or [''])[0]
                token = self._bearer()
                snapshot = bootstrap_snapshot(self.fabric, node_id, token)
                self._send(200, {'ok': True, **snapshot})
                return
            if parsed.path == '/v1/controller/realm':
                self._authorize_controller()
                self._send(200, {'ok': True, 'realm': self.controller.realm()})
                return
            if parsed.path in ('/v1/controller/continuation/active', '/v1/controller/continuation/active/identity'):
                self._authorize_controller()
                # The caller cannot choose a workspace, path or another selector.
                if parsed.query:
                    self._send(400, {'ok': False, 'error': 'unsupported_continuation_query'})
                    return
                try:
                    active = resolve_active_continuation()
                    identity = active_continuation_identity(active)
                    if parsed.path.endswith('/identity'):
                        self._send(200, {'ok': True, 'identity': identity})
                    else:
                        # Reuse the existing credential-isolated executor projection.
                        from agentos_node.one_mcp import _project_resolve
                        resolution = _project_resolve(active['resolution'])
                        original_ir = active['resolution'].get('continuation', {}).get('canonical_ir')
                        if not isinstance(original_ir, dict) or resolution['continuation']['canonical_ir'] != original_ir:
                            raise ValueError('canonical IR cannot be projected losslessly')
                        self._send(200, {
                            'ok': True, 'schema': 'agentos.one-active-resolve/v1',
                            'source': 'ONE_ACTIVE_CONTINUATION',
                            'selector': {key: identity[key] for key in ('project_id', 'index_id', 'ir_id')},
                            'resolution': resolution,
                            'credential_exposed': False,
                        })
                except Exception:
                    # No paths, private IR or resolver exception text on failure.
                    self._send(409, {'ok': False, 'error': 'ONE_IR_HEAD_UNRESOLVED'})
                return
            if parsed.path == '/v1/controller/nodes':
                self._authorize_controller()
                self._send(200, {'ok': True, 'node_map': self.controller.nodes()})
                return
            if parsed.path == '/v1/dispatch':
                self._authorize_scheduler()
                self._send(200, {
                    'ok': True,
                    'schema': 'agentos.runner-window/v1',
                    'intents': runner_window_catalog(),
                    'runner_pool': self.controller.scheduler(),
                })
                return
            dispatch_request_prefix = '/v1/dispatch/requests/'
            if parsed.path.startswith(dispatch_request_prefix):
                self._authorize_scheduler()
                request_id = parsed.path.removeprefix(dispatch_request_prefix).strip('/')
                if not request_id or '/' in request_id:
                    raise KeyError(parsed.path)
                self._send(200, self._runner_window_status(request_id))
                return
            if parsed.path == '/v1/controller/scheduler':
                self._authorize_scheduler()
                self._send(200, {'ok': True, 'runner_pool': self.controller.scheduler()})
                return
            scheduler_request_prefix = '/v1/controller/scheduler/requests/'
            if parsed.path.startswith(scheduler_request_prefix):
                self._authorize_scheduler()
                request_id = parsed.path.removeprefix(scheduler_request_prefix).strip('/')
                if not request_id or '/' in request_id:
                    raise KeyError(parsed.path)
                self._send(200, self._scheduler_status(request_id))
                return
            rollout_prefix = '/v1/controller/runtime/rollouts/'
            if parsed.path.startswith(rollout_prefix):
                self._authorize_controller()
                rollout_id = parsed.path.removeprefix(rollout_prefix).strip('/')
                if not rollout_id or '/' in rollout_id:
                    raise KeyError(parsed.path)
                self._send(200, {'ok': True, 'rollout': self.controller.verify_runtime_rollout(rollout_id)})
                return
            if parsed.path.startswith('/v1/controller/nodes/'):
                self._authorize_controller()
                node_id = parsed.path.removeprefix('/v1/controller/nodes/').strip('/')
                if not node_id or '/' in node_id:
                    raise KeyError(parsed.path)
                self._send(200, {'ok': True, 'node': self.controller.node(node_id)})
                return
            if parsed.path.startswith('/v1/controller/receipts/'):
                self._authorize_controller()
                task_id = parsed.path.removeprefix('/v1/controller/receipts/').strip('/')
                if not task_id or '/' in task_id:
                    raise KeyError(parsed.path)
                self._send(200, {'ok': True, 'receipt': self.controller.receipt(task_id)})
                return
            self._send(404, {'ok': False, 'error': 'not found'})
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == '/v1/join/request':
                body = self._json_body()
                result = self.fabric.request_join(manifest=dict(body.get('manifest') or {}), expires_minutes=int(body.get('expires_minutes') or 10))
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/join/status':
                body = self._json_body()
                result = self.fabric.join_status(request_id=str(body.get('request_id') or ''), claim_secret=str(body.get('claim_secret') or ''))
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/join/claim':
                body = self._json_body()
                result = self.fabric.claim_join(request_id=str(body.get('request_id') or ''), claim_secret=str(body.get('claim_secret') or ''))
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/enroll':
                body = self._json_body()
                result = self.fabric.enroll(invite_id=str(body.get('invite_id') or ''), code=str(body.get('code') or ''), manifest=dict(body.get('manifest') or {}))
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/heartbeat':
                body = self._json_body()
                token = self._bearer()
                node = self.fabric.record_heartbeat(body, token)
                auto_ota = None
                policy = self.controller.ota_policy.load()
                desired = str(policy.get('desired_source_commit') or '')
                node_id = str(body.get('node_id') or '')
                effective = self.controller.node(node_id)
                if (
                    policy.get('auto_converge') is True
                    and desired
                    and effective.get('status') == 'online'
                    and effective.get('runtime_status') != 'converged'
                    and 'shell.exec' in set(effective.get('capabilities') or [])
                    and (effective.get('workspace_roots') or {}).get('readable')
                ):
                    auto_ota = self.controller.dispatch(node_id, {
                        'action': 'node.runtime.converge',
                        'task_id': f'auto_ota_{desired[:12]}_{node_id}',
                        'source_ref': str(policy.get('desired_source_ref') or 'feature/realm-node-fabric-readiness'),
                        'source_commit': desired,
                    })
                self._send(200, {'ok': True, 'node': node, 'auto_ota': auto_ota})
                return
            if parsed.path == '/v1/benchmark':
                body = self._json_body()
                token = self._bearer()
                node_id = str(body.get('node_id') or '')
                report = record_join_regression(self.fabric, node_id, token, body)
                self._send(200, {'ok': True, 'benchmark': report})
                return
            if parsed.path == '/v1/receipts':
                body = self._json_body()
                token = self._bearer()
                receipt = self.fabric.record_receipt(body, token)
                self._send(200, {'ok': True, 'receipt': receipt})
                return
            # Compatibility fence: preserve the live-accepted #64 transport contract.
            # Privileged runtime/controller surfaces below remain separately authenticated.
            if parsed.path == '/v1/controller/dispatch':
                body = self._json_body()
                result = LegacyControllerService(self.fabric).dispatch(body)
                self._send(200, result)
                return
            if parsed.path == '/v1/resolve':
                body = self._json_body()
                if body.get('schema') not in (None, 'agentos.resolve-request/v1'):
                    raise ValueError('invalid resolve request schema')
                if str(body.get('intent') or 'continue') != 'continue':
                    raise ValueError('only continue intent is supported in v1')
                node_id = str(body.get('node_id') or '')
                if not node_id:
                    raise ValueError('node_id is required')
                token = self._bearer()
                self.fabric.authenticate(node_id, token)
                node_context = bootstrap_snapshot(self.fabric, node_id, token)
                project_query = str(body.get('project') or body.get('query') or '').strip()
                if not project_query:
                    raise ValueError('project query is required')
                result = resolve_continuation(project_query, node_context=node_context)
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/dispatch':
                scheduler_claims = self._authorize_scheduler()
                dispatch_body = self._json_body()
                if scheduler_claims is not None:
                    requested_commit = str(dispatch_body.get('source_commit') or '')
                    if requested_commit != str(scheduler_claims.get('sha') or ''):
                        raise PermissionError('github oidc source commit mismatch')
                self._send(202, self._runner_window_submit(dispatch_body))
                return
            if parsed.path == '/v1/controller/scheduler/submit':
                scheduler_claims = self._authorize_scheduler()
                scheduler_body = self._json_body()
                if scheduler_claims is not None:
                    requested_commit = str((scheduler_body.get('params') or {}).get('source_commit') or '')
                    if requested_commit != str(scheduler_claims.get('sha') or ''):
                        raise PermissionError('github oidc source commit mismatch')
                self._send(202, self._scheduler_submit(scheduler_body))
                return
            if parsed.path == '/v1/controller/runtime/rollout':
                self._authorize_controller()
                result = self.controller.rollout_runtime(self._json_body())
                self._send(202, result)
                return
            prefix = '/v1/controller/nodes/'
            suffix = '/discover'
            if parsed.path.startswith(prefix) and parsed.path.endswith(suffix):
                self._authorize_controller()
                node_id = parsed.path[len(prefix):-len(suffix)].strip('/')
                if not node_id or '/' in node_id:
                    raise KeyError(parsed.path)
                result = self.controller.discover(node_id)
                self._send(202, result)
                return
            self._send(404, {'ok': False, 'error': 'not found'})
        except Exception as exc:
            self._error(exc)


class RealmHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], fabric: RealmFabricStore, *, controller_token: str | None = None):
        super().__init__(address, RealmRequestHandler)
        self.fabric = fabric
        self.controller = RuntimeControllerService(fabric)
        self.controller_token = controller_token if controller_token is not None else os.environ.get('AGENTOS_CONTROLLER_TOKEN', '')


def serve(*, host: str = '127.0.0.1', port: int = 8780, fabric: RealmFabricStore | None = None, controller_token: str | None = None) -> None:
    store = fabric or RealmFabricStore()
    realm = store.load()
    realm_id = str(realm.get('realm_id') or '').strip()
    if not realm_id:
        raise ValueError('initialize Realm before serving')

    registry = store.node_registry
    manifest = _core_node_manifest(realm_id)
    registry.register_manifest(manifest)
    registry.record_heartbeat(_core_node_heartbeat(manifest))
    stop = threading.Event()
    heartbeat = threading.Thread(target=_run_core_node_heartbeat, args=(registry, manifest, stop), name='agentos-core-node-heartbeat', daemon=True)
    heartbeat.start()

    server = RealmHTTPServer((host, port), store, controller_token=controller_token)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        stop.set()
        heartbeat.join(timeout=2)
        server.server_close()
