#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
action = 'github.repo.import_layoutlib_v079'
if action in text:
    print('layoutlib_v079_import_patch=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '\ndef _seed_verify_studio_web_remote(params: dict[str, Any]) -> dict[str, Any]:\n'
if anchor not in text:
    raise SystemExit('function insertion anchor not found')

fn = r'''

def _import_layoutlib_v079(params: dict[str, Any]) -> dict[str, Any]:
    """Import the fixed LayoutLib v0.7.9 production package into its canonical repo.

    This is deliberately not a general git/file-copy action. Source repository,
    source commit, source files, destination repository and destination path are
    all fixed by Core policy so the effect is reviewable and replayable.
    """
    import hashlib as _ll_hashlib
    import shutil as _ll_shutil
    import subprocess as _ll_subprocess
    import tempfile as _ll_tempfile

    source_repo = 'alston-personal/agentmanager'
    source_commit = 'e8efc4ed7cbd41839f960373f79c5fb6a5f82375'
    target_repo = 'alston-personal/layoutlib'
    release = 'v0.7.9'
    files = [
        'web_assets/layoutlab_v0_5.html',
        'web_assets/layoutlib-browser-v0.5.js',
        'web_assets/layoutlib-spatial-semantics-v0.1.js',
        'web_assets/layoutlib-editor-v0.7.js',
        'web_assets/layoutlab-editor-ui-v0.7.js',
        'web_assets/layoutlab-capability-bridge-v0.7.js',
        'web_assets/layoutlab-v0.7-release-fix.js',
    ]
    expected = {
        'repository': target_repo,
        'source_commit': source_commit,
    }
    if params not in ({}, expected):
        raise ValueError('unexpected parameters')

    def run(argv, cwd=None, timeout=90):
        p = _ll_subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
        return {'argv': argv, 'returncode': p.returncode, 'stdout': p.stdout[-4000:], 'stderr': p.stderr[-4000:]}

    auth = run(['/usr/bin/gh', 'auth', 'status'], cwd=str(Path.home()), timeout=20)
    if auth['returncode'] != 0:
        return {'ok': False, 'error': 'ubuntu GitHub identity is not authenticated', 'auth': auth}

    with _ll_tempfile.TemporaryDirectory(prefix='layoutlib-v079-import-') as td:
        root = Path(td)
        src = root / 'source'
        dst = root / 'layoutlib'
        clone_src = run(['/usr/bin/gh', 'repo', 'clone', source_repo, str(src)], timeout=120)
        if clone_src['returncode'] != 0:
            return {'ok': False, 'stage': 'clone_source', 'clone_source': clone_src}
        checkout = run(['/usr/bin/git', '-C', str(src), 'checkout', '--detach', source_commit], timeout=60)
        if checkout['returncode'] != 0:
            return {'ok': False, 'stage': 'checkout_source', 'checkout': checkout}

        source_hashes = {}
        for rel in files:
            p = src / rel
            if not p.is_file():
                return {'ok': False, 'stage': 'source_manifest', 'missing': rel}
            source_hashes[rel] = _ll_hashlib.sha256(p.read_bytes()).hexdigest()

        clone_dst = run(['/usr/bin/gh', 'repo', 'clone', target_repo, str(dst)], timeout=120)
        if clone_dst['returncode'] != 0:
            return {'ok': False, 'stage': 'clone_target', 'clone_target': clone_dst}
        run(['/usr/bin/git', '-C', str(dst), 'checkout', '-B', 'main'], timeout=30)

        release_dir = dst / 'release' / release
        release_dir.mkdir(parents=True, exist_ok=True)
        for rel in files:
            _ll_shutil.copy2(src / rel, release_dir / Path(rel).name)

        provenance = f'''# LayoutLib {release} production extraction\n\nCanonical source extraction from `{source_repo}` at exact commit `{source_commit}`.\n\nThe files in this directory are the seven assets used by the authoritative Oracle `Layout Lab v0.7` production release path. They are preserved flat so the historical script references remain valid.\n\n## Ownership boundary\n\n- LayoutLib library/parser/editor semantics: `layoutlib-browser-v0.5.js`, `layoutlib-spatial-semantics-v0.1.js`, `layoutlib-editor-v0.7.js`.\n- Layout Lab reference/demo surface: `layoutlab_v0_5.html`, `layoutlab-editor-ui-v0.7.js`, `layoutlab-capability-bridge-v0.7.js`, `layoutlab-v0.7-release-fix.js`.\n- The historical filename `layoutlib-browser-v0.5.js` identifies itself internally as Browser Adapter v0.6.0; it is intentionally not renamed in this extraction.\n\nThis extraction is provenance-preserving. Refactoring/version normalization must be a later, separately reviewed change.\n'''
        (release_dir / 'PROVENANCE.md').write_text(provenance, encoding='utf-8')
        manifest = {
            'schema': 'layoutlib.production-extraction/v1',
            'release': release,
            'source_repository': source_repo,
            'source_commit': source_commit,
            'files': [{'source': rel, 'destination': f'release/{release}/{Path(rel).name}', 'sha256': source_hashes[rel]} for rel in files],
        }
        (release_dir / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        readme = f'''# LayoutLib\n\nCanonical repository for the LayoutLib spatial layout library and the Layout Lab reference demo.\n\nThe first canonicalized production snapshot is under `release/{release}/`, extracted without semantic refactoring from `{source_repo}@{source_commit}`.\n'''
        (dst / 'README.md').write_text(readme, encoding='utf-8')

        run(['/usr/bin/git', '-C', str(dst), 'config', 'user.name', 'AgentOS Oracle Core'])
        run(['/usr/bin/git', '-C', str(dst), 'config', 'user.email', 'agentos-core@users.noreply.github.com'])
        add = run(['/usr/bin/git', '-C', str(dst), 'add', 'README.md', f'release/{release}'])
        if add['returncode'] != 0:
            return {'ok': False, 'stage': 'git_add', 'git_add': add}
        status = run(['/usr/bin/git', '-C', str(dst), 'status', '--porcelain'])
        changed = bool(status['stdout'].strip())
        if changed:
            commit = run(['/usr/bin/git', '-C', str(dst), 'commit', '-m', 'chore: import canonical LayoutLib v0.7.9 production snapshot'], timeout=60)
            if commit['returncode'] != 0:
                return {'ok': False, 'stage': 'git_commit', 'git_commit': commit}
            push = run(['/usr/bin/git', '-C', str(dst), 'push', 'origin', 'HEAD:main'], timeout=120)
            if push['returncode'] != 0:
                return {'ok': False, 'stage': 'git_push', 'git_push': push}
        head = run(['/usr/bin/git', '-C', str(dst), 'rev-parse', 'HEAD'])
        if head['returncode'] != 0:
            return {'ok': False, 'stage': 'head', 'head': head}
        target_commit = head['stdout'].strip()

        # Byte-for-byte post-copy verification before declaring the effect complete.
        destination_hashes = {}
        for rel in files:
            name = Path(rel).name
            p = release_dir / name
            destination_hashes[name] = _ll_hashlib.sha256(p.read_bytes()).hexdigest()
            if destination_hashes[name] != source_hashes[rel]:
                return {'ok': False, 'stage': 'hash_verify', 'file': name}

        return {
            'ok': True,
            'repository': target_repo,
            'release': release,
            'source_repository': source_repo,
            'source_commit': source_commit,
            'target_commit': target_commit,
            'changed': changed,
            'file_count': len(files),
            'source_sha256': source_hashes,
            'destination_sha256': destination_hashes,
        }
'''
text = text.replace(anchor, fn + anchor, 1)

mapping_anchor = '    "github.repo.ensure_layoutlib": _ensure_layoutlib_remote,\n'
if mapping_anchor not in text:
    raise SystemExit('LayoutLib ACTIONS insertion anchor not found')
text = text.replace(mapping_anchor, mapping_anchor + '    "github.repo.import_layoutlib_v079": _import_layoutlib_v079,\n', 1)
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('layoutlib_v079_import_patch=PASS')
