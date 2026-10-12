### Mio public discovery contract (candidate for #1825)

The stand-alone `scripts/persona_public_discovery_contract.py` supports an offline,
bounded **read-only projection** of public Threads post candidates, not discovery itself.
It requires an independently verified authorized public-feed/public-post adapter
receipt, bound to the Mio account; the existing `post.read` owned-post adapter
receipt is explicitly **insufficient**. It rejects private, stale, self-authored,
unbounded, duplicate, or missing-provenance items. The projection sets
`write_allowed=false`, each candidate remains `UNDECIDED`, and no publish or
external reply authority is granted. It does not read credentials or DM content,
schedule a PDCA action, or write persona state. Production adapter ownership,
account isolation, a node-authoritative actual public read, IR-based evaluation,
and exact-parent real reply receipts all remain **unverified / not implemented**
by this stage. Growth Proof is not claimed. Tests run without platform writes.
