# app/utils/help_render.py
# Lightweight markdown -> safe HTML for help articles (enterprise guides).

import re

from markupsafe import Markup, escape


def render_help_markdown(text: str) -> Markup:
    if not text:
        return Markup("")

    lines = text.strip().splitlines()
    html_parts = []
    in_list = False
    list_type = None
    in_code = False
    code_buf = []

    def close_list():
        nonlocal in_list, list_type
        if in_list:
            html_parts.append(f"</{list_type}>")
            in_list = False
            list_type = None

    def flush_code():
        nonlocal in_code, code_buf
        if in_code:
            code = escape("\n".join(code_buf))
            html_parts.append(f'<pre class="help-code"><code>{code}</code></pre>')
            code_buf = []
            in_code = False

    def inline_format(s: str) -> str:
        s = escape(s)
        # links [text](url) — only relative or http(s)
        def _link(m):
            label, url = m.group(1), m.group(2)
            if url.startswith(("http://", "https://", "/", "#")):
                return f'<a href="{escape(url)}">{label}</a>'
            return label

        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        return s

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                flush_code()
            else:
                close_list()
                in_code = True
                code_buf = []
            continue

        if in_code:
            code_buf.append(line)
            continue

        if not stripped:
            close_list()
            continue

        if stripped in ("---", "***", "___"):
            close_list()
            html_parts.append('<hr class="help-hr">')
            continue

        if stripped.startswith("> "):
            close_list()
            html_parts.append(f'<blockquote class="help-callout">{inline_format(stripped[2:])}</blockquote>')
            continue

        if stripped.startswith("#### "):
            close_list()
            html_parts.append(f"<h5>{inline_format(stripped[5:])}</h5>")
            continue
        if stripped.startswith("### "):
            close_list()
            html_parts.append(f"<h4>{inline_format(stripped[4:])}</h4>")
            continue
        if stripped.startswith("## "):
            close_list()
            html_parts.append(f"<h3>{inline_format(stripped[3:])}</h3>")
            continue
        if stripped.startswith("# "):
            close_list()
            html_parts.append(f"<h2>{inline_format(stripped[2:])}</h2>")
            continue

        ol_match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if ol_match:
            if not in_list or list_type != "ol":
                close_list()
                html_parts.append("<ol>")
                in_list = True
                list_type = "ol"
            html_parts.append(f"<li>{inline_format(ol_match.group(2))}</li>")
            continue

        if stripped.startswith(("- ", "* ")):
            if not in_list or list_type != "ul":
                close_list()
                html_parts.append("<ul>")
                in_list = True
                list_type = "ul"
            html_parts.append(f"<li>{inline_format(stripped[2:])}</li>")
            continue

        close_list()
        html_parts.append(f"<p>{inline_format(stripped)}</p>")

    flush_code()
    close_list()
    return Markup("".join(html_parts))
