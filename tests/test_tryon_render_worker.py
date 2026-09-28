import importlib.util
import json
import sys
import types
from pathlib import Path


def load_worker(monkeypatch, tmp_path):
    fake_gradio = types.ModuleType("gradio_client")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

    fake_gradio.Client = FakeClient
    fake_gradio.handle_file = lambda value: value
    monkeypatch.setitem(sys.modules, "gradio_client", fake_gradio)
    monkeypatch.setenv("AGENT_DATA_ROOT", str(tmp_path))

    path = Path(__file__).resolve().parents[1] / "scripts" / "tryon_render_worker.py"
    spec = importlib.util.spec_from_file_location("tryon_render_worker_test_target", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, body: bytes, content_type: str, url: str):
        self._body = body
        self._url = url
        self.headers = types.SimpleNamespace(
            get=lambda key, default=None: content_type if key.lower() == "content-type" else default,
            get_content_charset=lambda: "utf-8",
        )

    def read(self, limit=-1):
        return self._body if limit < 0 else self._body[:limit]

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_resolve_product_page_og_image(monkeypatch, tmp_path):
    worker = load_worker(monkeypatch, tmp_path)
    html = b'<html><head><meta property="og:image" content="/assets/shoe.jpg"></head></html>'

    monkeypatch.setattr(
        worker.urllib.request,
        "urlopen",
        lambda req, timeout=45: FakeResponse(html, "text/html; charset=utf-8", "https://shop.example/p/123"),
    )

    assert worker.resolve_input_image_url("https://shop.example/p/123") == "https://shop.example/assets/shoe.jpg"


def test_partial_render_keeps_failed_bag_pending(monkeypatch, tmp_path):
    worker = load_worker(monkeypatch, tmp_path)
    person = tmp_path / "person.webp"
    person.write_bytes(b"x" * 2000)

    monkeypatch.setattr(worker, "BASE_BODY_URL", str(person))
    monkeypatch.setattr(worker, "idm_try_on", lambda *args, **kwargs: str(person))

    def fail_any_item(*args, **kwargs):
        raise RuntimeError("provider temporarily unavailable")

    monkeypatch.setattr(worker, "omni_try_on", fail_any_item)

    job = {
        "schema": worker.SCHEMA,
        "jobId": "partial-job",
        "characterId": "sunlake-milkcat-ai-001",
        "characterVersion": "mio-body-v1",
        "view": "front",
        "pose": "neutral_standing",
        "status": "queued",
        "requestedAt": "2026-09-28T00:00:00Z",
        "startedAt": None,
        "completedAt": None,
        "failedAt": None,
        "supersededBy": None,
        "input": {
            "selectedLayers": {
                "upper_main": {
                    "garmentId": "top-1",
                    "name": "top",
                    "sourceImageUrl": "https://example.com/top.jpg",
                },
                "bag": {
                    "garmentId": "bag-1",
                    "name": "bag",
                    "sourceImageUrl": "https://example.com/bag.jpg",
                },
            }
        },
        "output": {"asset": None, "previewAsset": None, "width": None, "height": None},
        "error": None,
    }
    job_path = worker.JOB_DIR / "partial-job.json"
    worker.atomic_write(job_path, job)
    worker.process_job(job_path, job)

    saved = json.loads(job_path.read_text(encoding="utf-8"))
    assert saved["status"] == "ready"
    assert saved["output"]["renderedLayers"] == ["upper_main"]
    assert saved["output"]["pendingLayers"] == ["bag"]
    assert saved["output"]["warnings"][0]["layer"] == "bag"
    assert (worker.ASSET_DIR / "partial-job.webp").exists()


def test_any_item_only_job_can_render_bag(monkeypatch, tmp_path):
    worker = load_worker(monkeypatch, tmp_path)
    person = tmp_path / "person.webp"
    person.write_bytes(b"x" * 2000)

    monkeypatch.setattr(worker, "BASE_BODY_URL", str(person))
    monkeypatch.setattr(worker, "omni_try_on", lambda *args, **kwargs: (str(person), "pbgo/OmniTry"))

    job = {
        "schema": worker.SCHEMA,
        "jobId": "bag-job",
        "characterId": "sunlake-milkcat-ai-001",
        "characterVersion": "mio-body-v1",
        "view": "front",
        "pose": "neutral_standing",
        "status": "queued",
        "requestedAt": "2026-09-28T00:00:00Z",
        "startedAt": None,
        "completedAt": None,
        "failedAt": None,
        "supersededBy": None,
        "input": {
            "selectedLayers": {
                "bag": {
                    "garmentId": "bag-1",
                    "name": "bag",
                    "sourceImageUrl": "https://example.com/bag.jpg",
                }
            }
        },
        "output": {"asset": None, "previewAsset": None, "width": None, "height": None},
        "error": None,
    }
    job_path = worker.JOB_DIR / "bag-job.json"
    worker.atomic_write(job_path, job)
    worker.process_job(job_path, job)

    saved = json.loads(job_path.read_text(encoding="utf-8"))
    assert saved["status"] == "ready"
    assert saved["output"]["renderedLayers"] == ["bag"]
    assert saved["output"]["pendingLayers"] == []
    assert saved["output"]["provider"] == "hybrid-vton"


def test_clothing_only_cache_key_remains_compatible(monkeypatch, tmp_path):
    worker = load_worker(monkeypatch, tmp_path)
    job = {
        "characterId": "sunlake-milkcat-ai-001",
        "characterVersion": "mio-body-v1",
        "view": "front",
        "pose": "neutral_standing",
        "input": {
            "selectedLayers": {
                "upper_main": {"garmentId": "net-43774-002"}
            }
        },
    }
    assert (
        worker.outfit_cache_key(job, ["upper_main"])
        == "c4a850d62a8dd41826d583e229ee230e009ef536aa4b1fae9d7036ede4a394c8"
    )


def test_any_item_provider_fallback(monkeypatch, tmp_path):
    worker = load_worker(monkeypatch, tmp_path)
    person = tmp_path / "person.webp"
    item = tmp_path / "item.jpg"
    output = tmp_path / "output.webp"
    person.write_bytes(b"p" * 2000)
    item.write_bytes(b"i" * 2000)
    output.write_bytes(b"o" * 2000)

    monkeypatch.setattr(worker, "ANY_ITEM_SPACE_IDS", ["broken/OmniTry", "pbgo/OmniTry"])
    monkeypatch.setattr(worker, "download_input", lambda url, suffix: person if "person" in url else item)

    class FakeBroken:
        def predict(self, *args, **kwargs):
            raise RuntimeError("configuration error")

    class FakeWorking:
        def predict(self, *args, **kwargs):
            return str(output)

    monkeypatch.setattr(
        worker,
        "any_item_client",
        lambda space_id: FakeBroken() if space_id.startswith("broken/") else FakeWorking(),
    )

    rendered, provider = worker.omni_try_on(
        "https://example.com/person.webp",
        "https://example.com/item.jpg",
        "shoe",
        123,
    )
    assert rendered == str(output)
    assert provider == "pbgo/OmniTry"


def test_any_item_client_passes_hf_token(monkeypatch, tmp_path):
    worker = load_worker(monkeypatch, tmp_path)
    worker._ANY_ITEM_CLIENTS.clear()
    worker.HF_TOKEN = "hf_test_token"
    captured = {}

    class TokenClient:
        def __init__(self, source, token=None, **kwargs):
            captured["source"] = source
            captured["token"] = token
            captured["kwargs"] = kwargs

    monkeypatch.setattr(worker, "Client", TokenClient)
    client = worker.any_item_client("pbgo/OmniTry")
    assert isinstance(client, TokenClient)
    assert captured["source"] == "pbgo/OmniTry"
    assert captured["token"] == "hf_test_token"


def test_any_item_transient_failure_retries_same_provider(monkeypatch, tmp_path):
    worker = load_worker(monkeypatch, tmp_path)
    person = tmp_path / "person.webp"
    item = tmp_path / "item.jpg"
    output = tmp_path / "output.webp"
    person.write_bytes(b"p" * 2000)
    item.write_bytes(b"i" * 2000)
    output.write_bytes(b"o" * 2000)

    monkeypatch.setattr(worker, "ANY_ITEM_SPACE_IDS", ["pbgo/OmniTry"])
    monkeypatch.setattr(worker, "download_input", lambda url, suffix: person if "person" in url else item)
    monkeypatch.setattr(worker.time, "sleep", lambda seconds: None)

    calls = {"count": 0}

    class FlakyClient:
        def predict(self, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] < 3:
                raise RuntimeError("502 Bad Gateway")
            return str(output)

    monkeypatch.setattr(worker, "any_item_client", lambda space_id: FlakyClient())

    rendered, provider = worker.omni_try_on(
        "https://example.com/person.webp",
        "https://example.com/item.jpg",
        "shoe",
        123,
    )
    assert rendered == str(output)
    assert provider == "pbgo/OmniTry"
    assert calls["count"] == 3


def test_any_item_falls_back_to_qwen_reference_edit(monkeypatch, tmp_path):
    worker = load_worker(monkeypatch, tmp_path)
    person = tmp_path / "person.webp"
    item = tmp_path / "item.jpg"
    output = tmp_path / "qwen-output.webp"
    person.write_bytes(b"p" * 2000)
    item.write_bytes(b"i" * 2000)
    output.write_bytes(b"o" * 2000)

    monkeypatch.setattr(worker, "ANY_ITEM_SPACE_IDS", ["broken/OmniTry"])
    monkeypatch.setattr(worker, "download_input", lambda url, suffix: person if "person" in url else item)

    class Broken:
        def predict(self, *args, **kwargs):
            raise RuntimeError("CONFIG_ERROR")

    monkeypatch.setattr(worker, "any_item_client", lambda space_id: Broken())
    monkeypatch.setattr(
        worker,
        "qwen_reference_try_on",
        lambda *args, **kwargs: (str(output), worker.QWEN_EDIT_SPACE_ID),
    )

    rendered, provider = worker.omni_try_on(
        "https://example.com/person.webp",
        "https://example.com/item.jpg",
        "shoe",
        123,
    )
    assert rendered == str(output)
    assert provider == worker.QWEN_EDIT_SPACE_ID


def test_qwen_reference_edit_uses_reference_board_workflow(monkeypatch, tmp_path):
    worker = load_worker(monkeypatch, tmp_path)
    from PIL import Image

    person = tmp_path / "person.webp"
    item = tmp_path / "item.jpg"
    output = tmp_path / "qwen-output.webp"
    Image.new("RGB", (500, 900), "white").save(person, "WEBP")
    Image.new("RGB", (400, 400), "white").save(item, "JPEG")
    output.write_bytes(b"q" * 2000)

    calls = []

    class FakeQwen:
        def predict(self, *args, **kwargs):
            calls.append((args, kwargs))
            assert kwargs.get("api_name") == "/rewritten_instruction"
            assert len(args) == 2
            assert "canonical subject" in args[1]
            return ("rewritten instruction", str(output))

    monkeypatch.setattr(worker, "qwen_edit_client", lambda: FakeQwen())

    rendered, provider = worker.qwen_reference_try_on(
        str(person),
        str(item),
        "shoe",
        123,
    )
    assert rendered == str(output)
    assert provider == worker.QWEN_EDIT_SPACE_ID
    assert len(calls) == 1


def test_build_reference_board_is_valid_image(monkeypatch, tmp_path):
    worker = load_worker(monkeypatch, tmp_path)
    from PIL import Image

    person = tmp_path / "person.png"
    item = tmp_path / "item.png"
    Image.new("RGB", (400, 800), "white").save(person)
    Image.new("RGB", (300, 300), "white").save(item)

    board = worker.build_reference_board(person, item)
    try:
        image = Image.open(board)
        assert image.size == (1536, 1536)
        assert image.mode == "RGB"
    finally:
        board.unlink(missing_ok=True)
