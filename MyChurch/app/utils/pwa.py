# ================================================================
# Installable church app (PWA) for MyVineOS self-host (one church).
# ================================================================
from __future__ import annotations

import json
import re

from html import escape

from flask import g, jsonify, make_response, request, session, url_for


_SCRIPT_VER = "church2"
_CHOICES = frozenset({"dismissed", "installed", "no", "yes", "never"})
_SURFACES = frozenset({"phone", "desktop"})


def _choice_allowed(choice: str) -> bool:
    if choice in _CHOICES:
        return True
    if choice.startswith("snooze:"):
        tail = choice.split(":", 1)[-1]
        return tail.isdigit() and len(tail) >= 10
    return False


def _church_name() -> str:
    s = getattr(g, "settings", None) or {}
    name = (s.get("church_name") or "").strip()
    return name[:40] or "MyVineOS"


def _icon_src() -> str:
    s = getattr(g, "settings", None) or {}
    fav = (s.get("favicon_path") or s.get("logo_path") or "").strip()
    if fav.startswith("http://") or fav.startswith("https://") or fav.startswith("/"):
        return fav
    if fav:
        return "/static/images/" + fav.lstrip("/")
    return "/static/images/dashboard_bg1.png"


def _start_url() -> str:
    try:
        return url_for("church.church_home")
    except Exception:
        return "/public/"


def _device_fp() -> str | None:
    try:
        from poweredbytop.security.device_print import request_audit_context

        ctx = request_audit_context() or {}
        fp = (ctx.get("device_fp") or "").strip()
        if fp:
            return fp[:64]
    except Exception:
        pass
    return None


def _ensure_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pwa_prompt_choices (
            id INT NOT NULL AUTO_INCREMENT,
            church_id INT NULL,
            device_fp VARCHAR(64) NULL,
            surface VARCHAR(16) NOT NULL,
            choice VARCHAR(64) NOT NULL,
            user_id INT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_pwa_fp_surface (device_fp, surface),
            KEY idx_pwa_user_surface (user_id, surface)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    conn.commit()


def _lookup_choice(surface: str) -> str | None:
    fp = _device_fp()
    uid = None
    try:
        uid = int(session.get("user_id") or 0) or None
    except (TypeError, ValueError):
        uid = None
    try:
        from app.models.db import get_db

        db = get_db()
        _ensure_table(db)
        cur = db.cursor()
        if fp:
            cur.execute(
                "SELECT choice FROM pwa_prompt_choices "
                "WHERE device_fp = %s AND surface = %s "
                "ORDER BY updated_at DESC LIMIT 1",
                (fp, surface),
            )
            row = cur.fetchone()
            if row:
                val = row.get("choice") if isinstance(row, dict) else row[0]
                if val and _choice_allowed(str(val)):
                    return str(val)
        if uid:
            cur.execute(
                "SELECT choice FROM pwa_prompt_choices "
                "WHERE user_id = %s AND surface = %s "
                "ORDER BY updated_at DESC LIMIT 1",
                (uid, surface),
            )
            row = cur.fetchone()
            if row:
                val = row.get("choice") if isinstance(row, dict) else row[0]
                if val and _choice_allowed(str(val)):
                    return str(val)
    except Exception:
        return None
    return None


def _save_choice(surface: str, choice: str) -> None:
    fp = _device_fp()
    uid = None
    try:
        uid = int(session.get("user_id") or 0) or None
    except (TypeError, ValueError):
        uid = None
    try:
        from app.models.db import get_db

        db = get_db()
        _ensure_table(db)
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO pwa_prompt_choices (church_id, device_fp, surface, choice, user_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (None, fp, surface, choice, uid),
        )
        db.commit()
    except Exception:
        pass


def register_pwa(app) -> None:
    @app.route("/manifest.webmanifest")
    def pwa_manifest():
        name = _church_name()
        start = _start_url()
        icon = _icon_src()
        origin = (request.url_root or "/").rstrip("/") + "/"
        body = {
            "name": name,
            "short_name": name[:12],
            "description": name + " — church app",
            "start_url": start,
            "scope": "/",
            "id": origin,
            "display": "standalone",
            "display_override": ["standalone", "minimal-ui", "window-controls-overlay"],
            "orientation": "any",
            "background_color": "#0a0a0a",
            "theme_color": "#00b8c4",
            "icons": [
                {"src": icon, "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {
                    "src": icon,
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
            ],
            "related_applications": [
                {"platform": "webapp", "url": origin + "manifest.webmanifest"}
            ],
        }
        resp = make_response(json.dumps(body))
        resp.headers["Content-Type"] = "application/manifest+json; charset=utf-8"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.route("/pwa/choice", methods=["GET", "POST"])
    def pwa_choice():
        if request.method == "GET":
            surface = (request.args.get("surface") or "desktop").strip().lower()
            if surface not in _SURFACES:
                surface = "desktop"
            return jsonify({"ok": True, "choice": _lookup_choice(surface), "surface": surface})
        data = request.get_json(silent=True) or {}
        surface = str(data.get("surface") or request.form.get("surface") or "desktop").strip().lower()
        choice = str(data.get("choice") or request.form.get("choice") or "").strip().lower()
        if surface not in _SURFACES:
            surface = "desktop"
        if not _choice_allowed(choice):
            return jsonify({"ok": False, "error": "choice"}), 400
        _save_choice(surface, choice)
        return jsonify({"ok": True, "choice": choice, "surface": surface})

    @app.after_request
    def _inject_pwa(response):
        try:
            if response.status_code != 200:
                return response
            ctype = (response.headers.get("Content-Type") or "").lower()
            if "text/html" not in ctype:
                return response
            data = response.get_data(as_text=True)
            if not data or "<head" not in data.lower():
                return response
            if "pwa-install.js" in data:
                return response
            name = escape(_church_name(), quote=True)
            script = f"/static/js/pwa-install.js?v={_SCRIPT_VER}"
            bits = (
                f'  <meta name="apple-mobile-web-app-title" content="{name}">\n'
                f'  <link rel="manifest" href="/manifest.webmanifest">\n'
                f'  <script src="{script}" defer></script>\n'
            )
            if 'rel="manifest"' in data or "rel='manifest'" in data:
                data = re.sub(
                    r"""<link[^>]+rel=["']manifest["'][^>]*>""",
                    '<link rel="manifest" href="/manifest.webmanifest">',
                    data,
                    count=1,
                    flags=re.I,
                )
                if "pwa-install.js" not in data:
                    data, n = re.subn(
                        r"(<head[^>]*>)",
                        r"\1\n  " + f'<script src="{script}" defer></script>',
                        data,
                        count=1,
                        flags=re.I,
                    )
                    if not n:
                        return response
            else:
                data, n = re.subn(
                    r"(<head[^>]*>)",
                    r"\1\n" + bits,
                    data,
                    count=1,
                    flags=re.I,
                )
                if not n:
                    return response
            if "data-pwa-name" not in data:
                data = re.sub(
                    r"<html\b",
                    f'<html data-pwa-name="{name}" data-pwa-scope="/" data-pwa-sw="/sw.js" data-pwa-choice="/pwa/choice"',
                    data,
                    count=1,
                    flags=re.I,
                )
            response.set_data(data)
            response.headers["Content-Length"] = str(len(data.encode("utf-8")))
        except Exception:
            return response
        return response
