import json, subprocess, sys
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"validate_mio_visual_manifest.py"

def run(tmp_path, manifest, anchor, photo=False):
    mp=tmp_path/"manifest.json"; ap=tmp_path/"anchor.json"
    mp.write_text(json.dumps(manifest),encoding="utf-8")
    ap.write_text(json.dumps(anchor),encoding="utf-8")
    cmd=[sys.executable,str(SCRIPT),"--manifest",str(mp),"--visual-anchor",str(ap)]
    if photo: cmd.append("--photo-like-face")
    return subprocess.run(cmd,text=True,capture_output=True)

def base():
    anchor={"face_blueprint":{"schema":"agentos.persona-face-blueprint/v2.1"}}
    features={k:{"status":"pass","evidence":["reviewed against approved reference"]}
              for k in ("face_shape","eye_shape","brows","hair_flow","right_eye_beauty_mark","upper_right_canine")}
    manifest={
      "schema":"milkcat.image-manifest/v2",
      "identity_blueprint":{
        "blueprint_version":"2.1",
        "reference_pack_status":"approved",
        "camera_mirror_state":"not_mirrored",
        "features":features
      },
      "checks":{"identity":{"status":"pass","evidence":["identity review receipt"]}},
      "publication":{"allowed":True}
    }
    return manifest,anchor

def test_passes_complete_blueprint(tmp_path):
    m,a=base(); r=run(tmp_path,m,a,photo=True)
    assert r.returncode==0,r.stdout+r.stderr
    assert json.loads(r.stdout)["status"]=="PASS"

def test_blocks_pending_reference_for_photo_face(tmp_path):
    m,a=base(); m["identity_blueprint"]["reference_pack_status"]="pending"
    r=run(tmp_path,m,a,photo=True)
    assert r.returncode!=0
    assert json.loads(r.stdout)["reason"]=="approved_reference_pack_required"

def test_blocks_wrong_side_feature_failure(tmp_path):
    m,a=base(); m["identity_blueprint"]["features"]["right_eye_beauty_mark"]={"status":"fail","evidence":["mark appears on anatomical left after mirror resolution"]}
    r=run(tmp_path,m,a)
    assert r.returncode!=0
    assert json.loads(r.stdout)["reason"]=="identity_feature_gate_failed"

def test_allows_hidden_canine_with_evidence(tmp_path):
    m,a=base(); m["identity_blueprint"]["features"]["upper_right_canine"]={"status":"not_visible","evidence":["closed-mouth smile"]}
    r=run(tmp_path,m,a)
    assert r.returncode==0,r.stdout+r.stderr

def test_blocks_unknown_mirror_state(tmp_path):
    m,a=base(); m["identity_blueprint"]["camera_mirror_state"]="unknown"
    r=run(tmp_path,m,a)
    assert r.returncode!=0
    assert json.loads(r.stdout)["reason"]=="camera_mirror_state_unresolved"
