#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from agentos_node.social.contracts import SocialRequest, WRITE_OPERATIONS

DEFAULT_ENV_FILE = Path('/home/ubuntu/.config/agentos/social-runtime.env')
LOCAL_ACCEPTANCE_URL = 'http://127.0.0.1:8771/internal/v1/social/acceptances'
MAX_STDIN_BYTES = 64 * 1024


def _load_control_token(env_file: Path) -> str:
    if not env_file.is_file():
        raise RuntimeError('social_runtime_env_missing')
    matches: list[str] = []
    for line in env_file.read_text(encoding='utf-8').splitlines():
        if line.startswith('AGENTOS_SOCIAL_CONTROL_TOKEN='):
            matches.append(line.split('=', 1)[1])
    if len(matches) != 1:
        raise RuntimeError('social_runtime_control_token_invalid')
    token = matches[0]
    if not token:
        raise RuntimeError('social_runtime_control_token_unconfigured')
    return token


def _read_request(stream) -> tuple[dict, SocialRequest]:
    raw = stream.buffer.read(MAX_STDIN_BYTES + 1) if hasattr(stream, 'buffer') else stream.read(MAX_STDIN_BYTES + 1)
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    if not raw or len(raw) > MAX_STDIN_BYTES:
        raise ValueError('social_acceptance_request_size_invalid')
    value = json.loads(raw.decode('utf-8'))
    if not isinstance(value, dict):
        raise ValueError('social_acceptance_request_object_required')
    request = SocialRequest(**value).validate()
    if request.operation not in WRITE_OPERATIONS:
        raise ValueError('social_acceptance_write_operation_required')
    if not request.write_intent_id:
        raise ValueError('social_acceptance_write_intent_required')
    return value, request


def issue_acceptance(payload: dict, *, token: str, timeout: float = 5.0) -> dict[str, str]:
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    req = urllib.request.Request(
        LOCAL_ACCEPTANCE_URL,
        data=body,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-AgentOS-Control-Token': token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(MAX_STDIN_BYTES + 1)
            if len(raw) > MAX_STDIN_BYTES:
                raise RuntimeError('social_acceptance_response_size_invalid')
            value = json.loads(raw.decode('utf-8'))
    except urllib.error.HTTPError as exc:
        # Never echo the submitted request body or authentication token.
        raise RuntimeError(f'social_acceptance_runtime_http_{exc.code}') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError('social_acceptance_runtime_unreachable') from exc
    if not isinstance(value, dict):
        raise RuntimeError('social_acceptance_response_invalid')
    allowed = {'schema', 'acceptance_id', 'one_shot'}
    if set(value) - allowed:
        raise RuntimeError('social_acceptance_response_unexpected_field')
    if value.get('schema') != 'agentos.social-write-acceptance/v1' or not value.get('acceptance_id'):
        raise RuntimeError('social_acceptance_response_invalid')
    return {
        'schema': str(value['schema']),
        'acceptance_id': str(value['acceptance_id']),
        'one_shot': str(value.get('one_shot') or 'true'),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Issue one exact AgentOS Social write acceptance through the private local control plane.')
    parser.add_argument('--env-file', type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument('--timeout', type=float, default=5.0)
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout > 30:
        raise SystemExit('social_acceptance_timeout_invalid')

    try:
        payload, _request = _read_request(sys.stdin)
        token = _load_control_token(args.env_file)
        result = issue_acceptance(payload, token=token, timeout=args.timeout)
    except (ValueError, RuntimeError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # Output is intentionally restricted to the one-shot acceptance envelope.
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
