#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_ENV_FILE = Path('/home/ubuntu/.config/agentos/social-runtime.env')
DEFAULT_PRODUCT_SECRET_DIR = Path('/home/ubuntu/.config/agentos/social-products')
PRODUCT_ID_RE = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$')


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        raise RuntimeError('social_runtime_env_missing')
    return path.read_text(encoding='utf-8').splitlines()


def _index_key(lines: list[str], key: str) -> int | None:
    prefix = key + '='
    matches = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) > 1:
        raise RuntimeError(f'social_runtime_env_duplicate_key:{key}')
    return matches[0] if matches else None


def _get(lines: list[str], key: str, default: str = '') -> str:
    idx = _index_key(lines, key)
    if idx is None:
        return default
    return lines[idx].split('=', 1)[1]


def _set(lines: list[str], key: str, value: str) -> None:
    if '\n' in value or '\r' in value:
        raise ValueError('social_runtime_env_multiline_value_forbidden')
    idx = _index_key(lines, key)
    line = f'{key}={value}'
    if idx is None:
        lines.append(line)
    else:
        lines[idx] = line


def _atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    os.chmod(path, mode)


def _validate_product_id(product_id: str) -> str:
    value = str(product_id or '').strip()
    if not PRODUCT_ID_RE.fullmatch(value):
        raise ValueError('social_product_id_invalid')
    return value


def _validate_return_base(return_base: str) -> str:
    value = str(return_base or '').strip().rstrip('/')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('social_product_return_base_invalid')
    if parsed.query or parsed.fragment:
        raise ValueError('social_product_return_base_invalid')
    if parsed.path and not parsed.path.startswith('/'):
        raise ValueError('social_product_return_base_invalid')
    return value


def ensure_control_token(env_file: Path = DEFAULT_ENV_FILE) -> bool:
    lines = _read_lines(env_file)
    current = _get(lines, 'AGENTOS_SOCIAL_CONTROL_TOKEN')
    changed = not bool(current)
    if changed:
        _set(lines, 'AGENTOS_SOCIAL_CONTROL_TOKEN', secrets.token_urlsafe(48))
        _atomic_write(env_file, '\n'.join(lines) + '\n')
    else:
        os.chmod(env_file, 0o600)
    return changed


def register_product(
    product_id: str,
    return_base: str,
    *,
    env_file: Path = DEFAULT_ENV_FILE,
    product_secret_dir: Path = DEFAULT_PRODUCT_SECRET_DIR,
) -> tuple[bool, Path]:
    product_id = _validate_product_id(product_id)
    return_base = _validate_return_base(return_base)
    lines = _read_lines(env_file)
    raw = _get(lines, 'AGENTOS_SOCIAL_PRODUCTS_JSON', '{}') or '{}'
    try:
        registry = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError('social_product_registry_invalid') from exc
    if not isinstance(registry, dict):
        raise RuntimeError('social_product_registry_invalid')

    existing = registry.get(product_id)
    created = existing is None
    if existing is None:
        api_key = secrets.token_urlsafe(48)
        registry[product_id] = {'api_key': api_key, 'return_base': return_base}
    else:
        if not isinstance(existing, dict):
            raise RuntimeError('social_product_registry_invalid')
        api_key = str(existing.get('api_key') or '')
        existing_return = str(existing.get('return_base') or '').rstrip('/')
        if not api_key or existing_return != return_base:
            raise RuntimeError('social_product_registration_conflict')

    compact = json.dumps(registry, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    _set(lines, 'AGENTOS_SOCIAL_PRODUCTS_JSON', compact)
    _atomic_write(env_file, '\n'.join(lines) + '\n')

    secret_path = product_secret_dir / f'{product_id}.env'
    secret_text = (
        f'AGENTOS_SOCIAL_PRODUCT_ID={product_id}\n'
        f'AGENTOS_SOCIAL_PRODUCT_KEY={api_key}\n'
        f'AGENTOS_SOCIAL_RETURN_BASE={return_base}\n'
    )
    _atomic_write(secret_path, secret_text)
    return created, secret_path


def status(product_id: str, *, env_file: Path = DEFAULT_ENV_FILE, product_secret_dir: Path = DEFAULT_PRODUCT_SECRET_DIR) -> dict[str, bool]:
    product_id = _validate_product_id(product_id)
    lines = _read_lines(env_file)
    raw = _get(lines, 'AGENTOS_SOCIAL_PRODUCTS_JSON', '{}') or '{}'
    try:
        registry = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError('social_product_registry_invalid') from exc
    if not isinstance(registry, dict):
        raise RuntimeError('social_product_registry_invalid')
    return {
        'registered': product_id in registry,
        'secret_file_present': (product_secret_dir / f'{product_id}.env').is_file(),
        'control_token_configured': bool(_get(lines, 'AGENTOS_SOCIAL_CONTROL_TOKEN')),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Host-local AgentOS Social runtime secret provisioning.')
    parser.add_argument('--env-file', type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument('--product-secret-dir', type=Path, default=DEFAULT_PRODUCT_SECRET_DIR)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('ensure-control-token')
    register = sub.add_parser('register-product')
    register.add_argument('product_id')
    register.add_argument('return_base')
    status_cmd = sub.add_parser('status')
    status_cmd.add_argument('product_id')
    args = parser.parse_args(argv)

    if args.command == 'ensure-control-token':
        changed = ensure_control_token(args.env_file)
        print('social_runtime_control_token=' + ('GENERATED' if changed else 'PRESERVED'))
        return 0
    if args.command == 'register-product':
        created, secret_path = register_product(
            args.product_id,
            args.return_base,
            env_file=args.env_file,
            product_secret_dir=args.product_secret_dir,
        )
        print('social_runtime_product=' + ('REGISTERED' if created else 'PRESERVED'))
        print('social_runtime_product_secret_file=' + str(secret_path))
        print('social_runtime_secret_value_exposure=NONE')
        return 0
    if args.command == 'status':
        value = status(args.product_id, env_file=args.env_file, product_secret_dir=args.product_secret_dir)
        print(json.dumps(value, sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == '__main__':
    raise SystemExit(main())
