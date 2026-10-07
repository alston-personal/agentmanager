from model2ir.reconciliation import (
    ReconciliationPolicy,
    ReconciliationSource,
    weighted_reconcile_ir,
)


def test_main_visual_preserves_body_plan_person_owns_accessory():
    main = {
        "schema": "character-ir-candidate/v0.6",
        "body_plan": {"kind": "water_drop", "confidence": 0.95},
        "accessories": {"eyewear": "none"},
    }
    person = {
        "schema": "character-ir-candidate/v0.6",
        "body_plan": {"kind": "humanoid", "confidence": 0.9},
        "accessories": {"eyewear": "round_glasses"},
    }
    result = weighted_reconcile_ir(
        [
            ReconciliationSource("main", main, 0.75),
            ReconciliationSource("person", person, 0.25),
        ],
        ReconciliationPolicy(
            per_field={
                "accessories.eyewear": {"main": 0.2, "person": 0.8}
            },
            preserve_from={"body_plan.kind": "main"},
        ),
    )
    assert result["body_plan"]["kind"] == "water_drop"
    assert result["accessories"]["eyewear"] == "round_glasses"


def test_numeric_fields_are_weighted():
    a = {
        "schema": "character-ir-candidate/v0.6",
        "shape": {"roundness": 1.0},
    }
    b = {
        "schema": "character-ir-candidate/v0.6",
        "shape": {"roundness": 0.0},
    }
    result = weighted_reconcile_ir(
        [
            ReconciliationSource("a", a, 0.75),
            ReconciliationSource("b", b, 0.25),
        ]
    )
    assert result["shape"]["roundness"] == 0.75


def test_rejects_competing_ir_schemas():
    try:
        weighted_reconcile_ir(
            [
                ReconciliationSource("a", {"schema": "a/v1"}),
                ReconciliationSource("b", {"schema": "b/v1"}),
            ]
        )
    except ValueError as exc:
        assert "compatible Character IR schemas" in str(exc)
    else:
        raise AssertionError("expected schema mismatch to fail")


def test_main_visual_and_ip_genome_trait_fragments_can_share_one_character_ir():
    structural_main = {
        "schema": "character-ir-candidate/v0.6",
        "body_plan": {"kind": "water_drop", "confidence": 0.99},
    }
    main_traits = {
        "evidence_class": "ip-genome-visual-traits",
        "identity_traits": {
            "material": {
                "primary": {
                    "value": "transparent water",
                    "confidence": 0.98,
                    "status": "observed",
                }
            },
            "eyewear": {
                "primary": {
                    "value": "none",
                    "confidence": 0.9,
                    "status": "observed",
                }
            },
        },
    }
    person_traits = {
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
        "negative_constraints": ["no human torso transfer"],
    }

    result = weighted_reconcile_ir(
        [
            ReconciliationSource("main_structural", structural_main, 1.0),
            ReconciliationSource("main_traits", main_traits, 0.75),
            ReconciliationSource("person_traits", person_traits, 0.25),
        ],
        ReconciliationPolicy(
            preserve_from={"body_plan.kind": "main_structural"},
            per_field={
                "identity_traits.eyewear.primary.value": {
                    "main_traits": 0.2,
                    "person_traits": 0.8,
                },
                "identity_traits.material.primary.value": {
                    "main_traits": 0.95,
                    "person_traits": 0.05,
                },
                "identity_traits.props.primary.value": {
                    "main_traits": 0.1,
                    "person_traits": 0.9,
                },
            },
        ),
    )

    assert result["schema"] == "character-ir-candidate/v0.6"
    assert result["body_plan"]["kind"] == "water_drop"
    assert (
        result["identity_traits"]["material"]["primary"]["value"]
        == "transparent water"
    )
    assert (
        result["identity_traits"]["eyewear"]["primary"]["value"]
        == "round glasses"
    )
    assert result["identity_traits"]["eyewear"]["primary"]["confidence"] == 0.99
    assert result["identity_traits"]["props"]["primary"]["value"] == "coffee cup"
    assert result["negative_constraints"] == ["no human torso transfer"]
