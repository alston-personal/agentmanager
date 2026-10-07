# AgentOS Mobile iOS bootstrap client

This directory is the first native client skeleton for #1528.

Implemented source contracts:
- parse `agentos://join?one=...&v=v1`
- construct canonical `agentos.node-manifest/v0.1` with mobile profile
- request -> status -> claim calls against existing ONE device flow
- Keychain helper for the claimed node token

Not yet claimed:
- a complete Xcode project
- APNs registration
- background wake reliability
- notification executor
- camera/photo executor
- signed install on a physical iPhone

The claimed node token must be persisted in Keychain; the join claim secret is temporary and must not be logged or committed.
