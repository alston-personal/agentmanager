# Bounded Control Inbox service repair

Owner: AgentOS Core control transport. Incident: #845.

`Deploy Control Inbox Service Repair` is a manual maintenance deployment, not a
generic fallback for Realm/Node control-plane requests. Running it requires an
explicit deployment authorization for this workflow and accepted integration
generation. A source PR, green CI, or a request to continue investigating does
not authorize its execution.

The workflow runs the exact checked-out helper through the existing hosted SSH
deployment connection as `ubuntu`. It has no caller-supplied command, path,
Node, action, environment, or credential parameters. It does not wait for an
Oracle GitHub runner. The helper is restricted to:

1. verifying the existing Control Inbox service uses its fixed configuration;
2. checking GitHub inbox-read and local ONE controller authentication, retaining
   only HTTP status codes and never returning API bodies;
3. replacing a rejected credential only with an existing host-local credential
   that passes the same authentication check;
4. preserving all other environment lines, including the action allowlist and
   durable state location;
5. restarting only `agentos-control-inbox.service`, then rechecking auth;
6. restoring original credentials if restart/postchecks fail, unless another
   deployment changed the configuration, in which case it fails without
   overwriting the newer state.

If ONE is down, a route is missing, GitHub is unavailable, or no valid existing
credential is available, the helper fails without rebuilding Realm or retrying
an unrelated deployment. It never changes Core files, service definitions,
Realm credentials, the durable claim/outbox file, Windows tasks, or Mio workers.
The older `repair_control_inbox_github_auth_user.sh` remains a legacy full-env
rebuild; this maintenance path deliberately does not invoke it because that
script resets the host action allowlist.

The sanitized deployment receipt explicitly reports `end_to_end_verified=false`.
The authorized run [37260607129](https://github.com/alston-personal/agentmanager/actions/runs/37260607129)
on 2026-10-05 executed source `53863d329830a52ea1cd95536dbc582fac0bcd3a`
and returned `missing_equals_7_prev_cont_0_exportlike_0` before auth, writes,
or service restart. This disproves the earlier inference of one malformed line;
it does not identify the seven line contents or establish recovery.

Before authentication or mutation, shape normalization now allows at most seven
independent non-assignment lines, bounded to that observed incident count.
[systemd's EnvironmentFile contract](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml)
ignores independent lines without `=`. To avoid deleting portions of multiline
values, the helper rejects the entire normalization if an assignment contains a
quote, or any line contains a backslash, forbidden control/separator character,
BOM, or bare CR. Quotes in independent ignored lines or comments are literal:
[systemd v249's parser](https://github.com/systemd/systemd/blob/v249/src/basic/env-file.c)
enters quoted-value states only after `=`. It also rejects
export directives and more than seven non-assignment lines. Surviving assignments
must pass the existing strict key, duplicate, scope, allowlist, state, and auth
checks; their original bytes are preserved except rejected credential replacement.
Comments and blank lines are preserved. Failure codes report only aggregate
`missing_equals`, `prev_cont`, `exportlike`, and `lexical_unsafe` counts, plus
assignment/ignored/comment quote, backslash, control, and bare-CR line counts;
never line contents, keys, credentials, or values. Success reports the removed line count.
The first parser failure alone cannot establish the total malformed line count.
The follow-up authorized run [37277811979](https://github.com/alston-personal/agentmanager/actions/runs/37277811979)
at 2026-10-05 15:27 Asia/Taipei executed source `b7b970480be3394fc97b967a09038deca98871ac`
and stopped before auth, writes, or restart with seven ignored lines and one
lexically flagged line. That receipt does not identify its character class.
The former whole-file quote check could reject harmless quoted text; the refined
classification above also makes any remaining rejection distinguishable without
exposing configuration. This does not prove which class occurred on the host or
that maintenance will succeed. This new generation requires explicit maintenance
deployment authorization; the prior one-shot authorization was consumed by run
37277811979.
After maintenance, ChatGPT must submit a new short-lived bounded command through
#50 and observe its result. Expired commands must not be replayed. Only after
that transport receipt should Node freshness and the correct Mio DM session be
verified. A running service, accepted credential, or green workflow is not a
DM recovery receipt.
