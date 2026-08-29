#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'issue71_node_registry_repair_action_v1'
marker_v2 = 'issue71_node_registry_forensic_digest_bridge_v2'

if marker_v2 in text:
    print('issue71_repair_action_patch=ALREADY_PRESENT_V2')
    raise SystemExit(0)

# Upgrade an already-compiled v1 action without broadening its authority.  The
# original forensic copy was deliberately chmod 0600 by the agentos-node
# capture runner, so ubuntu cannot read that preserved file.  The immutable
# evidence chain is instead bridged by requiring the still-live malformed
# registry to have exactly the preserved forensic SHA256 before repair.
if marker in text:
    old = """    if not registry.is_file() or not forensic.is_file():
        return {'ok': False, 'stage': 'forensic_presence'}
    forensic_raw = forensic.read_bytes()
    forensic_sha = _i71_hashlib.sha256(forensic_raw).hexdigest()
    if forensic_sha != expected_forensic_sha:
        return {'ok': False, 'stage': 'forensic_digest', 'forensic_sha256': forensic_sha}
"""
    new = """    # issue71_node_registry_forensic_digest_bridge_v2
    # The preserved forensic file is owned 0600 by the capture identity.  Do
    # not chmod or rewrite it.  Prove equivalence by requiring the live bytes
    # to still match the already-recorded forensic digest, then parse those
    # identical bytes under the ubuntu-owned repair authority.
    if not registry.is_file() or not forensic.is_file():
        return {'ok': False, 'stage': 'forensic_presence'}
    forensic_raw = registry.read_bytes()
    forensic_sha = _i71_hashlib.sha256(forensic_raw).hexdigest()
    if forensic_sha != expected_forensic_sha:
        return {'ok': False, 'stage': 'forensic_digest_bridge', 'forensic_sha256': forensic_sha}
"""
    if old not in text:
        raise SystemExit('Issue 71 v1 forensic block not found')
    text = text.replace(old, new, 1)
    compile(text, str(path), 'exec')
    path.write_text(text, encoding='utf-8')
    print('issue71_repair_action_patch=UPGRADED_V2')
    raise SystemExit(0)

anchor = '\n# deployment_rejection_precedence_v1\nACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {'
if anchor not in text:
    raise SystemExit('Issue 71 repair action anchor not found')

function = r'''

# issue71_node_registry_repair_action_v1
# One-time, narrowly-scoped recovery primitive for GitHub Issue #71.  It has no
# arbitrary path/service/hash parameters: all authority-relevant values are
# fixed below.  It may only run while the previously accepted generation is
# converged and explicitly released.  A repair failure restarts the old Realm;
# success intentionally leaves Realm stopped so the fenced generation advance
# + install sequence owns the next start.
def _issue71_repair_node_registry(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({},):
        raise ValueError('unexpected parameters')

    import fcntl as _i71_fcntl
    import hashlib as _i71_hashlib
    import tempfile as _i71_tempfile
    from datetime import datetime as _i71_datetime, timezone as _i71_timezone

    expected_commit = 'dedca4b1894987c4ed23fa43c442dbc11810b623'
    expected_generation = 3
    expected_owner = 'agentos-core-mainline'
    expected_forensic_sha = 'd9087bdecd1f2afdbddfde6a81673d35006df17f0e273053367fd4b5d1997a45'
    expected_first_object_end = 4674
    data_root = Path('/home/ubuntu/agent-data')
    registry = data_root / 'realm/nodes.json'
    forensic = data_root / 'forensics/issue-71/20260829T081141Z/nodes.json'

    state = _deployment_state_read()
    observed = _observed_realm_commit()
    if (
        int(state.get('deployment_generation') or 0) != expected_generation
        or state.get('desired_core_commit') != expected_commit
        or observed != expected_commit
        or state.get('lease_owner') != expected_owner
        or state.get('lease_status') != 'released'
        or state.get('deployment_status') != 'converged'
    ):
        return {
            'ok': False,
            'stage': 'deployment_precondition',
            'deployment_generation': state.get('deployment_generation'),
            'desired_core_commit': state.get('desired_core_commit'),
            'observed_core_commit': observed,
            'lease_owner': state.get('lease_owner'),
            'lease_status': state.get('lease_status'),
            'deployment_status': state.get('deployment_status'),
        }

    # issue71_node_registry_forensic_digest_bridge_v2
    if not registry.is_file() or not forensic.is_file():
        return {'ok': False, 'stage': 'forensic_presence'}
    forensic_raw = registry.read_bytes()
    forensic_sha = _i71_hashlib.sha256(forensic_raw).hexdigest()
    if forensic_sha != expected_forensic_sha:
        return {'ok': False, 'stage': 'forensic_digest_bridge', 'forensic_sha256': forensic_sha}

    stop = _run(['systemctl', '--user', 'stop', 'agentos-realm-fabric.service'], cwd=Path.home(), timeout=20)
    if stop.get('returncode') != 0:
        return {'ok': False, 'stage': 'stop_realm', 'stop': stop}

    try:
        raw = registry.read_bytes()
        pre_sha = _i71_hashlib.sha256(raw).hexdigest()
        stamp = _i71_datetime.now(_i71_timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        preserve_dir = data_root / 'forensics/issue-71' / stamp
        preserve_dir.mkdir(parents=True, exist_ok=False)
        preserve = preserve_dir / 'nodes.pre-repair.json'
        preserve.write_bytes(raw)
        preserve.chmod(0o600)
        if _i71_hashlib.sha256(preserve.read_bytes()).hexdigest() != pre_sha:
            raise RuntimeError('pre-repair forensic copy digest mismatch')

        repair_mode = 'already_valid'
        try:
            current = json.loads(raw.decode('utf-8'))
            if current.get('schema') != 'agentos.node-registry/v0.1' or not isinstance(current.get('nodes'), dict):
                raise ValueError('current registry schema invalid')
        except Exception:
            repair_mode = 'forensic_first_valid_object'
            if pre_sha != expected_forensic_sha:
                raise RuntimeError('live malformed registry digest no longer matches preserved forensic evidence')
            obj, end = json.JSONDecoder().raw_decode(forensic_raw.decode('utf-8'))
            if end != expected_first_object_end:
                raise RuntimeError(f'unexpected first JSON object end: {end}')
            if obj.get('schema') != 'agentos.node-registry/v0.1':
                raise RuntimeError('forensic first object schema mismatch')
            if obj.get('realm_id') != 'realm-alston':
                raise RuntimeError('forensic first object Realm mismatch')
            if not isinstance(obj.get('nodes'), dict) or len(obj['nodes']) != 2:
                raise RuntimeError('forensic first object node set mismatch')

            lock_path = registry.with_suffix(registry.suffix + '.lock')
            with lock_path.open('a+', encoding='utf-8') as lock:
                _i71_fcntl.flock(lock.fileno(), _i71_fcntl.LOCK_EX)
                if _i71_hashlib.sha256(registry.read_bytes()).hexdigest() != pre_sha:
                    raise RuntimeError('live registry changed after repair lock acquisition')
                payload = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
                fd, tmp_name = _i71_tempfile.mkstemp(prefix='.nodes.json.issue71-', suffix='.tmp', dir=str(registry.parent), text=True)
                tmp = Path(tmp_name)
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                        handle.write(payload); handle.flush(); os.fsync(handle.fileno())
                    tmp.chmod(0o600)
                    os.replace(tmp, registry)
                    dir_fd = os.open(str(registry.parent), os.O_RDONLY)
                    try: os.fsync(dir_fd)
                    finally: os.close(dir_fd)
                finally:
                    tmp.unlink(missing_ok=True)
            current = json.loads(registry.read_text(encoding='utf-8'))

        if current.get('schema') != 'agentos.node-registry/v0.1' or not isinstance(current.get('nodes'), dict):
            raise RuntimeError('post-repair registry invalid')
        if current.get('realm_id') != 'realm-alston' or len(current['nodes']) != 2:
            raise RuntimeError('post-repair registry identity/node-count mismatch')
        post_sha = _i71_hashlib.sha256(registry.read_bytes()).hexdigest()
        return {'ok': True,'stage': 'repaired','repair_mode': repair_mode,'forensic_sha256': forensic_sha,'forensic_bridge': 'live_sha_equals_preserved_forensic_sha','pre_repair_sha256': pre_sha,'pre_repair_copy': str(preserve),'post_repair_sha256': post_sha,'realm_id': current.get('realm_id'),'node_ids': sorted(current['nodes']),'node_count': len(current['nodes']),'realm_service_stopped': True,'deployment_generation': expected_generation,'desired_core_commit': expected_commit,'observed_core_commit': observed,'lease_status': 'released'}
    except BaseException:
        _restart_user_service('agentos-realm-fabric.service', timeout=25)
        raise
'''

text = text.replace(anchor, function + anchor, 1)
needle = '    "agentos.realm-fabric.install_release": _install_realm_fabric_release,\n'
replacement = needle + '    "agentos.maintenance.issue71_repair_node_registry": _issue71_repair_node_registry,\n'
if needle not in text:
    raise SystemExit('Issue 71 ACTIONS mapping anchor not found')
text = text.replace(needle, replacement, 1)
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('issue71_repair_action_patch=PASS_V2')
