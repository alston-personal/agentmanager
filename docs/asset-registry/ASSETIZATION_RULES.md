# Assetization Rules

A reusable asset is considered fully assetized only when it has:

1. a canonical source;
2. an explicit version or pinned source boundary;
3. a stable reuse contract;
4. regression tests or guards;
5. documentation;
6. at least two real consumers, unless the asset is a platform primitive that must be centralized immediately.

Lifecycle used by AgentOS:

- `candidate` — potentially reusable, still project-local;
- `extracted-first-consumer` — canonical shared implementation exists and at least one real consumer uses it;
- `broadly-proven` — at least two consumers reuse it without product-specific logic leaking back into the shared implementation;
- `platform-primitive` — centralized by policy even before the second consumer, for capabilities such as auth, commerce, analytics, support, app shell, and release infrastructure.

Every asset manifest should point to verification evidence and state what must happen before promotion to the next lifecycle state.
