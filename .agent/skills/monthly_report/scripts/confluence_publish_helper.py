#!/usr/bin/env python3
"""Confluence Publisher Helper via vopc5750 CDP Session (capability://confluence.page.publish).

Enforces:
1. Only runs on browser-capable node (`vopc5750`) via authenticated CDP session (port 9229).
2. Uses Confluence REST API `POST /rest/api/content/{id}/child/attachment` with `X-Atlassian-Token: nocheck`.
3. Automatically converts uploaded filenames in storage HTML into native Confluence attachment links:
   `<ac:link><ri:attachment ri:filename="..." /></ac:link>`.
"""
from __future__ import annotations

import re


def link_attachments_in_storage_html(html: str, filenames: list[str]) -> str:
    """Replace bare/code-wrapped attachment filenames with Confluence native <ac:link> tags."""
    result = html
    for fname in filenames:
        tag = f'<ac:link><ri:attachment ri:filename="{fname}" /></ac:link>'
        # Replace <code>filename</code> first, then bare filename (avoiding double-wrapping)
        result = re.sub(rf"<code>\s*{re.escape(fname)}\s*</code>", tag, result)
        result = re.sub(rf'(?<!ri:filename="){re.escape(fname)}(?!")', tag, result)
    return result
