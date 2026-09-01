import json
import re

SECTION_MARKER = re.compile(
    r'^\s*[\[\(]?\s*(verse\s*\d*|chorus|bridge|pre-?chorus|tag|intro|outro|ending|interlude)\s*[\]\)]?\s*$',
    re.IGNORECASE,
)


def parse_lyrics_to_sections(lyrics_raw: str) -> list:
    """
    Split pasted lyrics on lines like [Verse 1], (Chorus), Bridge, etc.
    Returns structured sections for screen mode and JSON storage.
    """
    if not lyrics_raw or not lyrics_raw.strip():
        return []

    lines = lyrics_raw.replace('\r\n', '\n').split('\n')
    sections = []
    current_label = 'Lyrics'
    current_type = 'verse'
    current_lines = []
    sort = 0

    def flush():
        nonlocal sort
        content = '\n'.join(current_lines).strip()
        if content:
            sort += 1
            sections.append({
                'id': f"s{sort}",
                'type': current_type,
                'label': current_label,
                'content': content,
                'sort': sort,
                'repeat': 1,
            })

    for line in lines:
        stripped = line.strip()
        if SECTION_MARKER.match(stripped):
            flush()
            current_lines = []
            label = stripped.strip('[]() ')
            low = label.lower()
            if 'chorus' in low:
                current_type = 'chorus'
            elif 'bridge' in low:
                current_type = 'bridge'
            elif 'tag' in low:
                current_type = 'tag'
            elif 'intro' in low:
                current_type = 'intro'
            elif 'outro' in low or 'ending' in low:
                current_type = 'outro'
            else:
                current_type = 'verse'
            current_label = label.title() if label else 'Section'
            continue
        current_lines.append(line)

    flush()
    return sections


def normalize_sections(raw_sections, lyrics_raw=None) -> list:
    if isinstance(raw_sections, list) and raw_sections:
        out = []
        for i, sec in enumerate(raw_sections):
            if not isinstance(sec, dict):
                continue
            content = (sec.get('content') or '').strip()
            if not content:
                continue
            out.append({
                'id': sec.get('id') or f"s{i + 1}",
                'type': sec.get('type') or 'verse',
                'label': sec.get('label') or f"Section {i + 1}",
                'content': content,
                'sort': sec.get('sort', i + 1),
                'repeat': sec.get('repeat', 1),
            })
        if out:
            return sorted(out, key=lambda x: x.get('sort', 0))

    if lyrics_raw:
        parsed = parse_lyrics_to_sections(lyrics_raw)
        if parsed:
            return parsed

    if lyrics_raw and lyrics_raw.strip():
        return [{
            'id': 'v1', 'type': 'verse', 'label': 'Lyrics',
            'content': lyrics_raw.strip(), 'sort': 1, 'repeat': 1,
        }]
    return []


def parse_play_order(raw) -> list:
    """Normalize a play-order list of section ids."""
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x) for x in data if x]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def default_play_order_from_sections(sections: list) -> list:
    """One pass through library sections in sort order."""
    ordered = sorted(sections or [], key=lambda x: x.get('sort', 0))
    return [s.get('id') for s in ordered if s.get('id')]


def resolve_display_sections(song: dict, arrangement=None) -> list:
    """Order/filter sections for prompter using arrangement, song play order, or sort."""
    try:
        sections = song.get('sections')
        if not isinstance(sections, list):
            sections = json.loads(song.get('sections_json') or '[]')
    except (json.JSONDecodeError, TypeError):
        sections = []
    sections = normalize_sections(sections, song.get('lyrics_raw'))
    by_id = {s.get('id'): s for s in sections if s.get('id')}

    order = parse_play_order(arrangement)
    if not order:
        order = parse_play_order(song.get('play_order') or song.get('play_order_json'))
    if not order:
        order = default_play_order_from_sections(sections)

    ordered = []
    for sid in order:
        if sid in by_id:
            # Copy so repeated chorus gets independent display slots
            ordered.append(dict(by_id[sid]))
    return ordered or sections