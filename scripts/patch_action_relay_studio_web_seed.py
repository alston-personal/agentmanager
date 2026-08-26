#!/usr/bin/env python3
from pathlib import Path

p = Path('agentos_node/action_relay.py')
s = p.read_text(encoding='utf-8')

if 'def _seed_verify_studio_web_remote(' in s:
    print('already_patched=YES')
    raise SystemExit(0)

marker = '\ndef _layoutlab_api_restart(params: dict[str, Any]) -> dict[str, Any]:\n'
if marker not in s:
    raise SystemExit('seed insertion marker missing')

fn = r'''

def _seed_verify_studio_web_remote(params: dict[str, Any]) -> dict[str, Any]:
    """Push the one governed Studio Web checkout and prove remote rebuildability."""
    if params not in ({}, {"repository": "alston-personal/studio-web"}):
        raise ValueError("unexpected parameters")
    repository = "alston-personal/studio-web"
    source = Path("/home/agentos-node/projects/studio-web")
    if not (source / ".git").exists() or not (source / "package.json").is_file():
        return {"ok": False, "repository": repository, "error": "governed source checkout unavailable"}

    steps: list[dict[str, Any]] = []
    git_prefix = ["git", "-c", f"safe.directory={source}", "-C", str(source)]
    status = _run(git_prefix + ["status", "--porcelain"], cwd=Path.home(), timeout=20)
    steps.append({"step": "source_status", **status})
    if status["returncode"] != 0 or (status.get("stdout") or "").strip():
        return {"ok": False, "repository": repository, "steps": steps, "error": "source checkout is not clean"}

    head = _run(git_prefix + ["rev-parse", "HEAD"], cwd=Path.home(), timeout=20)
    steps.append({"step": "source_head", **head})
    if head["returncode"] != 0:
        return {"ok": False, "repository": repository, "steps": steps}
    source_head = (head.get("stdout") or "").strip()

    auth = _run(["/usr/bin/gh", "auth", "status"], cwd=Path.home(), timeout=20)
    steps.append({"step": "gh_auth", **auth})
    if auth["returncode"] != 0:
        return {"ok": False, "repository": repository, "steps": steps, "error": "ubuntu GitHub identity is not authenticated"}

    view = _run(["/usr/bin/gh", "repo", "view", repository, "--json", "nameWithOwner,isPrivate"], cwd=Path.home(), timeout=20)
    steps.append({"step": "remote_view", **view})
    if view["returncode"] != 0:
        return {"ok": False, "repository": repository, "steps": steps, "error": "remote repository unavailable"}
    try:
        meta = json.loads(view.get("stdout") or "{}")
    except json.JSONDecodeError:
        meta = {}
    if meta.get("nameWithOwner") != repository or meta.get("isPrivate") is not True:
        return {"ok": False, "repository": repository, "steps": steps, "error": "remote identity/visibility mismatch"}

    setup = _run(["/usr/bin/gh", "auth", "setup-git"], cwd=Path.home(), timeout=20)
    steps.append({"step": "gh_auth_setup_git", **setup})
    if setup["returncode"] != 0:
        return {"ok": False, "repository": repository, "steps": steps}

    push = _run(git_prefix + ["push", "https://github.com/alston-personal/studio-web.git", "HEAD:main"], cwd=Path.home(), timeout=120)
    steps.append({"step": "initial_push", **push})
    if push["returncode"] != 0:
        return {"ok": False, "repository": repository, "source_head": source_head, "steps": steps}

    verify_root = Path("/tmp") / f"studio-web-remote-verify-{uuid.uuid4().hex}"
    clone = _run(["/usr/bin/gh", "repo", "clone", repository, str(verify_root)], cwd=Path.home(), timeout=120)
    steps.append({"step": "fresh_clone", **clone})
    if clone["returncode"] != 0:
        return {"ok": False, "repository": repository, "source_head": source_head, "steps": steps}

    try:
        remote_head_step = _run(["git", "-C", str(verify_root), "rev-parse", "HEAD"], cwd=Path.home(), timeout=20)
        steps.append({"step": "remote_head", **remote_head_step})
        remote_head = (remote_head_step.get("stdout") or "").strip()
        if remote_head_step["returncode"] != 0 or remote_head != source_head:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "steps": steps, "error": "remote head mismatch"}

        if (verify_root / "pnpm-lock.yaml").is_file():
            install_argv = ["pnpm", "install", "--frozen-lockfile"]
            build_argv = ["pnpm", "run", "build"]
            package_manager = "pnpm"
        elif (verify_root / "package-lock.json").is_file():
            install_argv = ["npm", "ci"]
            build_argv = ["npm", "run", "build"]
            package_manager = "npm"
        elif (verify_root / "yarn.lock").is_file():
            install_argv = ["yarn", "install", "--frozen-lockfile"]
            build_argv = ["yarn", "run", "build"]
            package_manager = "yarn"
        else:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "steps": steps, "error": "supported lockfile missing"}

        install = _run(install_argv, cwd=verify_root, timeout=600)
        steps.append({"step": "fresh_install", **install})
        if install["returncode"] != 0:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "package_manager": package_manager, "steps": steps}

        build = _run(build_argv, cwd=verify_root, timeout=600)
        steps.append({"step": "fresh_build", **build})
        if build["returncode"] != 0:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "package_manager": package_manager, "steps": steps}

        home = verify_root / "dist" / "index.html"
        layout_source = verify_root / "public" / "layout-lab" / "index.html"
        layout_dist = verify_root / "dist" / "layout-lab" / "index.html"
        if not home.is_file() or not layout_source.is_file() or not layout_dist.is_file():
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "package_manager": package_manager, "steps": steps, "error": "required built artifact missing"}
        layout_bytes = layout_dist.read_bytes()
        if b"Layout Lab | Milkcat Studio" not in layout_bytes or b"Analyze layout" not in layout_bytes:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "package_manager": package_manager, "steps": steps, "error": "Layout Lab identity marker missing"}
        source_sha = hashlib.sha256(layout_source.read_bytes()).hexdigest()
        dist_sha = hashlib.sha256(layout_bytes).hexdigest()
        home_sha = hashlib.sha256(home.read_bytes()).hexdigest()
        if source_sha != dist_sha:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "package_manager": package_manager, "layout_source_sha256": source_sha, "layout_dist_sha256": dist_sha, "steps": steps, "error": "Layout Lab source/dist mismatch"}
        return {
            "ok": True,
            "repository": repository,
            "source_head": source_head,
            "remote_head": remote_head,
            "package_manager": package_manager,
            "fresh_clone_build": True,
            "layoutlab_website_owned": True,
            "layout_sha256": dist_sha,
            "home_sha256": home_sha,
            "production_cutover": False,
            "steps": steps,
        }
    finally:
        _run(["rm", "-rf", str(verify_root)], cwd=Path.home(), timeout=30)
'''
s = s.replace(marker, fn + marker, 1)

map_marker = '    "github.repo.ensure_studio_web": _ensure_studio_web_remote,\n'
if map_marker not in s:
    raise SystemExit('action map marker missing')
s = s.replace(map_marker, map_marker + '    "github.repo.seed_verify_studio_web": _seed_verify_studio_web_remote,\n', 1)

p.write_text(s, encoding='utf-8')
print('patched=YES')
