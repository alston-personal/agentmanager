#!/usr/bin/env python3
"""Draft-only FLUX Kontext image executor for Mio; no publishing privileges."""
import argparse, hashlib, json, os, shutil, tempfile
from pathlib import Path

PROVIDERS=("black-forest-labs/FLUX.1-Kontext-Dev","mcp-tools/FLUX.1-Kontext-Dev")

def canonical_reference(request):
    pack=request.get("canonical_reference_pack") or {}
    reference_path=os.environ.get("AGENTOS_MIO_REFERENCE_IMAGE","")
    if not reference_path or pack.get("status")!="approved":
        raise ValueError("canonical_reference_unavailable")
    asset=pack.get("canonical_asset") or {}
    if asset.get("reference_id") not in (pack.get("approved_reference_ids") or []):
        raise ValueError("canonical_reference_not_approved")
    data=Path(reference_path).read_bytes()
    if len(data)>15_000_000 or hashlib.sha256(data).hexdigest()!=asset.get("sha256"):
        raise ValueError("canonical_reference_digest_mismatch")
    return data

def generate(request, destination):
    prompt=str(request.get("generation_prompt") or "").strip()
    if not prompt or request.get("mode")!="generate":
        raise ValueError("image_generation_prompt_required")
    action_id=str(request.get("action_id") or "")
    if not action_id or len(action_id)>128 or not all(c.isalnum() or c in "-_" for c in action_id):
        raise ValueError("unsafe_action_id")
    data=canonical_reference(request)
    from persona_media_asset import subject_mode
    subject=subject_mode(request)
    scene=subject=="scene_only"
    if scene:
        policy=request.get("visual_content_policy")
        scene_policy=policy.get("scene_only_images") if isinstance(policy,dict) else None
        if not isinstance(scene_policy,dict) or scene_policy.get("enabled") is not True:
            raise ValueError("MEDIA_SCENE_POLICY_NOT_ENABLED")
        assembly=request.get("content_assembly") or {}
        if not assembly.get("world") or assembly.get("wardrobe")!=[]:
            raise ValueError("MEDIA_SCENE_WARDROBE_NOT_ALLOWED")
    from gradio_client import Client, handle_file
    from PIL import Image
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    output=destination/(action_id+".jpg")
    if output.exists():
        raise FileExistsError("draft_output_exists_requires_review")
    with tempfile.TemporaryDirectory(prefix="mio-kontext-") as td:
        # Reference availability is configuration, approval/digest is persona
        # data authority. A public avatar is not interchangeable with the pack.
        source=Path(td)/("neutral.png" if scene else "canonical.jpg")
        if scene:
            # The identity reference is never sent to a scene-only generator.
            Image.new("RGB",(512,512),(240,240,240)).save(source,format="PNG")
        else:
            source.write_bytes(data)
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
        if scene:
            instructions=("Replace the neutral canvas with a photorealistic fictional scene or objects using only the selected source descriptions. "
                "No people, faces, human body parts, silhouettes, reflections, mannequins or depictions of people. "
                "No clothing, shoes, bags, jewelry, wearables or animal-worn accessories. No invented animals, food, brands, signage, logos or readable text. "
                "Never represent a real visit, purchase or photograph. Requested visual: "+prompt)
        if request.get("content_assembly"):
            instructions+=" Use only these selected source-backed world and wardrobe items; do not add other wearables or props: "+json.dumps(request["content_assembly"],ensure_ascii=False)
            if len(instructions)>30000:
                raise ValueError("image_generation_context_too_large")
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
                    img.convert("RGB").save(output,format="JPEG",quality=94)
                digest=hashlib.sha256(output.read_bytes()).hexdigest()
                return {"status":"GENERATED_UNVERIFIED","provider":provider,
                    "image_path":str(output),"image_sha256":digest,
                    "reference_image_sha256":hashlib.sha256(data).hexdigest(),
                    "subject_mode":subject,"identity_reference_used":not scene,
                    "generation_input_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
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
        request_path=Path(args.request)
        request=json.loads(request_path.read_text(encoding="utf-8"))
        persona=request_path.parent.parent.parent
        request["canonical_reference_pack"]=json.loads((persona/"reference_pack.json").read_text(encoding="utf-8"))
        request["visual_content_policy"]=json.loads((persona/"visual_content_policy.json").read_text(encoding="utf-8"))
        result=generate(request,args.output_dir)
    except (OSError,ValueError,ImportError,RuntimeError) as exc:
        known={"canonical_reference_unavailable","canonical_reference_not_approved",
               "canonical_reference_digest_mismatch","image_generation_prompt_required",
               "unsafe_action_id","draft_output_exists_requires_review"}
        reason=str(exc) if str(exc) in known else type(exc).__name__
        result={"status":"BLOCKED","reason":reason,"publication_allowed":False}
    receipt=Path(args.receipt)
    receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"provider":result.get("provider"),
          "reason":result.get("reason")},ensure_ascii=False))
    return 0
if __name__=="__main__":raise SystemExit(main())
