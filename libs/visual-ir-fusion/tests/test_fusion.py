from visual_ir_fusion import FusionPolicy, IRSource, fuse_ir, score_preservation


def leaf(value, confidence=1.0, status="observed"):
    return {"value": value, "confidence": confidence, "status": status}


def test_main_visual_controls_silhouette_and_person_controls_accessories():
    main = {
        "schema": "visual-ir/v0.1",
        "dimensions": {
            "silhouette": leaf("water_drop"),
            "material": leaf("transparent_water"),
            "accessories": {"eyewear": leaf("none")},
        },
    }
    person = {
        "schema": "visual-ir/v0.1",
        "dimensions": {
            "silhouette": leaf("human"),
            "material": leaf("skin_and_cloth"),
            "accessories": {"eyewear": leaf("round_glasses")},
        },
    }

    fused = fuse_ir(
        [
            IRSource("main", main, 0.75),
            IRSource("person", person, 0.25),
        ],
        FusionPolicy(
            per_dimension={
                "silhouette": {"main": 0.95, "person": 0.05},
                "material": {"main": 0.95, "person": 0.05},
                "accessories.eyewear": {"main": 0.20, "person": 0.80},
            }
        ),
    )

    assert fused["dimensions"]["silhouette"]["value"] == "water_drop"
    assert fused["dimensions"]["material"]["value"] == "transparent_water"
    assert (
        fused["dimensions"]["accessories"]["eyewear"]["value"]
        == "round_glasses"
    )


def test_numeric_dimensions_are_weighted():
    a = {"schema": "visual-ir/v0.1", "dimensions": {"roundness": leaf(1.0)}}
    b = {"schema": "visual-ir/v0.1", "dimensions": {"roundness": leaf(0.0)}}
    fused = fuse_ir([IRSource("a", a, 0.75), IRSource("b", b, 0.25)])
    assert fused["dimensions"]["roundness"]["value"] == 0.75


def test_preservation_score_can_protect_silhouette():
    target = {
        "schema": "visual-ir/v0.1",
        "dimensions": {
            "silhouette": leaf("water_drop"),
            "accessories": {"eyewear": leaf("round_glasses")},
        },
    }
    actual = {
        "schema": "visual-ir/v0.1",
        "dimensions": {
            "silhouette": leaf("human"),
            "accessories": {"eyewear": leaf("round_glasses")},
        },
    }
    score = score_preservation(target, actual)
    assert score["dimensions"]["silhouette"] == 0.0
    assert score["dimensions"]["accessories.eyewear"] == 1.0
    assert score["overall"] == 0.5
