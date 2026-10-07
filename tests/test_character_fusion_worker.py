from scripts.character_fusion_worker import accept, fuse, water_drop_main_ir


def person_ir():
    return {
        "evidence_class": "ip-genome-visual-traits",
        "identity_traits": {
            "hair": {
                "primary": {
                    "value": "brown hair in a bun",
                    "confidence": 0.94,
                    "status": "observed",
                }
            },
            "eyewear": {
                "primary": {
                    "value": "round glasses",
                    "confidence": 0.99,
                    "status": "observed",
                }
            },
            "props": {
                "primary": {
                    "value": "coffee cup",
                    "confidence": 0.88,
                    "status": "observed",
                }
            },
        },
        "negative_constraints": ["do not preserve human anatomy"],
    }


def test_water_drop_fusion_keeps_species_and_transfers_identity_cues():
    target = fuse(water_drop_main_ir(), person_ir())
    assert target["body_plan"]["kind"] == "water_drop"
    assert target["identity_traits"]["material"]["primary"]["value"] == "transparent glossy water"
    assert target["identity_traits"]["eyewear"]["primary"]["value"] == "round glasses"
    assert target["identity_traits"]["props"]["primary"]["value"] == "coffee cup"


def test_water_drop_acceptance_rejects_costume_like_human():
    target = fuse(water_drop_main_ir(), person_ir())
    bad = {
        "body_plan": {"kind": "water_drop"},
        "human_torso_dominant": True,
        "human_head_embedded": False,
        "costume_like": True,
        "literal_human_hair": False,
    }
    result = accept("water-drop", target, bad)
    assert result["pass"] is False
    assert result["checks"]["no_human_torso"] is False
    assert result["checks"]["not_costume"] is False


def test_water_drop_acceptance_allows_water_native_identity_traits():
    target = fuse(water_drop_main_ir(), person_ir())
    good = {
        "body_plan": {"kind": "water_drop"},
        "material": "transparent water",
        "eyewear": "round glasses",
        "human_torso_dominant": False,
        "human_head_embedded": False,
        "costume_like": False,
        "literal_human_hair": False,
    }
    result = accept("water-drop", target, good)
    assert result["pass"] is True
