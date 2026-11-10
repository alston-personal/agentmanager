# Independent WoW verification inspection while original Completion work waits

The original WoW #2134 WorkItem stays `waiting_external` or `blocked` according to the Completion Controller and its finite retry policy. A separate, **read-only**, source-controlled Paw inspection is permitted when the exact original item's `last_blocker_kind` is `VERIFICATION`, even if a retry timer has not expired. This creates a separate canonical Core WorkItem and an Employee assignment `paw-wow-2134-inspect-v1`, but does NOT reset, wake, resume or mark done the original WoW project task. Other waiting/blocked kinds such as `HUMAN_AUTH` remain excluded.

The actual ONE/Supervisor process must independently deliver a verified wake and claim; a pending assignment is not execution. The inherited role/skill remains `sector.paw` / `engineering.work.inspect` with no repository mutation, model invocation, merger or deployment capability from this integration. Existing #2134 and Draft PR #2135 continue to own the product implementation.

This eliminates a circular dependency in which a blocked engineering WorkItem could not even receive independent read-only investigation of its blocker.
