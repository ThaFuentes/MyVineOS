# Optional AI-assisted structured parsing for donations emails + sermon imports.
# Always designed as an enhancer on top of deterministic rule parsers:
#   mode='rules'  — never call AI
#   mode='auto'   — call AI only when rules look weak
#   mode='ai'     — always try AI (still falls back to rules if AI fails)

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.utils.ai_client import ai_status, call_ai, extract_json_payload, log_ai_usage


def normalize_parse_mode(raw: str | None, default: str = 'auto') -> str:
    v = (raw or default).strip().lower()
    if v in ('rules', 'rule', 'none', 'off', 'no_ai', 'without_ai'):
        return 'rules'
    if v in ('ai', 'always', 'force_ai', 'with_ai'):
        return 'ai'
    return 'auto'


def ai_configured() -> bool:
    try:
        return bool(ai_status().get('configured'))
    except Exception:
        return False


def _strip_for_prompt(text: str, limit: int = 9000) -> str:
    text = (text or '').replace('\x00', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    if len(text) > limit:
        text = text[:limit] + '\n\n[truncated]'
    return text.strip()


def ai_parse_donation_email(
    subject: str,
    body: str,
    from_addr: str = '',
    *,
    rules_hint: dict | None = None,
) -> tuple[Optional[dict], Optional[str]]:
    """
    Ask AI for structured gift fields. Returns (dict, error).
    Never invents amounts if not present — model is instructed to use null.
    """
    if not ai_configured():
        return None, 'AI is not configured (Settings → AI Providers).'

    system = (
        'You extract donation/gift data from payment-provider notification emails. '
        'Return ONLY a JSON object with keys: '
        'processor, amount, currency, donor_name, donor_email, confirmation_number, '
        'method, date (YYYY-MM-DD), fund_label, is_recurring (bool), notes, confidence (0-100). '
        'If a field is unknown use empty string, 0 for amount, false for is_recurring. '
        'Do not invent amounts or confirmation numbers that are not in the email. '
        'processor is one of: stripe, paypal, cashapp, venmo, tithely, zelle, pushpay, '
        'givelify, planning_center, ach, unknown.'
    )
    hint = ''
    if rules_hint:
        hint = (
            '\nRule-based parser already suggested (may be incomplete):\n'
            + json.dumps(rules_hint, default=str)[:1500]
        )
    user = (
        f'From: {from_addr}\nSubject: {subject}\n\nEmail body:\n'
        f'{_strip_for_prompt(body, 8000)}'
        f'{hint}\n\nRespond with JSON only.'
    )
    text, err = call_ai(user, system=system, timeout=55, max_prompt_chars=12000)
    if err:
        log_ai_usage(
            feature='donation_email_parse',
            provider=None,
            model=None,
            status='error',
            prompt_chars=len(user),
            detail=err,
        )
        return None, err
    data = extract_json_payload(text or '')
    if not isinstance(data, dict):
        log_ai_usage(
            feature='donation_email_parse',
            provider=None,
            model=None,
            status='error',
            prompt_chars=len(user),
            detail='invalid json',
        )
        return None, 'AI returned unusable JSON for donation parse.'
    log_ai_usage(
        feature='donation_email_parse',
        provider=None,
        model=None,
        status='ok',
        prompt_chars=len(user),
        response_chars=len(text or ''),
    )
    return data, None


_SCRIPTURE_INLINE = re.compile(
    r'\b('
    r'(?:[1-3]\s*)?'
    r'(?:Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|'
    r'Samuel|Kings|Chronicles|Ezra|Nehemiah|Esther|Job|Psalm|Psalms|Proverb|Proverbs|'
    r'Ecclesiastes|Song(?:\s+of\s+(?:Songs|Solomon))?|Isaiah|Jeremiah|Lamentations|'
    r'Ezekiel|Daniel|Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|Zephaniah|'
    r'Haggai|Zechariah|Malachi|Matthew|Mark|Luke|John|Acts|Romans|Corinthians|'
    r'Galatians|Ephesians|Philippians|Colossians|Thessalonians|Timothy|Titus|'
    r'Philemon|Hebrews|James|Peter|Jude|Revelation|'
    r'Gen|Exod?|Lev|Num|Deut|Josh|Judg|Sam|Kgs|Chr|Neh|Ps|Prov|Eccl|Isa|Jer|Ezek|Dan|'
    r'Hos|Amos|Mic|Matt|Mk|Lk|Jn|Rom|Cor|Gal|Eph|Phil|Col|Thess|Tim|Heb|Jas|Pet|Rev)'
    r'\.?'
    r'\s+\d+'
    r'(?::\d+(?:\s*[-–—,;]\s*\d+)*)?'
    r')\b',
    re.I,
)


def _split_numbered_lines(plain_text: str) -> list[str]:
    """Normalize to line list used for AI structure mapping."""
    text = (plain_text or '').replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('\xa0', ' ')
    # Keep blank lines as empty strings so indices stay stable
    lines = text.split('\n')
    if len(lines) == 1 and len(lines[0]) > 500:
        # Soft-wrap very long single lines on sentence boundaries for indexing only
        soft = re.split(r'(?<=[.!?])\s+(?=[A-Z"“‘])', lines[0])
        if len(soft) > 3:
            lines = soft
    return lines


def _first_scripture_in(text: str) -> str:
    m = _SCRIPTURE_INLINE.search(text or '')
    if not m:
        return ''
    return re.sub(r'\s+', ' ', m.group(1)).strip()[:120]


def _all_scriptures_in(text: str, limit: int = 8) -> list[str]:
    found = []
    seen = set()
    for m in _SCRIPTURE_INLINE.finditer(text or ''):
        ref = re.sub(r'\s+', ' ', m.group(1)).strip()
        key = ref.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(ref[:120])
        if len(found) >= limit:
            break
    return found


def ai_parse_sermon_structure(
    plain_text: str,
    *,
    filename: str = '',
    rules_hint: dict | None = None,
) -> tuple[Optional[dict], Optional[str]]:
    """
    Ask AI ONLY for section boundaries on numbered original lines.
    Never ask the model to rewrite body text — we slice original lines ourselves.

    Returns dict:
      title, primary_passage, service_date,
      sections: [{title, section_type, start_line, end_line, scripture_reference}]
    """
    if not ai_configured():
        return None, 'AI is not configured (Settings → AI Providers).'

    lines = _split_numbered_lines(plain_text)
    if not any(ln.strip() for ln in lines):
        return None, 'Empty sermon text.'

    # Cap lines sent to model but keep mapping to original via line numbers
    max_lines = 400
    send_lines = lines[:max_lines]
    numbered = '\n'.join(f'{i+1}|{ln}' for i, ln in enumerate(send_lines))
    if len(lines) > max_lines:
        numbered += f'\n# NOTE: source continues after line {max_lines}; map only lines 1-{max_lines}.'

    system = (
        'You are a STRUCTURE indexer for MyVineOS pastoral sermons. '
        'You NEVER rewrite, summarize, paraphrase, or shorten the sermon. '
        'You ONLY assign line-number ranges so software can copy the original text. '
        'Return ONLY JSON with keys: '
        'title (sermon title string), '
        'primary_passage (main Bible reference if present, else empty), '
        'service_date (YYYY-MM-DD or empty), '
        'sections (array). Each section object MUST have: '
        'title, section_type, start_line (int, 1-based inclusive), end_line (int, inclusive), '
        'scripture_reference (Bible ref found in that range, or empty), '
        'heading_text (optional exact heading line from source if present). '
        '\n\n'
        'REQUIRED SECTION ORDER / SHAPE (this is how MyVine podium expects sermons):\n'
        '1) introduction — TOP of the message only (welcome, opener, ice-breaker). '
        'Title must be "Introduction". section_type=introduction.\n'
        '2) point sections — The MAIN SERMON BODY starts at Section 1. '
        'When the document has a "Sermon Content" / "Message" / "Body" heading, '
        'that is where Section 1 begins (do NOT put that whole body in Introduction). '
        'Each additional major point, story, or argument is the next numbered section: '
        'Section 1, Section 2, Section 3, … '
        'section_type=point for all of these. '
        'title MUST be exactly "Section 1", "Section 2", etc. '
        'If the source has a subheading (Point 1: Love, Story: …), put that phrase in heading_text.\n'
        '3) application — practical "so what / live it out" near the end. '
        'Title "Application". section_type=application. Optional if absent.\n'
        '4) conclusion — closing, invitation, altar call, final prayer. '
        'Title "Conclusion". section_type=conclusion. Optional if absent.\n'
        '5) notes — "Verses and Notes", "Notes & References", full scripture dumps, research, '
        'delivery tips, personal prep. Title "Notes & References". section_type=notes. '
        'These are PREP material (not podium outline). Put them LAST. '
        'NEVER label notes/verses/references as introduction.\n'
        '\n'
        'Hard rules:\n'
        '(A) Cover the WHOLE document with non-overlapping ranges; last end_line near final line.\n'
        '(B) Do NOT invent text. Do NOT put body content in JSON — ranges only.\n'
        '(C) Prefer 1 intro + 2–10 body sections + optional application/conclusion + notes last.\n'
        '(D) Never leave the entire sermon as one blob under Introduction.\n'
        '(E) Never put Verses and Notes / full scripture research under Introduction — use notes.\n'
        '(F) scripture_reference = a verse actually present in that line range when possible.\n'
        '(G) Title line of the document is NOT a body section — put it in the top-level title field.'
    )
    hint = ''
    if rules_hint:
        compact = {
            'rules_title': rules_hint.get('title'),
            'rules_primary_passage': rules_hint.get('primary_passage'),
            'rules_section_count': len(rules_hint.get('sections') or []),
            'rules_section_titles': [
                (s.get('title') or '') for s in (rules_hint.get('sections') or [])[:16]
            ],
        }
        hint = '\nRule parser hints (optional):\n' + json.dumps(compact, default=str)

    user = (
        f'Filename: {filename or "unknown"}\n'
        f'Total lines: {len(send_lines)}\n'
        f'Numbered sermon (format: LINE|text):\n{numbered}'
        f'{hint}\n\n'
        'Return JSON only with line ranges. Do not rewrite any sermon wording.'
    )
    text, err = call_ai(user, system=system, timeout=75, max_prompt_chars=16000)
    if err:
        log_ai_usage(
            feature='sermon_import_parse',
            provider=None,
            model=None,
            status='error',
            prompt_chars=len(user),
            detail=err,
        )
        return None, err
    data = extract_json_payload(text or '')
    if not isinstance(data, dict) or not isinstance(data.get('sections'), list):
        log_ai_usage(
            feature='sermon_import_parse',
            provider=None,
            model=None,
            status='error',
            prompt_chars=len(user),
            detail='invalid json structure',
        )
        return None, 'AI returned unusable sermon structure.'

    # Attach original lines so caller can materialize content safely
    data['_source_lines'] = lines
    data['_lines_sent'] = len(send_lines)
    log_ai_usage(
        feature='sermon_import_parse',
        provider=None,
        model=None,
        status='ok',
        prompt_chars=len(user),
        response_chars=len(text or ''),
    )
    return data, None


def materialize_ai_sermon_sections(
    ai_data: dict,
    *,
    as_html: bool = True,
    html_from_text=None,
) -> tuple[list[dict], dict]:
    """
    Build sections from AI line ranges + original source lines.
    Returns (sections, meta) where meta has coverage stats / errors.
    Rejects / pads if AI dropped large portions of the original.
    """
    lines = list(ai_data.get('_source_lines') or [])
    n = len(lines)
    meta = {
        'coverage': 0.0,
        'chars_original': sum(len(x) for x in lines),
        'chars_used': 0,
        'rejected': False,
        'reason': '',
        'prep_notes': '',  # → sermon Notes & References field (not podium)
    }
    if n == 0:
        meta['rejected'] = True
        meta['reason'] = 'no source lines'
        return [], meta

    raw_secs = ai_data.get('sections') or []
    ranges: list[dict] = []
    for sec in raw_secs:
        if not isinstance(sec, dict):
            continue
        try:
            start = int(sec.get('start_line') or 0)
            end = int(sec.get('end_line') or 0)
        except (TypeError, ValueError):
            continue
        if start < 1:
            start = 1
        if end < start:
            end = start
        # Clamp to lines we have (AI only saw first max_lines sometimes)
        start = min(start, n)
        end = min(end, n)
        heading_text = (sec.get('heading_text') or sec.get('subtitle') or '').strip()[:200]
        ranges.append({
            'title': (sec.get('title') or 'Section').strip()[:200] or 'Section',
            'section_type': (sec.get('section_type') or 'point').strip().lower(),
            'start': start,
            'end': end,
            'scripture_reference': (sec.get('scripture_reference') or '').strip()[:120],
            'heading_text': heading_text,
        })

    if not ranges:
        meta['rejected'] = True
        meta['reason'] = 'no valid line ranges'
        return [], meta

    # Sort and de-overlap (keep earlier assignment)
    ranges.sort(key=lambda r: (r['start'], r['end']))
    cleaned = []
    covered_until = 0
    for r in ranges:
        s = max(r['start'], covered_until + 1)
        e = r['end']
        if s > e:
            continue
        if s > n:
            continue
        e = min(e, n)
        cleaned.append({**r, 'start': s, 'end': e})
        covered_until = e

    # Extend last section to document end if AI stopped early (keep original text)
    if cleaned and cleaned[-1]['end'] < n:
        cleaned[-1]['end'] = n

    # Fill leading gap before first section
    if cleaned and cleaned[0]['start'] > 1:
        # Prefer attach to first section rather than drop
        cleaned[0]['start'] = 1

    # Fill internal gaps by extending previous end
    for i in range(1, len(cleaned)):
        prev = cleaned[i - 1]
        cur = cleaned[i]
        if cur['start'] > prev['end'] + 1:
            # Unassigned middle lines — attach to previous section (preserve text)
            prev['end'] = cur['start'] - 1

    # Normalize MyVine shape: Introduction → Section 1..N → Application → Conclusion → Notes
    cleaned = _normalize_myvine_section_plan(cleaned, lines)

    sections: list[dict] = []
    prep_note_chunks: list[str] = []
    used_chars = 0
    valid_types = {
        'introduction', 'point', 'scripture', 'application',
        'conclusion', 'notes', 'body',
    }
    for r in cleaned:
        chunk_lines = lines[r['start'] - 1 : r['end']]
        content = '\n'.join(chunk_lines).strip()
        if not content:
            continue
        used_chars += len(content)
        stype = r['section_type'] if r['section_type'] in valid_types else 'point'
        title = (r.get('title') or '').strip()

        # Prep / research / full verse dumps → Notes & References (not podium outline)
        is_prep = stype == 'notes' or bool(re.match(
            r'^(verses?\s*(and|&)?\s*notes|notes\s*(and|&)?\s*references?|'
            r'notes\s*(and|&)?\s*refs|references?|research|personal prep|prep notes|'
            r'delivery tips|full scripture|scripture notes)\b',
            title,
            re.I,
        ))
        if is_prep:
            label = title if title else 'Notes & References'
            if content.lower().startswith(label.lower()):
                prep_note_chunks.append(content)
            else:
                prep_note_chunks.append(f'{label}\n{content}')
            continue

        # Scripture: AI value if present, else first/all refs found in original chunk
        refs_found = _all_scriptures_in(content)
        scripture = r['scripture_reference'] or (refs_found[0] if refs_found else '')
        # If AI missed but body has refs, put multi-ref note in notes field
        notes_parts = []
        heading = (r.get('heading_text') or '').strip()
        if heading and heading.lower() not in title.lower():
            notes_parts.append(heading)
        if len(refs_found) > 1:
            notes_parts.append('Scriptures: ' + '; '.join(refs_found[:6]))
        notes = ' · '.join(notes_parts)
        body = content
        if as_html and html_from_text and '<' not in body:
            body = html_from_text(body)
        elif as_html and '<' not in body:
            # minimal paragraphs
            paras = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
            if not paras:
                paras = [body]
            body = ''.join(f'<p>{_escape_html(p)}</p>' for p in paras)
        sections.append({
            'section_type': stype,
            'title': title[:200] or 'Section',
            'content': body,
            'notes': notes,
            'scripture_reference': scripture[:120],
            'source': '',
        })

    meta['prep_notes'] = '\n\n'.join(prep_note_chunks).strip()
    meta['chars_used'] = used_chars
    orig = max(meta['chars_original'], 1)
    meta['coverage'] = used_chars / orig

    # Reject if AI would throw away most of the sermon
    if meta['coverage'] < 0.75 or not sections:
        meta['rejected'] = True
        meta['reason'] = (
            f'AI structure covered only {int(meta["coverage"] * 100)}% of original text; kept rules parse'
        )
        return [], meta

    return sections, meta


def _escape_html(s: str) -> str:
    return (
        (s or '')
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('\n', '<br>\n')
    )


_INTRO_TITLE_RE = re.compile(
    r'^(introduction|intro|opening|welcome)\b', re.I
)
_APP_TITLE_RE = re.compile(
    r'^(application|apply|so what|living it|live it|response)\b', re.I
)
_CONC_TITLE_RE = re.compile(
    r'^(conclusion|closing|close|invitation|altar call|final|prayer|amen)\b', re.I
)
_NOTES_TITLE_RE = re.compile(
    r'^(verses?\s*(and|&)?\s*notes|notes\s*(and|&)?\s*references?|notes\s*(and|&)?\s*refs|'
    r'notes|scripture notes|study notes|references?|research|personal prep|prep notes|'
    r'delivery tips|full scripture)\b',
    re.I,
)
_SERMON_BODY_HEAD_RE = re.compile(
    r'^(sermon\s+content|sermon\s+body|message|body|main\s+points?)\b', re.I
)
_POINT_HEAD_RE = re.compile(
    r'^(?:point|section|part)\s*(\d+)\b|^(\d{1,2})[.)]\s+\S',
    re.I,
)


def _infer_special_type(title: str, heading_text: str, section_type: str) -> str:
    blob = f'{title} {heading_text}'.strip()
    st = (section_type or 'point').lower()
    if st in ('introduction', 'application', 'conclusion', 'notes', 'scripture'):
        # Trust explicit types unless title clearly contradicts
        if st == 'introduction' and _APP_TITLE_RE.match(blob):
            return 'application'
        return st
    if _INTRO_TITLE_RE.match(blob):
        return 'introduction'
    if _APP_TITLE_RE.match(blob):
        return 'application'
    if _CONC_TITLE_RE.match(blob):
        return 'conclusion'
    if _NOTES_TITLE_RE.match(blob):
        return 'notes'
    if st == 'body':
        return 'point'
    return 'point'


def _normalize_myvine_section_plan(ranges: list[dict], lines: list[str]) -> list[dict]:
    """
    Force MyVine podium shape:
      Introduction → Section 1..N → Application → Conclusion → Notes
    Body/point chunks become Section 1, Section 2, ... in order.
    """
    if not ranges:
        return ranges

    # Classify each range
    classified = []
    for r in ranges:
        title = (r.get('title') or '').strip()
        heading = (r.get('heading_text') or '').strip()
        # Peek first non-empty line of chunk for better classification
        first_line = ''
        for ln in lines[r['start'] - 1 : r['end']]:
            if (ln or '').strip():
                first_line = ln.strip()
                break
        stype = _infer_special_type(title, heading or first_line, r.get('section_type') or 'point')
        # "Sermon Content" heading alone should start Section 1, not stay as intro/body blob title
        if _SERMON_BODY_HEAD_RE.match(title) or _SERMON_BODY_HEAD_RE.match(first_line):
            stype = 'point'
            if not heading:
                heading = title if _SERMON_BODY_HEAD_RE.match(title) else first_line
        classified.append({**r, 'section_type': stype, 'heading_text': heading})

    intro = [c for c in classified if c['section_type'] == 'introduction']
    apps = [c for c in classified if c['section_type'] == 'application']
    concs = [c for c in classified if c['section_type'] == 'conclusion']
    notes = [c for c in classified if c['section_type'] == 'notes']
    # Everything else is main sermon body → Section N
    body = [
        c for c in classified
        if c['section_type'] not in ('introduction', 'application', 'conclusion', 'notes')
    ]

    # If no intro but first body chunk looks short/opening, leave as body (Section 1)
    # If multiple intros, keep first as intro and fold rest into body front
    ordered: list[dict] = []
    if intro:
        first_intro = dict(intro[0])
        first_intro['title'] = 'Introduction'
        first_intro['section_type'] = 'introduction'
        ordered.append(first_intro)
        for extra in intro[1:]:
            body.insert(0, {**extra, 'section_type': 'point'})

    # Drop/merge bare "Sermon Content" heading chunks into the next real point
    # so Section 1 is the first actual teaching unit, not an empty shell.
    merged_body: list[dict] = []
    i = 0
    while i < len(body):
        b = dict(body[i])
        chunk = '\n'.join(lines[b['start'] - 1 : b['end']]).strip()
        first = next((ln.strip() for ln in lines[b['start'] - 1 : b['end']] if ln.strip()), '')
        is_shell = (
            _SERMON_BODY_HEAD_RE.match((b.get('title') or ''))
            or _SERMON_BODY_HEAD_RE.match(first)
        ) and len(chunk) < 80
        if is_shell and i + 1 < len(body):
            nxt = dict(body[i + 1])
            nxt['start'] = min(b['start'], nxt['start'])
            # keep later end
            if not nxt.get('heading_text'):
                nxt['heading_text'] = (b.get('heading_text') or b.get('title') or first)[:200]
            merged_body.append(nxt)
            i += 2
            continue
        merged_body.append(b)
        i += 1

    # Number body as Section 1..N
    for idx, b in enumerate(merged_body, start=1):
        item = dict(b)
        item['section_type'] = 'point'
        # Keep original point title in heading_text if useful
        orig_title = (item.get('title') or '').strip()
        if orig_title and not _SERMON_BODY_HEAD_RE.match(orig_title) and not re.match(
            r'^section\s+\d+$', orig_title, re.I
        ):
            if not item.get('heading_text'):
                item['heading_text'] = orig_title
        item['title'] = f'Section {idx}'
        ordered.append(item)

    for a in apps:
        item = dict(a)
        item['title'] = 'Application'
        item['section_type'] = 'application'
        ordered.append(item)

    for c in concs:
        item = dict(c)
        item['title'] = 'Conclusion'
        item['section_type'] = 'conclusion'
        ordered.append(item)

    for nt in notes:
        item = dict(nt)
        # Standardize label so materialize routes to sermon Notes & References
        item['title'] = 'Notes & References'
        item['section_type'] = 'notes'
        ordered.append(item)

    # If AI produced only body with no Section numbering path, ensure at least Section 1
    if not ordered:
        return ranges
    # If we somehow have no point sections but have intro+app, that's ok
    return ordered


def merge_donation_parse(rules: dict, ai: dict) -> dict:
    """Prefer non-empty AI fields when rules are weak; never replace a good amount with 0."""
    out = dict(rules or {})
    ai = ai or {}

    def pick(key, *, prefer_ai_if_rules_empty=True, numeric=False):
        rv = out.get(key)
        av = ai.get(key)
        if numeric:
            try:
                rv_n = float(rv or 0)
            except (TypeError, ValueError):
                rv_n = 0.0
            try:
                av_n = float(av or 0)
            except (TypeError, ValueError):
                av_n = 0.0
            if rv_n <= 0 and av_n > 0:
                out[key] = av_n
            elif av_n > 0 and rv_n > 0 and abs(av_n - rv_n) / max(rv_n, 0.01) < 0.02:
                out[key] = rv_n  # same
            elif rv_n <= 0:
                out[key] = av_n
            return
        rs = (str(rv).strip() if rv is not None else '')
        as_ = (str(av).strip() if av is not None else '')
        empty_rules = (not rs) or rs.lower() in ('online donor', 'unknown', 'online')
        if prefer_ai_if_rules_empty and empty_rules and as_:
            out[key] = as_
        elif as_ and not empty_rules and key in ('donor_email', 'fund_label', 'confirmation_number', 'method'):
            # fill missing specific fields from AI
            if empty_rules:
                out[key] = as_

    pick('amount', numeric=True)
    for k in (
        'processor', 'currency', 'donor_name', 'donor_email', 'confirmation_number',
        'method', 'date', 'fund_label', 'notes',
    ):
        pick(k)
    if 'is_recurring' in ai:
        out['is_recurring'] = bool(ai.get('is_recurring'))
    # confidence: max of both, with AI floor when it found amount
    try:
        rc = float(out.get('confidence') or 0)
    except (TypeError, ValueError):
        rc = 0.0
    try:
        ac = float(ai.get('confidence') or 0)
    except (TypeError, ValueError):
        ac = 0.0
    if float(out.get('amount') or 0) > 0 and ac:
        out['confidence'] = min(100.0, max(rc, ac, 75.0))
    else:
        out['confidence'] = min(100.0, max(rc, ac))
    extras = dict(out.get('extras') or {})
    extras['parse_mode'] = 'rules+ai'
    extras['ai_used'] = True
    out['extras'] = extras
    return out


def sermon_rules_quality(parsed: dict) -> float:
    """0–100 heuristic for whether rule-based sermon parse is strong enough."""
    sections = parsed.get('sections') or []
    if not sections:
        return 5.0
    score = 25.0
    if parsed.get('title'):
        score += 10
    if parsed.get('primary_passage'):
        score += 10
    if parsed.get('service_date'):
        score += 5
    n = len(sections)
    if n >= 3:
        score += 25
    elif n == 2:
        score += 12
    # Multiple real section types is good
    types = { (s.get('section_type') or '') for s in sections }
    if len(types) >= 2:
        score += 15
    # One giant blob is weak
    if n == 1:
        content = (sections[0].get('content') or '')
        plain = re.sub(r'<[^>]+>', ' ', content)
        if len(plain) > 800:
            score -= 10
    return max(0.0, min(100.0, score))
