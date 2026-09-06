# Social Runtime Host-Local Provisioning

Issue: #267.

This operator boundary prepares the shared social runtime for real product OAuth and governed writes without moving product credentials or the Core control token through GitHub, workflow inputs, chat, browser JavaScript, receipts, or public HTTP responses.

## Tool

`python3 scripts/social_runtime_local_config.py`

The production defaults are fixed under `/home/ubuntu/.config/agentos`:

- runtime env: `social-runtime.env`
- product secret files: `social-products/<product_id>.env`

All writes are atomic and mode `0600`. Secret values are never printed by the tool.

## Control-plane token

Run on the Oracle host as the runtime owner:

```bash
python3 scripts/social_runtime_local_config.py ensure-control-token
```

If `AGENTOS_SOCIAL_CONTROL_TOKEN` is empty, the tool creates a cryptographically random value in the host-local runtime env. If a value already exists, it is preserved. The command reports only `GENERATED` or `PRESERVED`.

The control token remains separate from every product key and is still usable only against the private `127.0.0.1` runtime control route. The public gateway must continue to block `/internal/v1/social/acceptances`.

## Product registration

After the product's canonical return base is accepted, register it locally:

```bash
python3 scripts/social_runtime_local_config.py register-product \
  leopardcat-tarot \
  https://studio.milkcat.org/leopardcat-tarot
```

The helper:

1. validates a bounded product ID and HTTPS return base;
2. generates a random product API key only for a new registration;
3. updates `AGENTOS_SOCIAL_PRODUCTS_JSON` atomically;
4. writes the product's server-side credential to the fixed host-local file `social-products/<product_id>.env`;
5. never prints the key value;
6. is idempotent for the exact same registration;
7. fails closed if an existing product is silently pointed at a different return base.

A return-base change is therefore an explicit migration event rather than an accidental credential reuse.

## Safe status

```bash
python3 scripts/social_runtime_local_config.py status leopardcat-tarot
```

Status returns booleans only: whether the product is registered, whether its fixed secret file exists, and whether the Core control token is configured. It does not expose provider credentials, product API keys, or the control token.

## Boundary with product repos

Core owns generation and storage of the shared-runtime product credential. A product backend may consume its host-local `social-products/<product_id>.env` secret through its deployment/runtime boundary, but the value must never be committed to the product repository or sent to browser code.

For LeopardCat, actual registration should wait until `https://studio.milkcat.org/leopardcat-tarot` is verified as the canonical product return base. This Core tool does not implement the LeopardCat route, UI, or product deployment.
