from capabilities.wardrobe_visual_review import evaluate_review


def base_request():
    return {
        "schema": "agentos.wardrobe-visual-review-request/v1",
        "selectedLayers": {
            "upper_main": {"garmentId": "top-1"},
            "lower_main": {"garmentId": "bottom-1"},
        },
        "renderedLayers": ["upper_main", "lower_main"],
        "pendingLayers": [],
        "machineChecks": [],
    }


def test_candidate_without_semantic_backend():
    receipt = evaluate_review(base_request())
    assert receipt["state"] == "candidate"
    assert receipt["accepted"] is False


def test_rejects_missing_selected_layer():
    request = base_request()
    request["renderedLayers"] = ["upper_main"]
    receipt = evaluate_review(request)
    assert receipt["state"] == "rejected"
    assert any(row["code"] == "missing_selected_layer" for row in receipt["checks"])


def test_verifies_only_with_full_semantic_coverage():
    request = base_request()
    request["semanticReceipt"] = {
        "schema": "agentos.wardrobe-visual-semantic-receipt/v1",
        "backendReady": True,
        "checks": [
            {"code": "layer_match", "layer": "upper_main", "passed": True, "source": "vision"},
            {"code": "layer_match", "layer": "lower_main", "passed": True, "source": "vision"},
            {"code": "identity_preserved", "passed": True, "source": "vision"},
            {"code": "no_detached_reference", "passed": True, "source": "vision"},
        ],
    }
    receipt = evaluate_review(request)
    assert receipt["state"] == "verified"
    assert receipt["accepted"] is True
