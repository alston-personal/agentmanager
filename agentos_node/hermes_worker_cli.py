"""Single-shot Hermes adapter CLI for the existing AgentOS Employee Worker Host."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from agentos_node.hermes_worker import process_exact, SCHEMA


def absolute(value: str) -> Path:
    path=Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("absolute_path_required")
    return path.resolve()


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(prog="agentos-hermes-worker")
    parser.add_argument("--runtime-root",type=absolute,required=True)
    parser.add_argument("--wake-root",type=absolute,required=True)
    parser.add_argument("--worker-state-root",type=absolute,required=True)
    parser.add_argument("--node-id",required=True)
    parser.add_argument("--wake-id",required=True)
    parser.add_argument("--presence-generation",type=int,required=True)
    parser.add_argument("--once",action="store_true",required=True)
    args=parser.parse_args(argv)
    if args.presence_generation < 1:
        parser.error("invalid_presence_generation")
    try:
        result=process_exact(runtime_root=args.runtime_root,wake_root=args.wake_root,
             worker_state_root=args.worker_state_root,node_id=args.node_id,
             wake_id=args.wake_id,presence_generation=args.presence_generation)
    except (OSError,ValueError,RuntimeError,PermissionError):
        # No raw exceptions: upstream payloads, paths and API responses are data.
        result={"schema":SCHEMA,"status":"failed","work_performed":False,
            "error_code":"hermes_governed_worker_failed","executor_provider":"unbound",
            "executor_model":"","credential_exposed":False,
            "session_identity_exposed":False,"verified_marker_emitted":False}
        print(json.dumps(result,ensure_ascii=False))
        return 2
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
