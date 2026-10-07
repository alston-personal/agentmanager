from model2ir.reconciliation import ReconciliationPolicy, ReconciliationSource, weighted_reconcile_ir


def test_main_visual_preserves_body_plan_person_owns_accessory():
    main = {"schema": "character-ir-candidate/v0.6", "body_plan": {"kind": "water_drop", "confidence": 0.95}, "accessories": {"eyewear": "none"}}
    person = {"schema": "character-ir-candidate/v0.6", "body_plan": {"kind": "humanoid", "confidence": 0.9}, "accessories": {"eyewear": "round_glasses"}}
    result = weighted_reconcile_ir(
        [ReconciliationSource("main", main, 0.75), ReconciliationSource("person", person, 0.25)],
        ReconciliationPolicy(
            per_field={"accessories.eyewear": {"main": 0.2, "person": 0.8}},
            preserve_from={"body_plan.kind": "main"},
        ),
    )
    assert result["body_plan"]["kind"] == "water_drop"
    assert result["accessories"]["eyewear"] == "round_glasses"


def test_numeric_fields_are_weighted():
    a = {"schema": "character-ir-candidate/v0.6", "shape": {"roundness": 1.0}}
    b = {"schema": "character-ir-candidate/v0.6", "shape": {"roundness": 0.0}}
    result = weighted_reconcile_ir([ReconciliationSource("a", a, 0.75), ReconciliationSource("b", b, 0.25)])
    assert result["shape"]["roundness"] == 0.75


def test_rejects_competing_ir_schemas():
    try:
        weighted_reconcile_ir([ReconciliationSource("a", {"schema": "a/v1"}), ReconciliationSource("b", {"schema": "b/v1"})])
    except ValueError as exc:
        assert "compatible Character IR schemas" in str(exc)
    else:
        raise AssertionError("expected schema mismatch to fail")
