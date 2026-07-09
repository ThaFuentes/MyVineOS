#!/usr/bin/env python3
"""
Structured full-site simulation: guest → member → admin workflows, then security (last).
Explicit HTTP flows (not blind BFS) to avoid crawl explosion.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import pymysql
import requests

BASE = os.environ.get("SIM_BASE", "http://127.0.0.1:5001")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
REPORT = os.path.join(os.path.dirname(__file__), "full_site_sim_report.json")

ADMIN = ("admin", "TestAdmin2026!")
MEMBER = ("sim_member", "SimTest2026!")
VISITOR = ("sim_visitor", "SimTest2026!")
PASTOR = ("sim_pastor", "SimTest2026!")

ERROR_PATS = [
    (r"Traceback \(most recent call last\)", "traceback"),
    (r"Internal Server Error", "500_page"),
    (r"UndefinedError:", "undefined"),
    (r"TypeError:", "type_error"),
    (r"AttributeError:", "attr_error"),
]


@dataclass
class Step:
    phase: str
    role: str
    name: str
    method: str
    path: str
    status: int
    ok: bool
    note: str = ""
    real_fail: bool = True


@dataclass
class Sim:
    steps: list[Step] = field(default_factory=list)

    def add(
        self,
        phase: str,
        role: str,
        name: str,
        method: str,
        path: str,
        r: requests.Response,
        *,
        expect_ok: bool = True,
        allow_status: Optional[set[int]] = None,
        real_fail: bool = True,
    ) -> None:
        text = re.sub(r"<!--.*?-->", "", r.text or "", flags=re.S)
        err = ""
        for pat, et in ERROR_PATS:
            if re.search(pat, text, re.I):
                err = et
                break
        status_ok = r.status_code < 400
        if allow_status:
            status_ok = r.status_code in allow_status
        ok = (status_ok if expect_ok else True) and not err
        if expect_ok and not status_ok:
            ok = False
        note = err or (r.url if r.url != urljoin(BASE, path) else "")
        self.steps.append(
            Step(phase, role, name, method, path, r.status_code, ok, note, real_fail)
        )


def csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not m:
        m = re.search(r'value="([^"]+)"\s+name="csrf_token"', html)
    return m.group(1) if m else ""


def session_for(role: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def login(s: requests.Session, user: str, password: str) -> bool:
    r = s.get(f"{BASE}/login", timeout=30)
    tok = csrf(r.text)
    r2 = s.post(
        f"{BASE}/login",
        data={"csrf_token": tok, "username": user, "password": password},
        timeout=30,
    )
    return "dashboard" in (r2.url or "") and "pending" not in (r2.text or "").lower()


def db_connect():
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", 3308)),
        user=os.environ.get("MYSQL_USER", "churchuser"),
        password=os.environ.get("MYSQL_PASSWORD", "ChurchPass2026!"),
        database=os.environ.get("MYSQL_DATABASE", "church_management"),
        cursorclass=pymysql.cursors.DictCursor,
    )


def db_ids() -> dict:
    out = {}
    try:
        db = db_connect()
        cur = db.cursor()
        for table, col in [
            ("prayers", "id"),
            ("dreams", "id"),
            ("announcements", "id"),
            ("prophecies", "id"),
            ("sermons", "id"),
            ("events", "id"),
            ("users", "id"),
            ("groups", "id"),
        ]:
            try:
                cur.execute(
                    f"SELECT {col} AS id FROM {table} ORDER BY id DESC LIMIT 5"
                )
                out[table] = [r["id"] for r in cur.fetchall()]
            except Exception:
                out[table] = []
        db.close()
    except Exception as exc:
        print(f"DB warning: {exc}")
    return out


def get_record(sim: Sim, phase: str, role: str, name: str, path: str, s: requests.Session) -> requests.Response:
    r = s.get(f"{BASE}{path}", timeout=30)
    sim.add(phase, role, name, "GET", path, r)
    return r


def post_record(
    sim: Sim,
    phase: str,
    role: str,
    name: str,
    path: str,
    s: requests.Session,
    data: dict,
    referer: str = "",
) -> requests.Response:
    headers = {"Referer": urljoin(BASE, referer or path)} if referer or path else {}
    r = s.post(f"{BASE}{path}", data=data, headers=headers, timeout=45)
    sim.add(phase, role, name, "POST", path, r)
    return r


def guest_public_phase(sim: Sim, ids: dict) -> None:
    phase, role = "1_public", "guest"
    s = session_for(role)
    pages = [
        "/public/",
        "/public/community",
        "/public/events/",
        "/public/prayers/",
        "/public/sermons/",
        "/public/dreams/",
        "/public/prophecies/",
        "/public/announcements/",
        "/public/donate",
        "/login",
    ]
    for p in pages:
        get_record(sim, phase, role, f"Browse {p}", p, s)

    # Guest comments on public content
    for content_type, table, path_tpl, fields in [
        (
            "prayer",
            "prayers",
            "/public/prayers/{id}",
            {"action": "comment", "contributor_name": "Guest Sam", "comment": "Praying with you — sim test."},
        ),
        (
            "dream",
            "dreams",
            "/public/dreams/{id}",
            {"action": "comment", "contributor_name": "Guest Sam", "comment": "Thank you for sharing this dream."},
        ),
        (
            "announcement",
            "announcements",
            "/public/announcements/{id}",
            {"action": "comment", "contributor_name": "Guest Sam", "comment": "Great announcement!"},
        ),
    ]:
        cid = (ids.get(table) or [None])[0]
        if not cid:
            sim.steps.append(
                Step(phase, role, f"Guest comment {content_type}", "SKIP", path_tpl, 0, True, "no content id", False)
            )
            continue
        path = path_tpl.format(id=cid)
        r = get_record(sim, phase, role, f"View public {content_type}", path, s)
        tok = csrf(r.text)
        data = dict(fields)
        if tok:
            data["csrf_token"] = tok
        post_record(sim, phase, role, f"Guest comment {content_type}", path, s, data, referer=path)


def member_phase(sim: Sim, ids: dict) -> None:
    phase, role = "2_member", "member"
    s = session_for(role)
    if not login(s, *MEMBER):
        sim.steps.append(Step(phase, role, "Login", "POST", "/login", 0, False, "login failed"))
        return
    sim.steps.append(Step(phase, role, "Login", "POST", "/login", 200, True))

    for p in [
        "/dashboard",
        "/prayers/",
        "/prayers/add",
        "/events/",
        "/dreams/",
        "/prophecies/",
        "/announcements/",
        "/sermons/",
        "/profile/",
        "/groups/",
        "/donations/",
        "/support-tickets/",
        "/support-tickets/submit",
    ]:
        get_record(sim, phase, role, f"Browse {p}", p, s)

    # Create prayer
    r = get_record(sim, phase, role, "Prayer add form", "/prayers/add", s)
    tok = csrf(r.text)
    if tok:
        post_record(
            sim,
            phase,
            role,
            "Submit prayer",
            "/prayers/add",
            s,
            {
                "csrf_token": tok,
                "title": "Member Sim Prayer",
                "description": "Please pray for our church family this week.",
                "visibility": "public",
            },
            referer="/prayers/add",
        )

    # Submit dream
    r = get_record(sim, phase, role, "Dream submit form", "/dreams/submit", s)
    tok = csrf(r.text)
    if tok:
        post_record(
            sim,
            phase,
            role,
            "Submit dream",
            "/dreams/submit",
            s,
            {
                "csrf_token": tok,
                "title": "Member Sim Dream",
                "description": "Dream journal entry from site simulation.",
                "visibility": "public",
            },
            referer="/dreams/submit",
        )

    # Member comment on own-area prayer if exists
    pid = (ids.get("prayers") or [None])[0]
    if pid:
        r = get_record(sim, phase, role, "View prayer", f"/prayers/{pid}", s)
        tok = csrf(r.text)
        if tok:
            post_record(
                sim,
                phase,
                role,
                "Prayer response",
                f"/prayers/{pid}",
                s,
                {"csrf_token": tok, "prayer": "Lord hear our prayer — member sim response."},
                referer=f"/prayers/{pid}",
            )

    # Support ticket
    r = get_record(sim, phase, role, "Support ticket form", "/support-tickets/submit", s)
    tok = csrf(r.text)
    if tok:
        post_record(
            sim,
            phase,
            role,
            "Submit support ticket",
            "/support-tickets/submit",
            s,
            {
                "csrf_token": tok,
                "subject": "Sim support ticket",
                "description": "Testing support ticket flow from simulation.",
                "priority": "normal",
            },
            referer="/support-tickets/submit",
        )

    s.get(f"{BASE}/logout", timeout=15)


def approved_visitor_phase(sim: Sim, ids: dict) -> None:
    phase, role = "1b_visitor", "visitor"
    s = session_for(role)
    if not login(s, *VISITOR):
        sim.steps.append(
            Step(phase, role, "Login", "POST", "/login", 0, False, "visitor login failed — approve sim_visitor?")
        )
        return
    sim.steps.append(Step(phase, role, "Login", "POST", "/login", 200, True))

    for p in ["/dashboard", "/prayers/", "/prayers/add", "/profile/"]:
        get_record(sim, phase, role, f"Browse {p}", p, s)

    r = get_record(sim, phase, role, "Prayer add form", "/prayers/add", s)
    tok = csrf(r.text)
    if tok:
        post_record(
            sim,
            phase,
            role,
            "Visitor prayer request",
            "/prayers/add",
            s,
            {
                "csrf_token": tok,
                "title": "Visitor Prayer Request",
                "description": "Newly approved visitor prayer sim.",
                "visibility": "public",
            },
            referer="/prayers/add",
        )
    s.get(f"{BASE}/logout", timeout=15)


def admin_phase(sim: Sim, ids: dict) -> None:
    phase, role = "3_admin", "admin"
    s = session_for(role)
    if not login(s, *ADMIN):
        sim.steps.append(Step(phase, role, "Login", "POST", "/login", 0, False, "admin login failed"))
        return
    sim.steps.append(Step(phase, role, "Login", "POST", "/login", 200, True))

    admin_pages = [
        "/dashboard",
        "/members/directory",
        "/settings/",
        "/settings/general",
        "/settings/ai",
        "/groups/",
        "/announcements/",
        "/announcements/create",
        "/events/",
        "/events/add",
        "/the_gathering/",
        "/the_gathering/dashboard/",
        "/the_gathering/prayers/",
        "/the_gathering/dreams/",
        "/the_gathering/announcements/",
        "/the_gathering/sermons/",
        "/the_gathering/events/",
        "/attendance/",
        "/inventory/",
        "/log/",
        "/pastoral/bible/upload",
    ]
    for p in admin_pages:
        get_record(sim, phase, role, f"Browse {p}", p, s)

    # Create announcement for moderation pipeline
    r = get_record(sim, phase, role, "Announcement create", "/announcements/create", s)
    tok = csrf(r.text)
    if tok:
        post_record(
            sim,
            phase,
            role,
            "Create announcement",
            "/announcements/create",
            s,
            {
                "csrf_token": tok,
                "title": "Admin Sim Announcement",
                "content": "<p>Announcement from full site simulation.</p>",
                "visibility": "public",
            },
            referer="/announcements/create",
        )

    # Member permissions edit
    r = get_record(sim, phase, role, "Members directory", "/members/directory?search_term=sim_member", s)
    m = re.search(r"/members/member/(\d+)", r.text)
    if m:
        uid = m.group(1)
        r = get_record(sim, phase, role, "Edit member", f"/members/member/{uid}", s)
        tok = csrf(r.text)
        if tok:
            post_record(
                sim,
                phase,
                role,
                "Update member role",
                f"/members/member/{uid}",
                s,
                {
                    "csrf_token": tok,
                    "first_name": "Mary",
                    "last_name": "Member",
                    "email": "sim_member@testchurch.local",
                    "phone": "555-0100",
                    "address": "123 Test St",
                    "birthday": "1990-01-15",
                    "role": "Member",
                    "accepts_emails": "on",
                },
                referer=f"/members/member/{uid}",
            )

    # Gathering moderation pages (browse detail with comments)
    for table, path in [
        ("dreams", "/the_gathering/dreams/"),
        ("announcements", "/the_gathering/announcements/"),
    ]:
        cid = (ids.get(table) or [None])[0]
        if cid:
            get_record(sim, phase, role, f"Moderate {table}", f"{path}{cid}", s)

    s.get(f"{BASE}/logout", timeout=15)


def pastor_smoke(sim: Sim) -> None:
    phase, role = "2b_pastor", "pastor"
    s = session_for(role)
    if not login(s, *PASTOR):
        return
    for p in ["/pastoral/", "/pastoral/bible/study", "/pastoral/sermons/", "/pastoral/care/"]:
        get_record(sim, phase, role, f"Browse {p}", p, s)
    s.get(f"{BASE}/logout", timeout=15)


def security_phase(sim: Sim) -> None:
    """Run only after functional tests — basic auth boundary checks."""
    phase, role = "4_security", "security"

    # Guest cannot access admin settings
    s = session_for("guest")
    r = s.get(f"{BASE}/settings/general", timeout=20, allow_redirects=True)
    blocked = "settings" not in (r.url or "") or r.status_code in (302, 403)
    sim.steps.append(
        Step(
            phase,
            role,
            "Guest blocked from settings",
            "GET",
            "/settings/general",
            r.status_code,
            blocked,
            r.url,
            True,
        )
    )

    # Member cannot access pastoral
    s = session_for("member")
    if login(s, *MEMBER):
        r = s.get(f"{BASE}/pastoral/", timeout=20, allow_redirects=True)
        blocked = "/pastoral" not in (r.url or "") or "dashboard" in (r.url or "")
        sim.steps.append(
            Step(
                phase,
                role,
                "Member blocked from pastoral",
                "GET",
                "/pastoral/",
                r.status_code,
                blocked,
                r.url,
                True,
            )
        )
        s.get(f"{BASE}/logout", timeout=10)

    # POST without CSRF should fail on prayer add
    s = session_for("member")
    if login(s, *MEMBER):
        r = s.post(
            f"{BASE}/prayers/add",
            data={"title": "No CSRF", "description": "test", "visibility": "public"},
            timeout=20,
        )
        csrf_blocked = r.status_code in (400, 403) or "csrf" in (r.text or "").lower()
        sim.steps.append(
            Step(
                phase,
                role,
                "CSRF required on prayer add",
                "POST",
                "/prayers/add",
                r.status_code,
                csrf_blocked,
                "expected 400/403",
                True,
            )
        )
        s.get(f"{BASE}/logout", timeout=10)


def print_report(sim: Sim) -> tuple[int, int]:
    real_fails = [x for x in sim.steps if not x.ok and x.real_fail]
    skips = [x for x in sim.steps if not x.ok and not x.real_fail]
    print("\n" + "=" * 78)
    print("FULL SITE SIMULATION")
    print("=" * 78)
    cur_phase = ""
    for st in sim.steps:
        if st.phase != cur_phase:
            cur_phase = st.phase
            print(f"\n--- {cur_phase} ---")
        flag = "OK" if st.ok else ("SKIP" if not st.real_fail else "FAIL")
        extra = f" → {st.note}" if st.note else ""
        print(f"[{flag}] {st.role:8} {st.name:32} {st.method} {st.status}{extra}")
    print("-" * 78)
    print(f"Steps: {len(sim.steps)}  Real failures: {len(real_fails)}  Skips: {len(skips)}")
    return len(real_fails), len(skips)


def main() -> int:
    print(f"Full site simulation @ {BASE}")
    t0 = time.time()
    sim = Sim()
    ids = db_ids()
    print(f"DB ids loaded: { {k: len(v) for k, v in ids.items()} }")

    guest_public_phase(sim, ids)
    approved_visitor_phase(sim, ids)
    member_phase(sim, ids)
    pastor_smoke(sim)
    admin_phase(sim, ids)

    real_fails, _ = print_report(sim)

    if real_fails == 0:
        print("\nFunctional tests passed — running security phase...")
        security_phase(sim)
        real_fails, _ = print_report(sim)
    else:
        print("\nSkipping security phase until functional failures are fixed.")

    report = {
        "base": BASE,
        "elapsed_sec": round(time.time() - t0, 1),
        "steps": [
            {
                "phase": s.phase,
                "role": s.role,
                "name": s.name,
                "method": s.method,
                "path": s.path,
                "status": s.status,
                "ok": s.ok,
                "note": s.note,
            }
            for s in sim.steps
        ],
        "failures": sum(1 for s in sim.steps if not s.ok and s.real_fail),
    }
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport: {REPORT}")
    return 1 if real_fails else 0


if __name__ == "__main__":
    sys.exit(main())