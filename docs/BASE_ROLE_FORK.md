# Base Role Employee Fork candidate (#151, #1768)

This module joins existing Employee Runtime, RoleRegistry, Employee Lifecycle,
and EmployeeThreadService; it is **not** a new worker loop, scheduler, role DB,
privilege system, or ONE Experience store.

## Contract

- Parent holds an active assignment lease.
- Child has a new durable Employee identity, private memory namespace, assignment
  and lease lifecycle; no model/executor binding or skills are copied.
- Role IDs must be a nonempty subset of parent's active roles. The role registry
  still hydrates baseline core.root policies. This is **not** authority to execute
  anything: ONE capability and runtime authorization remain required.
- Thread return requires terminal child receipt and does not modify parent's
  head unless an authorized caller applies it using existing optimistic fencing.
- The optional fork experience return is a *candidate reference* containing
  provenance/receipt linkage, never private memory or automatically accepted
  canonical Experience. ONE #117/#1768 decides acceptance, dedup, promotion and
  growth proof.
- A Fork is a durable worker identity, not a second Atlas/Root nor a daemon
  per conversation. For Receptionist, create its own scoped role in the registry
  and register a parent Employee with only that role. Short chats are sessions/
  assignments; do not create a permanent employee for each conversation.

## Source and evidence boundary

\`agent_core/employee_fork.py\` has isolated tests in
\`tests/test_employee_fork.py\`. These establish the static service contract,
not a live unattended fork/Executor run or actual ONE Experience write receipt.
It is not deployed and must not be reported as #470 closure.
