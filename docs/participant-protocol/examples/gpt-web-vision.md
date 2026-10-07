# GPT Web Vision Participant

Status: adapter foundation implemented; runtime acceptance blocked on structured response harvesting.

Participant: `participant://agent/gpt-web`

## Purpose

Expose ChatGPT Web as a provider-neutral AgentOS vision participant for document and invoice extraction without coupling invoice code directly to browser automation.

Capabilities:

- `vision.document.extract/v1`
- `vision.invoice.extract/v1`

## Invocation boundary

The adapter validates an image inside the assigned workspace, hashes it, and builds a bounded desktop plan:

```text
open chatgpt.com
 -> paste governed image from workspace
 -> paste fixed structured-extraction prompt
 -> response adapter harvests JSON
 -> schema validation
 -> receipt
```

The current implementation intentionally stops before claiming READY because the repository does not yet contain a verified ChatGPT Web structured-response harvester.

## Safety and reliability

- no arbitrary shell
- no arbitrary filesystem path
- image must remain inside workspace
- png/jpeg/webp only
- max 12 MiB
- optional SHA-256 binding is enforced by `desktop.image_paste`
- capability is not scheduler-eligible until response harvesting is implemented and verified
- GUI timeout/failure must degrade to another Vision provider or local OCR; invoice foreground flow must not wait indefinitely

## Invoice routing target

```text
local/template OCR
  -> semantic confidence
  -> provider-neutral vision router
       -> Gemini API
       -> GPT Web participant
       -> future OpenAI API / other VLM
  -> canonical invoice IR
  -> cross-check / review
```

## Remaining acceptance

1. Implement ChatGPT Web response harvester.
2. Correlate request, image digest, response and receipt.
3. Parse only structured JSON matching the invoice contract.
4. Run the same public handwritten-invoice benchmark as Gemini/RapidOCR.
5. Prove bounded latency and 0 unsafe field claims before setting `verified=true`.
