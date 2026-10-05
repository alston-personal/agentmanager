# Document Stamp Recognition

`document.stamp-recognition` is a vendor-neutral visual identity capability.

It is intentionally separate from invoice OCR. Financial Intake may use a
matched stamp to recover a vendor name or tax ID, but this capability itself only
answers:

1. Is there a stamp?
2. Is this the same physical/visual stamp seen before?
3. Is it a different stamp that belongs to the same verified entity?
4. Is the evidence too weak to auto-apply remembered attributes?

## Why this is separate

A stamp is a reusable visual entity. The same capability can be reused for
invoices, receipts, contracts, acceptance forms, customs documents, certificates,
or any other document class.

## Matching states

- **same_stamp** — high visual/fingerprint similarity to a confirmed stamp.
- **same_entity_new_stamp** — verified entity attributes agree, but the visual
  fingerprint is materially different. Create a new stamp version instead of
  pretending it is the old stamp.
- **unknown_stamp** — no useful prior match; OCR/extraction + human confirmation
  may create a new entity/sample.
- **uncertain** — insufficient evidence. Never auto-fill remembered business
  data from this state.

## Learning loop

First encounter:

`detect → OCR/visual features → human confirmation → stamp entity + sample`

Later encounter:

`detect → fingerprint → nearest confirmed samples → match decision`

A confirmed match can bypass repeated OCR for stable attributes, while still
retaining the current sample and match evidence for audit.

## Storage model

Recommended tables are independent from invoice tables:

- `stamp_entities`
- `stamp_versions`
- `stamp_samples`
- `stamp_matches`

Consumer records only store references such as `stamp_id` / `entity_id`.
