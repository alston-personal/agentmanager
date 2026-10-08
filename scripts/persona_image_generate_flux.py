#!/usr/bin/env python3
"""Draft-only FLUX Kontext image executor for Mio; no publishing privileges."""
import argparse, hashlib, json, os, shutil, tempfile
from pathlib import Path

CANONICAL_SOURCE="https://studio.milkcat.org/personas/mio/mio-avatar.webp"
PROVIDERS=("black-forest-labs/FLUX.1-Kontext-Dev","mcp-tools/FLUX.1-Kontext-Dev")

def generate(request, destination):
    from gradio_client import Client, handle_file
    from PIL import Image
    from urllib.request import urlopen
    prompt=str(request.get("generation_prompt") or "").strip()
    if not prompt or request.get("mode")!="generate":
        raise ValueError("image_generation_prompt_required")
    action_id=str(request.get("action_id") or "")
    if not action_id or len(action_id)>128 or not all(c.isalnum() or c in "-_" for c in action_id):
        raise ValueError("unsafe_action_id")
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    output=destination/(action_id+".webp")
    if output.exists():
        raise FileExistsError("draft_output_exists_requires_review")
    with tempfile.TemporaryDirectory(prefix="mio-kontext-") as td:
        source=Path(td)/"canonical.webp"
        with urlopen(CANONICAL_SOURCE,timeout=20) as response:
            with source.open("wb") as writer:
                size=0
                while True:
                    chunk=response.read(65536)
                    if not chunk: break
                    size+=len(chunk)
                    if size>15_000_000: raise ValueError("canonical_reference_too_large")
                    writer.write(chunk)
        with Image.open(source) as img:
            img.verify()
        instructions=(
            "Edit the attached canonical Mio character reference, maintaining exactly the "
            "same face, eye geometry, subtle right under-eye beauty mark, deep-brown 7:3 "
            "hair part and recognizable face-framing strand, proportions, realistic skin "
            "and natural anatomy. Do not create a new person. Clearly fictional scene; "
            "never add fake brand logos, real-world visit proof, or unrelated people. "
            "Requested visual: "+prompt
        )
        errors=[]
        for provider in PROVIDERS:
            try:
                client=Client(provider,download_files=True,verbose=False)
                result=client.predict(input_image=handle_file(str(source)),prompt=instructions,
                    seed=0,randomize_seed=False,guidance_scale=2.5,steps=22,api_name="/infer")
                artifact=result[0] if isinstance(result,(list,tuple)) and result else result
                if isinstance(artifact,dict): artifact=artifact.get("path") or artifact.get("url")
                candidate=Path(str(artifact))
                if not candidate.is_file(): raise ValueError("provider_returned_no_local_image")
                with Image.open(candidate) as img:
                    img.verify()
                with Image.open(candidate) as img:
                    img.convert("RGB").save(output,format="WEBP",quality=94)
                digest=hashlib.sha256(output.read_bytes()).hexdigest()
                return {"status":"GENERATED_UNVERIFIED","provider":provider,
                    "image_path":str(output),"image_sha256":digest,
                    "reference_source":CANONICAL_SOURCE,
                    "identity_verified":False,"publication_allowed":False}
            except Exception as exc:
                errors.append({"provider":provider,"failure_class":type(exc).__name__})
        return {"status":"BLOCKED","reason":"ALL_IMAGE_PROVIDERS_FAILED","attempts":errors,
            "publication_allowed":False}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--request",required=True)
    ap.add_argument("--output-dir",required=True)
    ap.add_argument("--receipt",required=True)
    args=ap.parse_args()
    try:
        result=generate(json.loads(Path(args.request).read_text(encoding="utf-8")),args.output_dir)
    except (OSError,ValueError,ImportError,RuntimeError) as exc:
        result={"status":"BLOCKED","reason":type(exc).__name__,"publication_allowed":False}
    receipt=Path(args.receipt)
    receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"provider":result.get("provider"),
          "reason":result.get("reason")},ensure_ascii=False))
    return 0
if __name__=="__main__":raise SystemExit(main())
