# Mio Threads operational runbook (2026-09-20, Asia/Taipei)

**Purpose:** Preserve the *working retrieval and execution path* across new chats, agents, and computers. Consult this file **before** saying that Oracle or GitHub Actions is inaccessible. This document records verified past observations; re-check current state at each handoff. It is not a claim that image publishing or autonomous replying is complete.

## Identifiers and boundaries

- Persona: 澪 / Mio; Threads account: `@sunlake.milkcat`.
- Code: `alston-personal/agentmanager`, live branch `core/integration`.
- Persona memory: `alston-personal/my-agent-data`, `main`, `personas/sunlake-milkcat/events/events.jsonl`.
- Shared runtime owns API, authorization, media, publishing and receipts. Persona owns content, policies, schedule and event references. Do not put credentials in persona repos or receipts.
- Image work: PR [#405](https://github.com/alston-personal/agentmanager/pull/405), feature branch `feature/mio-image-publish-20260920`; **do not merge or claim complete without testing real image transport, image readback and public URL**. Do not downgrade an IMAGE request to TEXT.

## Critically important: How to fetch *push* workflow results

`mcp__GitHub__fetch_commit_workflow_runs` **only returns PR-triggered workflow runs** in this connection. An empty result for a push commit does **not** mean Actions never ran. This exact mistake led to many false "not verified" responses.

1. Via connected GitHub `fetch`, read `https://api.github.com/repos/alston-personal/agentmanager/actions/runs` (a bare collection URL worked on 2026-09-20). Parse `workflow_runs[]` and filter by **`head_sha`, workflow `name`/`path`, and `event: push`**; follow pagination only as supported. This read endpoint is different from the refused `/actions/workflows/<workflow>.yml/runs?event=push&per_page=10` URL.
2. Use connected GitHub `fetch_workflow_run_jobs({repo_full_name:"alston-personal/agentmanager",run_id})`. Identify the actual publish/install job ID.
3. Use `fetch_workflow_job_logs({repo_full_name:"alston-personal/agentmanager",job_id})` and inspect **runtime output lines**, not merely the job status or echoed shell source. Require `mio_approved_receipt=PASS`, `galaxy_day1_publish=PASS` (or authenticated already-present verification), actual `galaxy_day1_object_id` and `galaxy_day1_permalink`; cross-check the Threads post and expected text. For image, require media_type IMAGE and actual visible image; for reply, require a real reply ID. Do not expose tokens or secrets.
4. Read the existing `.github/workflows/oracle-publish-mio-approved.yml` and `scripts/publish_galaxy_threads_day1_user.sh` from current `core/integration` before changing a workflow. Never blindly retry a post if its result is unknown; read the platform state by exact intent/object ID first.

## Confirmed successful push-run proof (2026-09-20)

- New original TEXT article `personas/mio/approved/mio-post-20260920-small-discoveries-v1.txt`, source commit `ea2adc001eabefa107f68ae33f8dc06778942c8c`.
- [Actions run 35484386298](https://github.com/alston-personal/agentmanager/actions/runs/35484386298), publish job `106007938741`; job log emitted `mio_approved_receipt=PASS`, `galaxy_day1_publish=PASS`, Threads ID `18042529955827294`, permalink `https://www.threads.com/@sunlake.milkcat/post/DdfhumnFHdz`.
- This establishes that the GitHub push → self-hosted Oracle runner → existing governed publisher → Threads *TEXT* path worked at that time. It does not establish image publishing or unattended recurring posts.

## Confirmed reply monitoring + memory, remaining blockers

- [Actions run 35486126362](https://github.com/alston-personal/agentmanager/actions/runs/35486126362), monitor install job `106012720999`: `galaxy_experiment_monitor_receipt=PASS`, monitor read 15 replies. It saw reader cat comment ID `18234417796318016` and *human-assisted* Mio reply ID `18368916244215087`, permalink `https://www.threads.com/@sunlake.milkcat/post/Ddfl8WvE2C0`.
- These two events were written to `my-agent-data` `main` in commit `19836b0dce4179cbc481e3e57e32e56664ea578b`. A manual reply can be a Persona event once observed; do **not** invent source or claim autonomous posting.
- The same monitor logs showed `mio_social_decision=DEFERRED:RuntimeError` and `mio_social_outbound=DISCOVERY_UNAVAILABLE:threads_api_unavailable_http_500...`. **Autonomous reply delivery has not been verified**; diagnose decision relay and search API separately. A monitor `PASS` or `pending=0` is not a successful reply receipt.
- Existing code: `scripts/monitor_galaxy_threads_experiment_user.py`, `scripts/mio_persona_social_loop_user.py`, `scripts/sync_sunlake_milkcat_persona_user.py`, `scripts/install_galaxy_threads_experiment_monitor_user.sh`. Monitor uses an experiment snapshot; make sure new comments are not lost on failed reads, decision failures, or snapshot replacement.

## Continuation contract

First retrieve this runbook, current branch/PR state, latest push workflow runs **via the collection**, then job logs. Report verified platform evidence, not the number of commits or a rephrased plan. If the specific capability remains blocked, give the exact failing step and relevant job/error. User should not have to repeat the above path.


## Verified new post and governed reply (2026-09-20)

- New approved TEXT post `mio-post-20260920-cat-hello-v1.txt`: [Actions run 35486982735](https://github.com/alston-personal/agentmanager/actions/runs/35486982735), `mio_approved_receipt=PASS`, `galaxy_day1_publish=PASS`, platform ID `17994092795835001`, permalink `https://www.threads.com/@sunlake.milkcat/post/DdfomfNFPih`.
- Approved reply to reader `vivian780927`'s comment ID `18100785275370622` ("看不懂"): [Actions run 35487296837](https://github.com/alston-personal/agentmanager/actions/runs/35487296837), `persona_threads_reply_receipt=PASS`, `persona_threads_reply_publish=PASS:18100785275370622:17978287527132218`, and readback-confirmed permalink `https://www.threads.com/@sunlake.milkcat/post/DdfphJrFCpy`. This was an **approved governed reply**, not an autonomous generated decision.
- Existing approved-reply path: create exactly ONE new `personas/mio/approved/replies/mio-reply-*.json` per push in `core/integration`; existing workflow `.github/workflows/oracle-publish-sunlake-persona-replies.yml` triggers. Manifest has `root_post_id`, `reply_to_id`, `comment_author`, `expected_comment_text`, `text`; runtime verifies target/author/exact text, checks for prior replies, uses stable intent and requires platform readback. Keep checkout `fetch-depth: 0` and inline Python preflight compile; otherwise historical failures [35487025360](https://github.com/alston-personal/agentmanager/actions/runs/35487025360) and [35487064759](https://github.com/alston-personal/agentmanager/actions/runs/35487064759) recur. Failed reply create/publish [35487130528](https://github.com/alston-personal/agentmanager/actions/runs/35487130528) returned code 24.
- Core shared Threads provider repair: [social runtime rollout 35487237651](https://github.com/alston-personal/agentmanager/actions/runs/35487237651) succeeded, with same-container retry on publish code 24, never recreating a container. Subsequent approved reply succeeded as above.
- Verified records were appended to `alston-personal/my-agent-data` `main` `personas/sunlake-milkcat/events/events.jsonl`, commit `bf78ad0015a720fcfdc99e22df20884b3f4e5fdc`.
- **Still open:** automatic reply decisions use the Antigravity relay and are failing with `persona_decision_executor_failed:provider=claude:returncode=none:timed_out=false:category=other` in [monitor run 35487397344](https://github.com/alston-personal/agentmanager/actions/runs/35487397344). An approved reply delivered via the governed path does NOT establish fully autonomous replies. Durable history replay is installed; it should preserve unprocessed comments, but must be tested with a new real comment + automatic decision and receipt.
