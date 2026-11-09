#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, subprocess, tempfile, time, urllib.request

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-commit',required=True)
    args=ap.parse_args()
    sha=args.source_commit.strip()
    subprocess.run(['open','-a','Google Chrome','https://www.threads.com/messages'],check=False)
    time.sleep(3)
    img=tempfile.mktemp(suffix='.png')
    swift=tempfile.mktemp(suffix='.swift')
    try:
        urllib.request.urlretrieve(f'https://raw.githubusercontent.com/alston-personal/agentmanager/{sha}/scripts/macos_vision_ocr.swift',swift)
        cap=subprocess.run(['/usr/sbin/screencapture','-x',img],text=True,capture_output=True,timeout=15)
        if cap.returncode != 0:
            print('VISION_CAPTURE=FAIL')
            return 11
        ocr=subprocess.run(['/usr/bin/xcrun','swift',swift,img],text=True,capture_output=True,timeout=120)
        lines=[x for x in ocr.stdout.splitlines() if x.strip()]
        print('VISION_OCR_RC='+str(ocr.returncode))
        print('VISION_OCR_LINES='+str(len(lines)))
        print('VISION_OCR_BYTES='+str(len(ocr.stdout.encode())))
        return 0 if ocr.returncode==0 and lines else 12
    finally:
        for p in (img,swift):
            try: os.unlink(p)
            except FileNotFoundError: pass
if __name__=='__main__':
    raise SystemExit(main())
