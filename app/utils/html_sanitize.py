# app/utils/html_sanitize.py
# Sanitize user-supplied HTML for rich-text fields (Quill, pastoral content).

import bleach

ALLOWED_TAGS = [
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'sub', 'sup',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
    'a', 'span', 'div',
]

ALLOWED_ATTRIBUTES = {
    '*': ['class'],
    'a': ['href', 'title', 'target', 'rel'],
    'span': ['class', 'style'],
    'p': ['class', 'style'],
    'div': ['class', 'style'],
}

ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']

SERMON_RICH_FIELDS = frozenset({
    'header_text', 'footer_text', 'conclusion_text', 'notes',
})

SECTION_RICH_FIELDS = frozenset({'content', 'notes'})


def sanitize_plain_text(value: str | None) -> str:
    if not value:
        return ''
    return bleach.clean(str(value), tags=[], attributes={}, strip=True).strip()


def sanitize_rich_html(value: str | None) -> str:
    if not value:
        return ''
    cleaned = bleach.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return cleaned.strip()


def sanitize_sermon_meta(data: dict) -> dict:
    if not data:
        return data
    out = dict(data)
    for key, value in out.items():
        if value is None:
            continue
        if key in SERMON_RICH_FIELDS:
            out[key] = sanitize_rich_html(value) or None
        elif isinstance(value, str):
            out[key] = sanitize_plain_text(value) or None
    return out


def sanitize_sermon_sections(sections: list) -> list:
    sanitized = []
    for sec in sections or []:
        if not isinstance(sec, dict):
            continue
        row = dict(sec)
        for key, value in row.items():
            if value is None:
                continue
            if key in SECTION_RICH_FIELDS:
                row[key] = sanitize_rich_html(value)
            elif isinstance(value, str):
                row[key] = sanitize_plain_text(value)
        sanitized.append(row)
    return sanitized


def sanitize_vault_payload(data: dict) -> dict:
    if not data:
        return data
    out = dict(data)
    for key in ('title', 'section_type', 'scripture_reference', 'source_url', 'visibility'):
        if key in out and out[key] is not None:
            out[key] = sanitize_plain_text(out[key])
    for key in ('content', 'notes'):
        if key in out and out[key] is not None:
            out[key] = sanitize_rich_html(out[key])
    if 'tags' in out:
        if isinstance(out['tags'], list):
            out['tags'] = [sanitize_plain_text(t) for t in out['tags'] if t]
        elif isinstance(out['tags'], str):
            out['tags'] = [sanitize_plain_text(t) for t in out['tags'].split(',') if t.strip()]
    return out