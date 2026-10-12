"""Conservative social discovery triage; never authorizes a reply or follows.

Input must come from the verified public discovery projection. A candidate may
be worth *considering*, but every external action needs separate reasoning,
platform authorization, root/parent verification and a sending receipt.
"""
from datetime import datetime, timezone
import re

TOPICS = {
    "animals": ("貓", "狗", "松鼠", "動物", "領養", "寵物"),
    "outfits": ("穿搭", "衣服", "鞋", "裙", "風格"),
    "walking": ("散步", "步道", "公園", "風景", "夕陽"),
    "daily": ("日常", "週末", "早餐", "通勤", "下雨"),
}
SCHEMA = "agentos.mio-social-discovery-triage/v1"
MAX_CANDIDATES = 30


def triage_public_discovery(projection, *, visited_authors=(), contacted_posts=(),
                            blocklisted_authors=(), max_candidates=5, persona_ir=None):
    if not isinstance(projection, dict) or projection.get("schema") != "agentos.persona-public-discovery/v1" or projection.get("status") != "PASS" or projection.get("write_allowed") is not False:
        return {"schema": SCHEMA, "status": "BLOCKED", "reason": "VERIFIED_PROJECTION_REQUIRED", "items": [], "write_allowed": False}
    rows = projection.get("items")
    if not isinstance(rows, list) or len(rows) > MAX_CANDIDATES:
        return {"schema": SCHEMA, "status": "BLOCKED", "reason": "BOUNDS_INVALID", "items": [], "write_allowed": False}
    if not isinstance(max_candidates, int) or isinstance(max_candidates, bool) or not 1 <= max_candidates <= 10:
        raise ValueError("max_candidates out of range")
    for value in (visited_authors, contacted_posts, blocklisted_authors):
        if not isinstance(value, (set, list, tuple, frozenset)) or len(value) > 5000:
            raise ValueError("unbounded interaction memory")
    visited = {str(x).lower().lstrip("@") for x in visited_authors}
    contacted = {str(x) for x in contacted_posts}
    blocked = {str(x).lower().lstrip("@") for x in blocklisted_authors}
    # Prefer the current validated persona interests over static defaults.
    # Never treat arbitrary unverified platform text as a new persona interest.
    topics = TOPICS
    if persona_ir is not None:
        interests = (persona_ir.get("current_self") or {}).get("interests_with_evidence") if isinstance(persona_ir, dict) else None
        if not isinstance(interests, list) or len(interests) > 20:
            return {"schema": SCHEMA, "status": "BLOCKED", "reason": "PERSONA_IR_INVALID", "items": [], "write_allowed": False}
        derived = {}
        for interest in interests:
            if not isinstance(interest, dict) or not isinstance(interest.get("topic"), str) or not isinstance(interest.get("basis"), list) or not interest["basis"]:
                continue
            topic = interest["topic"].strip()
            if not 1 <= len(topic) <= 45:
                continue
            keywords = {topic}
            for terms in TOPICS.values():
                if any(term in topic for term in terms):
                    keywords.update(terms)
            derived[topic] = tuple(sorted(keywords))
        if not derived:
            return {"schema": SCHEMA, "status": "BLOCKED", "reason": "NO_EVIDENCED_INTERESTS", "items": [], "write_allowed": False}
        topics = derived
    ranked = []
    for row in rows:
        if not isinstance(row, dict) or row.get("reply_allowed") is not False or row.get("decision") != "UNDECIDED":
            continue
        author, post, text = row.get("author"), row.get("post_id"), row.get("text_excerpt")
        if not isinstance(author, str) or not isinstance(post, str) or not isinstance(text, str):
            continue
        if author.lower() in blocked or post in contacted or author.lower() == str(projection.get("account", "")).lower():
            continue
        matches = [lane for lane, terms in topics.items() if any(term in text for term in terms)]
        if not matches:
            continue
        ranked.append({"post_id": post, "author": author, "topic_lanes": matches,
                       "familiarity": "previously_seen" if author.lower() in visited else "new_person",
                       "reason": "shared_observed_topic",
                       "next_step": "READ_CONTEXT_AND_DECIDE_IF_INTERACTION_WELCOME",
                       "reply_allowed": False, "write_allowed": False})
    # Variety is an ordering preference, not an engagement target or reply quota.
    ranked.sort(key=lambda row: (row["familiarity"] != "new_person",
                                 -len(row["topic_lanes"]), row["post_id"]))
    return {"schema": SCHEMA, "status": "PASS", "items": ranked[:max_candidates],
            "candidate_count": len(ranked), "write_allowed": False,
            "interaction_policy": "no_unsolicited_reply_without_separate_context_review"}
