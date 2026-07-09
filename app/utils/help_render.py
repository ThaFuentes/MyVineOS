# app/utils/help_render.py
# Lightweight markdown -> safe HTML for help articles.

import re

from markupsafe import Markup, escape


def render_help_markdown(text: str) -> Markup:
    if not text:
        return Markup('')

    lines = text.strip().splitlines()
    html_parts = []
    in_list = False
    list_type = None

    def close_list():
        nonlocal in_list, list_type
        if in_list:
            html_parts.append(f'</{list_type}>')
            in_list = False
            list_type = None

    def inline_format(s: str) -> str:
        s = escape(s)
        s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
        s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
        return s

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            close_list()
            continue

        if stripped.startswith('### '):
            close_list()
            html_parts.append(f'<h4>{inline_format(stripped[4:])}</h4>')
            continue
        if stripped.startswith('## '):
            close_list()
            html_parts.append(f'<h3>{inline_format(stripped[3:])}</h3>')
            continue

        ol_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if ol_match:
            if not in_list or list_type != 'ol':
                close_list()
                html_parts.append('<ol>')
                in_list = True
                list_type = 'ol'
            html_parts.append(f'<li>{inline_format(ol_match.group(2))}</li>')
            continue

        if stripped.startswith('- '):
            if not in_list or list_type != 'ul':
                close_list()
                html_parts.append('<ul>')
                in_list = True
                list_type = 'ul'
            html_parts.append(f'<li>{inline_format(stripped[2:])}</li>')
            continue

        close_list()
        html_parts.append(f'<p>{inline_format(stripped)}</p>')

    close_list()
    return Markup(''.join(html_parts))