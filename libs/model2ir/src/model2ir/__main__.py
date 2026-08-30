from __future__ import annotations
import argparse, json
from pathlib import Path
from .core import extract_ir, diff_ir, reconcile_ir


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(prog='model2ir')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('extract')
    p.add_argument('asset')
    p.add_argument('-o', '--output', required=True)
    p = sub.add_parser('diff')
    p.add_argument('a'); p.add_argument('b'); p.add_argument('-o','--output', required=True)
    p = sub.add_parser('reconcile')
    p.add_argument('image_ir'); p.add_argument('model_ir'); p.add_argument('-o','--output', required=True)
    args = ap.parse_args()
    if args.cmd == 'extract': out = extract_ir(args.asset)
    elif args.cmd == 'diff': out = diff_ir(load_json(args.a), load_json(args.b))
    else: out = reconcile_ir(load_json(args.image_ir), load_json(args.model_ir))
    write_json(args.output, out)
    print(json.dumps({'ok': True, 'schema': out.get('schema'), 'output': args.output}))

if __name__ == '__main__':
    main()
