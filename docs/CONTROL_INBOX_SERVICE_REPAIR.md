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
After maintenance, ChatGPT must submit a new short-lived bounded command through
#50 and observe its result. Expired commands must not be replayed. Only after
that transport receipt should Node freshness and the correct Mio DM session be
verified. A running service, accepted credential, or green workflow is not a
DM recovery receipt.
