# Light cleanup for AI text shown in the UI — less markdown noise, safer HTML.

from __future__ import annotations

import html
import re


# Shared voice for pastoral-facing AI (insights + sermon tools)
PASTOR_VOICE_SYSTEM = (
    "You are a helpful ministry teammate talking with a modern-day pastor. "
    "Write like a clear, warm colleague in everyday English — not King James English, "
    "not a sermon, and not a formal corporate memo. "
    "Do not use markdown headings (no # or ##). "
    "Do not use numbered section titles like '1) Snapshot'. "
    "Use short paragraphs. If you need a list, use simple dashes. "
    "Be practical and specific. If the data is thin, say so honestly. "
    "Never invent people, emails, or facts that are not in the material you were given."
)


def format_ai_prose(text: str | None) -> str:
    """
    Turn model output into readable HTML for glass panels.
    Strips ## heading spam and keeps light structure.
    """
    if not text:
        return ''
    raw = str(text).replace('\r\n', '\n').strip()
    # Normalize markdown headers → plain bold labels
    raw = re.sub(r'(?m)^\s{0,3}#{1,6}\s*', '', raw)
    # Drop decorative horizontal rules
    raw = re.sub(r'(?m)^\s*([-*_]){3,}\s*$', '', raw)
    # Collapse excessive blank lines
    raw = re.sub(r'\n{3,}', '\n\n', raw).strip()

    parts: list[str] = []
    for block in re.split(r'\n\s*\n', raw):
        block = block.strip()
        if not block:
            continue
        lines = [ln.rstrip() for ln in block.split('\n')]
        # Bullet block
        if all(re.match(r'^\s*([-*•]|\d+[.)])\s+', ln) for ln in lines if ln.strip()):
            items = []
            for ln in lines:
                ln = ln.strip()
                if not ln:
                    continue
                item = re.sub(r'^([-*•]|\d+[.)])\s+', '', ln)
                items.append(f'<li>{_inline_format(item)}</li>')
            parts.append('<ul class="ai-prose-list">' + ''.join(items) + '</ul>')
        elif len(lines) == 1 and len(block) <= 72 and not re.search(r'[.!?]$', block):
            # Short header-like line → bold label, not a full paragraph
            parts.append(f'<p class="ai-prose-p"><strong>{_inline_format(block)}</strong></p>')
        else:
            joined = ' '.join(ln.strip() for ln in lines if ln.strip())
            parts.append(f'<p class="ai-prose-p">{_inline_format(joined)}</p>')
    return '\n'.join(parts) if parts else f'<p class="ai-prose-p">{html.escape(raw)}</p>'


def _inline_format(text: str) -> str:
    esc = html.escape(text)
    # **bold** and *italic* (simple)
    esc = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', esc)
    esc = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', esc)
    esc = re.sub(r'`([^`]+)`', r'<code>\1</code>', esc)
    return esc


def plain_snippet(text: str | None, needle: str, radius: int = 90) -> str:
    """Plain-text snippet around first case-insensitive match."""
    if not text:
        return ''
    plain = re.sub(r'<[^>]+>', ' ', str(text))
    plain = re.sub(r'\s+', ' ', plain).strip()
    if not plain:
        return ''
    n = (needle or '').strip()
    if not n:
        return plain[: radius * 2] + ('…' if len(plain) > radius * 2 else '')
    low = plain.lower()
    idx = low.find(n.lower())
    if idx < 0:
        return plain[: radius * 2] + ('…' if len(plain) > radius * 2 else '')
    start = max(0, idx - radius)
    end = min(len(plain), idx + len(n) + radius)
    snippet = plain[start:end]
    if start > 0:
        snippet = '…' + snippet
    if end < len(plain):
        snippet = snippet + '…'
    return snippet
