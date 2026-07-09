#!/usr/bin/env python3
"""
Exhaustive HTTP crawl of MyVine OS as guest, member, pastor, and admin.
Follows internal links, hits seeded routes, submits POST forms with safe test data.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs

import pymysql
import requests

BASE = os.environ.get("CRAWL_BASE", "http://127.0.0.1:5001")
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REPORT_PATH = os.environ.get(
    "CRAWL_REPORT",
    os.path.join(os.path.dirname(__file__), "crawl_report.json"),
)

ACCOUNTS = {
    "admin": ("admin", "TestAdmin2026!"),
    "pastor": ("sim_pastor", "SimTest2026!"),
    "member": ("sim_member", "SimTest2026!"),
    "visitor": ("sim_visitor", "SimTest2026!"),
}

SKIP_PATH_PREFIXES = (
    "/static/",
    "javascript:",
    "mailto:",
    "tel:",
    "#",
)

DESTRUCTIVE_KEYWORDS = re.compile(
    r"\b(delete|remove|destroy|wipe|purge|logout)\b", re.I
)

ERROR_PATTERNS = [
    (r"Traceback \(most recent call last\)", "traceback"),
    (r"Internal Server Error", "500_page"),
    (r"UndefinedError:", "undefined"),
    (r"TypeError:", "type_error"),
    (r"AttributeError:", "attr_error"),
    (r"KeyError:", "key_error"),
    (r"pymysql\.err\.", "db_error"),
]


class LinkFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.forms: list[dict] = []
        self._form: Optional[dict] = None
        self._select: Optional[dict] = None

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag == "a" and ad.get("href"):
            self.links.append(ad["href"])
        elif tag == "form":
            self._form = {
                "action": ad.get("action") or "",
                "method": (ad.get("method") or "GET").upper(),
                "fields": [],
            }
        elif self._form is not None and tag == "input":
            self._form["fields"].append(
                {
                    "name": ad.get("name"),
                    "type": (ad.get("type") or "text").lower(),
                    "value": ad.get("value", ""),
                }
            )
        elif self._form is not None and tag == "textarea":
            self._form["fields"].append(
                {"name": ad.get("name"), "type": "textarea", "value": ""}
            )
        elif self._form is not None and tag == "select":
            self._select = {"name": ad.get("name"), "options": []}
        elif self._select is not None and tag == "option":
            self._select["options"].append(
                {"value": ad.get("value", ""), "selected": "selected" in ad}
            )

    def handle_endtag(self, tag):
        if tag == "form" and self._form is not None:
            if self._select:
                self._form["fields"].append(self._select)
                self._select = None
            self.forms.append(self._form)
            self._form = None
        elif tag == "select" and self._select is not None and self._form is not None:
            self._form["fields"].append(self._select)
            self._select = None


@dataclass
class CrawlHit:
    role: str
    method: str
    path: str
    status: int
    final_url: str
    ok: bool
    error_type: str = ""
    error_snippet: str = ""
    note: str = ""


@dataclass
class CrawlStats:
    role: str
    pages_visited: int = 0
    forms_submitted: int = 0
    failures: list[CrawlHit] = field(default_factory=list)
    hits: list[CrawlHit] = field(default_factory=list)


def strip_comments(html: str) -> str:
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def detect_error(html: str) -> tuple[str, str]:
    text = strip_comments(html)
    for pat, etype in ERROR_PATTERNS:
        if re.search(pat, text, re.I):
            m = re.search(pat + r".{0,250}", text, re.I | re.S)
            return etype, (m.group(0) if m else pat)[:280]
    return "", ""


def normalize_path(url: str) -> str:
    p = urlparse(url)
    if p.netloc and p.netloc not in ("127.0.0.1:5001", "127.0.0.1", "localhost:5001"):
        return ""
    path = p.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    return path


def extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not m:
        m = re.search(r'value="([^"]+)"\s+name="csrf_token"', html)
    return m.group(1) if m else ""


def db_ids() -> dict:
    cfg = dict(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", 3308)),
        user=os.environ.get("MYSQL_USER", "churchuser"),
        password=os.environ.get("MYSQL_PASSWORD", "ChurchPass2026!"),
        database=os.environ.get("MYSQL_DATABASE", "church_management"),
        cursorclass=pymysql.cursors.DictCursor,
    )
    out: dict[str, list] = {}
    tables = [
        "events",
        "prayers",
        "announcements",
        "dreams",
        "prophecies",
        "sermons",
        "users",
        "groups",
        "donations",
        "items",
        "pastoral_sermons",
        "illustration_library",
        "pastoral_care_requests",
        "recurring_bills",
        "support_tickets",
        "tickets",
        "service_plans",
        "service_plan_templates",
    ]
    try:
        db = pymysql.connect(**cfg)
        cur = db.cursor()
        for t in tables:
            try:
                cur.execute(f"SELECT id FROM {t} ORDER BY id DESC LIMIT 8")
                out[t] = [r["id"] for r in cur.fetchall()]
            except Exception:
                out[t] = []
        db.close()
    except Exception as exc:
        print(f"DB id fetch warning: {exc}")
    return out


def seed_paths(ids: dict) -> list[str]:
    """Static + dynamic URL seeds."""
    seeds = [
        "/",
        "/public/",
        "/public/community",
        "/public/donate",
        "/public/events/",
        "/public/prayers/",
        "/public/sermons/",
        "/public/dreams/",
        "/public/prophecies/",
        "/public/announcements/",
        "/login",
        "/login?tab=register",
        "/request-reset-password",
        "/forgot-username",
        "/dashboard",
        "/prayers/",
        "/prayers/add",
        "/events/",
        "/events/add",
        "/dreams/",
        "/dreams/submit",
        "/prophecies/",
        "/prophecies/add",
        "/announcements/",
        "/announcements/create",
        "/sermons/",
        "/sermons/add",
        "/profile/",
        "/groups/",
        "/groups/create",
        "/groups/search?q=test",
        "/donations/",
        "/donations/add",
        "/donations/view_all",
        "/donations/reports",
        "/donations/get_years",
        "/donations/members_with_donations",
        "/support-tickets/",
        "/support-tickets/submit",
        "/tickets/",
        "/tickets/manage",
        "/members/directory",
        "/members/member",
        "/members/email_roster",
        "/attendance/",
        "/attendance/dashboard",
        "/attendance/open_kiosk",
        "/attendance/self_checkin",
        "/inventory/",
        "/inventory/items",
        "/inventory/items/add",
        "/inventory/receive",
        "/inventory/cat-location",
        "/inventory/scan",
        "/inventory/audit",
        "/inventory/barcode_lookup",
        "/bills/",
        "/bills/add",
        "/log/",
        "/log/change_records",
        "/settings/",
        "/settings/general",
        "/settings/email",
        "/settings/ai",
        "/settings/online-giving",
        "/settings/censored-words",
        "/settings/timezone",
        "/settings/ticket-managers",
        "/the_gathering/",
        "/the_gathering/dashboard/",
        "/the_gathering/events/",
        "/the_gathering/events/new",
        "/the_gathering/dreams/",
        "/the_gathering/dreams/new",
        "/the_gathering/prayers/",
        "/the_gathering/prophecies/",
        "/the_gathering/prophecies/new",
        "/the_gathering/announcements/",
        "/the_gathering/announcements/new",
        "/the_gathering/sermons/",
        "/pastoral/",
        "/pastoral/care/",
        "/pastoral/care/new",
        "/pastoral/illustrations/library",
        "/pastoral/sermons/",
        "/pastoral/sermons/new",
        "/pastoral/planning/",
        "/pastoral/planning/templates",
        "/pastoral/planning/templates/new",
        "/pastoral/planning/defaults",
        "/pastoral/bible/search",
        "/pastoral/bible/upload",
        "/pastoral/vault/",
        "/pastoral/podium/",
        "/pastoral/sermons/export/",
    ]
    # Dynamic IDs
    for eid in ids.get("events", [])[:5]:
        seeds += [
            f"/events/view/{eid}",
            f"/events/edit/{eid}",
            f"/public/events/{eid}",
        ]
    for pid in ids.get("prayers", [])[:5]:
        seeds += [f"/prayers/{pid}", f"/prayers/{pid}/edit", f"/public/prayers/{pid}"]
    for aid in ids.get("announcements", [])[:5]:
        seeds += [
            f"/announcements/{aid}",
            f"/announcements/edit/{aid}",
            f"/public/announcements/{aid}",
        ]
    for did in ids.get("dreams", [])[:5]:
        seeds += [f"/dreams/{did}", f"/dreams/edit/{did}", f"/public/dreams/{did}"]
    for pid in ids.get("prophecies", [])[:5]:
        seeds += [
            f"/prophecies/{pid}",
            f"/prophecies/edit/{pid}",
            f"/public/prophecies/{pid}",
        ]
    for sid in ids.get("sermons", [])[:5]:
        seeds += [f"/sermons/{sid}", f"/public/sermons/{sid}"]
    for gid in ids.get("groups", [])[:5]:
        seeds.append(f"/groups/edit/{gid}")
    for uid in ids.get("users", [])[:5]:
        seeds.append(f"/members/member/{uid}")
    for cid in ids.get("pastoral_care_requests", [])[:3]:
        seeds += [f"/pastoral/care/{cid}"]
    for psid in ids.get("pastoral_sermons", [])[:3]:
        seeds += [
            f"/pastoral/sermons/edit/{psid}",
            f"/pastoral/podium/view/{psid}",
            f"/pastoral/sermons/export/single/{psid}",
        ]
    for bid in ids.get("recurring_bills", [])[:3]:
        seeds += [f"/bills/{bid}", f"/bills/edit/{bid}", f"/bills/assign/{bid}"]
    for iid in ids.get("items", [])[:3]:
        seeds += [f"/inventory/items/edit/{iid}"]
    for tid in ids.get("tickets", [])[:3]:
        seeds.append(f"/tickets/{tid}")
    for stid in ids.get("support_tickets", [])[:3]:
        seeds.append(f"/support-tickets/{stid}")
    return list(dict.fromkeys(seeds))


def default_field_value(name: str, ftype: str, role: str) -> str:
    n = (name or "").lower()
    if ftype == "hidden":
        return ""
    if "csrf" in n:
        return ""
    if ftype in ("submit", "button", "image", "reset"):
        return ""
    if ftype == "checkbox":
        return "on"
    if ftype == "email" or n == "email":
        return f"crawl_{role}@testchurch.local"
    if n in ("username",):
        return f"crawl_{role}"
    if n in ("password", "confirm_password", "new_password"):
        return "CrawlTest2026!"
    if n in ("title", "subject", "name"):
        return f"Crawl test {role}"
    if n in ("description", "content", "message", "notes", "body", "prayer"):
        return "Automated crawl test content — safe to delete."
    if n in ("first_name",):
        return "Crawl"
    if n in ("last_name",):
        return "Bot"
    if n in ("phone",):
        return "555-0199"
    if n in ("address",):
        return "1 Crawl Lane"
    if n in ("birthday", "date", "service_date"):
        return "2026-07-08"
    if n in ("role",):
        return "Member"
    if n in ("visibility",):
        return "public"
    if n in ("urgency",):
        return "normal"
    if n in ("request_type",):
        return "prayer"
    if n in ("member_id", "user_id"):
        return "3"
    if n in ("action",):
        return "comment"
    return "test"


def fill_form(form: dict, html: str, role: str) -> dict:
    data = {}
    csrf = extract_csrf(html)
    if csrf:
        data["csrf_token"] = csrf
    for field in form.get("fields", []):
        name = field.get("name")
        if not name:
            continue
        ftype = field.get("type", "text")
        if ftype == "hidden" and field.get("value"):
            data[name] = field["value"]
            continue
        if ftype == "select":
            opts = field.get("options") or []
            picked = next((o for o in opts if o.get("selected")), None)
            if not picked and opts:
                picked = opts[0]
            if picked:
                data[name] = picked.get("value", "")
            continue
        if ftype in ("submit", "button", "image", "reset"):
            continue
        if ftype == "checkbox":
            if name not in data:
                data[name] = "on"
            continue
        if name not in data:
            data[name] = default_field_value(name, ftype, role)
    return data


class SiteCrawler:
    def __init__(self, role: str, session: Optional[requests.Session] = None):
        self.role = role
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": UA})
        self.stats = CrawlStats(role=role)
        self.visited: set[str] = set()

    def login(self, username: str, password: str) -> bool:
        r = self.session.get(urljoin(BASE, "/login"), timeout=30)
        csrf = extract_csrf(r.text)
        r2 = self.session.post(
            urljoin(BASE, "/login"),
            data={"csrf_token": csrf, "username": username, "password": password},
            timeout=30,
            allow_redirects=True,
        )
        return "dashboard" in (r2.url or "")

    def record(self, method: str, path: str, r: requests.Response, note: str = "") -> CrawlHit:
        err_type, err_snip = detect_error(r.text or "")
        ok = r.status_code < 500 and not err_type
        hit = CrawlHit(
            role=self.role,
            method=method,
            path=path,
            status=r.status_code,
            final_url=r.url,
            ok=ok,
            error_type=err_type,
            error_snippet=err_snip,
            note=note,
        )
        self.stats.hits.append(hit)
        if not ok:
            self.stats.failures.append(hit)
        return hit

    def fetch(self, path: str) -> Optional[requests.Response]:
        if path in self.visited:
            return None
        self.visited.add(path)
        try:
            r = self.session.get(urljoin(BASE, path), timeout=30, allow_redirects=True)
            self.stats.pages_visited += 1
            self.record("GET", path, r)
            return r
        except requests.RequestException as exc:
            hit = CrawlHit(
                role=self.role,
                method="GET",
                path=path,
                status=0,
                final_url="",
                ok=False,
                error_type="network",
                error_snippet=str(exc)[:200],
            )
            self.stats.failures.append(hit)
            self.stats.hits.append(hit)
            return None

    def submit_form(self, page_path: str, form: dict, page_html: str) -> None:
        actionable = re.search(
            r"/(add|create|edit|submit|new|send|save|request|comment|potluck|upload|receive|assign|record|approve|reject|register|login|care|library|defaults|templates|email|general|online-giving|censored|timezone|ai|kiosk|self_checkin|donate)",
            page_path,
            re.I,
        )
        if not actionable:
            return
        action = form.get("action") or page_path
        method = form.get("method", "GET")
        if method != "POST":
            return
        action_l = action.lower()
        if DESTRUCTIVE_KEYWORDS.search(action_l):
            return
        path = normalize_path(urljoin(BASE, action))
        if not path:
            return
        data = fill_form(form, page_html, self.role)
        if not data.get("csrf_token") and "csrf_token" not in str(form):
            # Might still work via session on some endpoints
            pass
        try:
            r = self.session.post(
                urljoin(BASE, path),
                data=data,
                timeout=45,
                allow_redirects=True,
                headers={"Referer": urljoin(BASE, page_path)},
            )
            self.stats.forms_submitted += 1
            self.record("POST", path, r, note=f"from {page_path}")
        except requests.RequestException as exc:
            hit = CrawlHit(
                role=self.role,
                method="POST",
                path=path,
                status=0,
                final_url="",
                ok=False,
                error_type="network",
                error_snippet=str(exc)[:200],
                note=f"from {page_path}",
            )
            self.stats.failures.append(hit)
            self.stats.hits.append(hit)

    def should_skip_path(self, path: str) -> bool:
        if not path:
            return True
        if any(path.startswith(p) for p in SKIP_PATH_PREFIXES if p != "#"):
            return True
        if path.startswith("/login") and self.role != "guest":
            return True
        if path == "/logout":
            return True
        return False

    def crawl(self, seeds: list[str], max_pages: int = 450) -> CrawlStats:
        queue: deque[str] = deque(seeds)
        max_queue = 800
        while queue and self.stats.pages_visited < max_pages:
            path = queue.popleft()
            if path in self.visited or self.should_skip_path(path):
                continue
            r = self.fetch(path)
            if self.stats.pages_visited % 25 == 0:
                print(f"  [{self.role}] pages={self.stats.pages_visited} queue={len(queue)}", flush=True)
            if r is None or not r.text:
                continue
            parser = LinkFormParser()
            try:
                parser.feed(r.text)
            except Exception:
                continue
            for href in parser.links:
                np = normalize_path(urljoin(path, href))
                if (
                    np
                    and np not in self.visited
                    and np not in queue
                    and not self.should_skip_path(np)
                    and len(queue) < max_queue
                ):
                    queue.append(np)
            for form in parser.forms:
                self.submit_form(path, form, r.text)
        return self.stats


def admin_seed_content(session: requests.Session) -> dict:
    """Create minimal content via HTTP so dynamic routes have targets."""
    created: dict[str, list] = {"events": [], "announcements": [], "dreams": [], "prophecies": []}
    s = SiteCrawler("admin_seed", session)

    def post_form(path: str, extra: dict) -> None:
        r = session.get(urljoin(BASE, path), timeout=30)
        data = fill_form({"fields": [], "method": "POST", "action": path}, r.text, "admin")
        data.update(extra)
        session.post(urljoin(BASE, path), data=data, timeout=45, allow_redirects=True)

    post_form(
        "/events/add",
        {
            "event_name": "Crawl Test Event",
            "description": "Event created by full site crawl.",
            "event_date": "2026-08-15",
            "event_time": "10:00",
            "location": "Main Hall",
            "visibility": "public",
        },
    )
    post_form(
        "/announcements/create",
        {
            "title": "Crawl Test Announcement",
            "content": "Announcement from crawl bot.",
            "visibility": "public",
        },
    )
    post_form(
        "/dreams/submit",
        {
            "title": "Crawl Test Dream",
            "description": "Dream journal crawl entry.",
            "visibility": "public",
        },
    )
    post_form(
        "/prophecies/add",
        {
            "title": "Crawl Test Prophecy",
            "description": "Prophecy crawl entry.",
            "visibility": "public",
        },
    )
    post_form(
        "/pastoral/sermons/new",
        {
            "title": "Crawl Test Sermon",
            "sermon_date": "2026-07-13",
            "status": "draft",
        },
    )
    post_form(
        "/pastoral/illustrations/library",
        {
            "title": "Crawl Illustration",
            "content": "Illustration text from crawl.",
            "category": "story",
            "visibility": "pastoral_group",
        },
    )

    ids = db_ids()
    for k in created:
        created[k] = ids.get(k, [])
    return ids


def main() -> int:
    print(f"Crawling {BASE} ...")
    ids = db_ids()

    # Admin seeds content first
    admin_session = requests.Session()
    admin_session.headers.update({"User-Agent": UA})
    crawler_admin = SiteCrawler("admin", admin_session)
    if not crawler_admin.login(*ACCOUNTS["admin"]):
        print("FATAL: admin login failed")
        return 1
    print("Admin seeding test content...")
    try:
        ids = admin_seed_content(admin_session)
    except Exception as exc:
        print(f"Seed warning: {exc}")
    seeds = seed_paths(ids)
    print(f"Seed URLs: {len(seeds)}")

    all_stats: list[CrawlStats] = []
    roles_order = [
        ("guest", None),
        ("visitor", ACCOUNTS["visitor"]),
        ("member", ACCOUNTS["member"]),
        ("pastor", ACCOUNTS["pastor"]),
        ("admin", ACCOUNTS["admin"]),
    ]

    for role, creds in roles_order:
        print(f"\n=== Crawling as {role} ===")
        sess = requests.Session()
        sess.headers.update({"User-Agent": UA})
        c = SiteCrawler(role, sess)
        if creds:
            if not c.login(*creds):
                print(f"  login failed for {role}, crawling as far as possible")
        t0 = time.time()
        c.crawl(seeds, max_pages=220 if role == "admin" else 160)
        elapsed = time.time() - t0
        print(
            f"  pages={c.stats.pages_visited} forms={c.stats.forms_submitted} "
            f"failures={len(c.stats.failures)} time={elapsed:.0f}s"
        )
        all_stats.append(c.stats)

    report = {
        "base": BASE,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed_count": len(seeds),
        "roles": [],
    }
    total_failures = 0
    for st in all_stats:
        role_report = {
            "role": st.role,
            "pages": st.pages_visited,
            "forms": st.forms_submitted,
            "failure_count": len(st.failures),
            "failures": [asdict(f) for f in st.failures],
        }
        report["roles"].append(role_report)
        total_failures += len(st.failures)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 72)
    print("FULL SITE CRAWL SUMMARY")
    print("=" * 72)
    for st in all_stats:
        print(
            f"{st.role:8} pages={st.pages_visited:4} forms={st.forms_submitted:4} "
            f"FAILURES={len(st.failures)}"
        )
    # fix typo in print - use st.failures
    for st in all_stats:
        if st.failures:
            print(f"\n--- {st.role} failures ---")
            seen = set()
            for f in st.failures:
                key = (f.method, f.path, f.error_type)
                if key in seen:
                    continue
                seen.add(key)
                print(f"  [{f.status}] {f.method} {f.path} ({f.error_type})")
                if f.error_snippet:
                    print(f"       {f.error_snippet[:120]}")

    print(f"\nReport saved: {REPORT_PATH}")
    print(f"TOTAL FAILURES: {total_failures}")
    return 1 if total_failures else 0


if __name__ == "__main__":
    sys.exit(main())