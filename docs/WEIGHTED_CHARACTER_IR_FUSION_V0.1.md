# Weighted Character IR Fusion Contract v0.1

## Purpose

This contract defines how existing AgentOS visual-character subsystems cooperate for multi-source character generation without creating a competing IR family.

Primary example:

```text
main visual + uploaded person photo -> fused Character IR -> rendered mascot
```

The water-drop demo is only the first acceptance fixture. Slime, leopard cat, robot, brand mascot, and other main visuals must use the same contract.

## Existing system responsibilities

### Character Blueprint

Owns image-derived structural evidence and reconstruction-oriented fields such as pose, body coverage, silhouette/body-plan evidence, proportions, semantic body parts, 3D proxy/reconstruction assumptions, and observed vs inferred vs assumed distinction.

### IP Genome Studio

Owns visual trait decomposition and consistency-oriented evidence such as hair/head-shape cues, eyewear, palette, clothing/accessory cues, props, companion/pet, style/material/surface cues where supported, confidence, locks, negative locks, and source references.

Its ICS representation may remain useful internally, but consumer integration must project relevant evidence into the shared Character IR vocabulary rather than introducing a parallel product-specific fusion schema.

### Model2IR

Owns 3D asset -> Canonical Character IR evidence, stabilization, diff/reconciliation and round-trip truth policy.

Generated 3D geometry is candidate evidence. It does not become canonical truth merely because it exists.

### Weighted reconciliation

The missing primitive added by this change is:

```python
weighted_reconcile_ir(sources, policy)
```

It combines compatible Character IR sources with global source weights, per-field source weights, explicit ownership locks via `preserve_from`, reconciliation provenance, and schema compatibility checks.

It does not perform image extraction and does not call an image renderer.

## Example authority policy

| Field family | Main visual | Person | Intent |
|---|---:|---:|---|
| body plan / silhouette | 0.95 | 0.05 | remain unmistakably the main visual |
| material / surface language | 0.90 | 0.10 | retain species/material identity |
| overall palette | 0.65 | 0.35 | accept personal accents |
| hair-shape cue | 0.55 | 0.45 | translate hair into main material language |
| eyewear | 0.20 | 0.80 | identity accessory comes from person |
| props | 0.10 | 0.90 | carried objects come from person |
| companion | 0.10 | 0.90 | pet/companion comes from person |

The exact numeric defaults are product policy, not canonical truth.

## Material-language translation

Weighted reconciliation alone does not mean literal copy/paste.

A person hair cue such as `bun + brown` combined with a water-drop material language should render as a water-flow bun silhouette with a brown-tinted identity accent, not human hair pasted on a droplet.

This translation belongs to the Character IR -> render adapter / character design compiler.

## End-to-end acceptance loop

```text
main visual
  -> Character Blueprint structural evidence where applicable
  -> IP Genome visual traits where applicable
  -> compatible Character IR evidence
                                      \
                                       > weighted_reconcile_ir
                                      /
person image
  -> Character Blueprint structural evidence
  -> IP Genome visual traits
  -> compatible Character IR evidence

-> target Character IR
-> character design / renderer adapter
-> generated image
-> re-extract evidence
-> diff / preservation score
-> PASS / retry / reject
```

## First acceptance fixture: water drop

Minimum protected invariants:

- output silhouette remains a single water-drop body
- no human head/body is embedded inside the droplet
- no person-wearing-a-water-drop-costume result
- hair cue is expressed through water/material form, not literal pasted hair
- identity accessories such as glasses may transfer
- person props/companion may transfer
- generated output must be re-extracted and checked before receiving a final serial/result status

## Legacy charactergenerator

The historical `alston-personal/charactergenerator` repository is valuable as a product fixture because it already implemented main image + fusion element images -> generated character.

Reuse interaction concept, historical examples and useful prompts as test fixtures. Do not reuse browser-direct provider credentials, prompt-only fusion as source of truth, or product-page-owned reconciliation logic.

## Security requirement

Any provider credential committed or embedded in historical browser source must be treated as exposed and rotated/revoked before reuse.

## Demo boundary

`studio-web /drop/` owns upload/selection UI, progress/result UX, serial/result presentation, calls to backend/library boundaries, and demo-specific copy/visuals. It does not own Character IR schema, extraction truth policy, fusion policy implementation, provider secrets, or reconciliation algorithms.
