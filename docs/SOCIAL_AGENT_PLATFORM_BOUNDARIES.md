# Social Agent Platform Boundaries

## Goal

The Social Agent Modular Platform is platform-neutral. Galaxy/social runtime is the I/O layer. Provider-specific behavior lives behind adapters.

```
Account / Persona / Content / Analytics / Conversation
                    |
              Social Orchestrator
                    |
             Galaxy Social Runtime
                    |
        +-----------+-----------+
        |           |           |
     Threads     Instagram    Facebook
     adapter      adapter       adapter
```

## Module ownership

- **Account / Identity** selects an account binding and platform.
- **Content / Media** produces provider-neutral content artifacts.
- **Publish** asks Galaxy to publish; it never calls a provider API directly.
- **Conversation / Reply** reads a conversation and asks Galaxy to reply.
- **Analytics** asks Galaxy for provider-neutral metrics when available.
- **Relationship** consumes social evidence and may request provider actions such as follow only when the selected adapter declares support.
- **Persona** consumes events/relationship state; it does not scrape or call social providers.
- **Galaxy** owns OAuth, provider credentials, provider adapters, write acceptance, API calls and secret-free receipts.

## Capability discovery

Networks do not expose identical features. Callers must query/consult platform capability availability rather than assuming that a Threads operation exists on Instagram or Facebook.

Current runtime:
- Threads: identity/read/publish/reply/search/insights are implemented.
- Instagram/Facebook: contract names exist but runtime adapters are not yet accepted.
- Follow/unfollow: not claimed as supported until a provider-specific operation is verified and implemented.

## Migration rule

Mio remains on the working Threads path while capabilities are extracted. Each migrated module must preserve:
1. existing provider receipt semantics,
2. idempotency/readback behavior,
3. account binding checks,
4. one-shot write acceptance,
5. regression coverage,
6. a fallback adapter until live smoke tests pass.
