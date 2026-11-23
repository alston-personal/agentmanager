#!/usr/bin/env python3
"""Confluence Publisher Helper via vopc5750 CDP Session (capability://confluence.page.publish).

Enforces:
1. Only runs on browser-capable node (`vopc5750`) via authenticated CDP session (port 9229).
2. Uses Confluence REST API `POST /rest/api/content/{id}/child/attachment` with `X-Atlassian-Token: nocheck`.
3. Automatically converts uploaded filenames in storage HTML into native Confluence attachment links:
   `<ac:link><ri:attachment ri:filename="..." /></ac:link>`.
4. Preserves Page Properties (`<ac:structured-macro ac:name="details">`) wrapper around top metadata
   tables so parent Page Properties Report pages (e.g. DQDIS Weekly Report) always index the report.
5. Uses real Confluence user mentions (`<ac:link><ri:user ri:userkey="..." /></ac:link>`) instead of
   plain `@username` text.
"""
from __future__ import annotations

import re


def format_user_mention(user_key: str | None = None, username: str = "alston.huang") -> str:
    """Return a real Confluence Storage Format user mention tag."""
    if user_key and user_key.strip():
        return f'<ac:link><ri:user ri:userkey="{user_key.strip()}" /></ac:link>'
    return f'<ac:link><ri:user ri:username="{username.strip()}" /></ac:link>'


def wrap_page_properties_details(table_html: str) -> str:
    """Wrap the top metadata table in Confluence Page Properties (details) macro."""
    if 'ac:name="details"' in table_html:
        return table_html
    return (
        '<ac:structured-macro ac:name="details">'
        f"<ac:rich-text-body>{table_html}</ac:rich-text-body>"
        "</ac:structured-macro>"
    )


def link_attachments_in_storage_html(html: str, filenames: list[str]) -> str:
    """Replace bare/code-wrapped attachment filenames with Confluence native <ac:link> tags."""
    result = html
    for fname in filenames:
        tag = f'<ac:link><ri:attachment ri:filename="{fname}" /></ac:link>'
        # Replace <code>filename</code> first, then bare filename (avoiding double-wrapping)
        result = re.sub(rf"<code>\s*{re.escape(fname)}\s*</code>", tag, result)
        result = re.sub(rf'(?<!ri:filename="){re.escape(fname)}(?!")', tag, result)
    return result
