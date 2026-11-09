---
name: mio-threads-publisher
description: Reuse the existing AgentOS Oracle governed Threads publisher for Mio. Do not recreate publishing infrastructure.
---

# Mio Threads publisher

## Canonical execution trail
- Repository: alston-personal/agentmanager; publishing branch used by the successful run: core/integration.
- Approved text: personas/mio/approved/mio-post-<unique-slug>.txt (<=500 characters). Optional image manifest uses the same key with .json and an existing verified asset under personas/mio/approved/assets/.
- Oracle bootstrap action: agentos.social_threads_mio_approved.publish. Parameters: source_commit (immutable exact 40-hex commit) and post_key (filename stem).
- Existing implementation: agentos_node/bootstrap_control.py and scripts/publish_galaxy_threads_day1_user.sh. Existing GitHub Actions run 35495831674 / job 106038465682 is a verified historical reference; inspect the run's workflow file and trigger before submitting.
- GitHub Actions runner stages the constrained bootstrap request for Oracle; Oracle Social Runtime publishes and reads back Threads. Never send credentials through ChatGPT or store them in the skill.

## Execution
1. Read latest Threads state and existing approved posts before authoring; avoid duplicate text and duplicate image posts.
2. Create one uniquely named approved post file on the canonical publishing branch, and optional manifest only when there is an exact existing image asset. A GitHub commit is a *request*, not evidence of publication.
3. Verify a fresh Actions run was triggered on the exact commit, follow its Oracle receipt and social-status readback. If the workflow was not triggered, investigate the real workflow path/trigger and authorized execution gateway; do not rerun the old successful post.
4. Report success only with a matching account, text, media type, Threads object ID and public permalink. Distinguish actions success from actual Threads readback.
5. When outcome is unknown, query the write_intent_id/post_key and exact text via Social Runtime before retrying. Never issue a second publish merely because an Actions run timed out.

## Autonomy (not proved by a manual publish)
The scheduler must independently enqueue a *new* approved post/decision using this same capability, and record its trigger, identity, Oracle receipt and Threads readback. Manual ChatGPT requests and recurring reminders are not proof of AgentOS autonomous operation. Verify scheduler state and next execution in Oracle before claiming P3 complete.
