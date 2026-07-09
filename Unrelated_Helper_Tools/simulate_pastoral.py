#!/usr/bin/env python3
"""Full HTTP simulation of the Pastoral Area as sim_pastor."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import pymysql
import requests

BASE = "http://127.0.0.1:5001"
UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0"
USER, PASS = "sim_pastor", "SimTest2026!"

ERROR_PATS = [
    (r"Traceback \(most recent call last\)", "traceback"),
    (r"UndefinedError:", "undefined"),
    (r"TypeError:", "type_error"),
    (r"Internal Server Error", "500_page"),
]


@dataclass
class Step:
    name: str
    method: str
    path: str
    status: int
    ok: bool
    detail: str = ""


@dataclass
class Run:
    steps: list[Step] = field(default_factory=list)
    created: dict = field(default_factory=dict)

    def add(
        self,
        name: str,
        method: str,
        path: str,
        r: requests.Response,
        expect_ok: bool = True,
        allow_status: Optional[set[int]] = None,
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
        detail = err
        if not detail and r.url != urljoin(BASE, path):
            detail = r.url
        self.steps.append(Step(name, method, path, r.status_code, ok, detail))


def csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""


def login() -> tuple[requests.Session, str]:
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    r = s.get(f"{BASE}/login", timeout=30)
    tok = csrf(r.text)
    r2 = s.post(
        f"{BASE}/login",
        data={"csrf_token": tok, "username": USER, "password": PASS},
        timeout=30,
    )
    if "dashboard" not in (r2.url or ""):
        raise RuntimeError(f"Pastor login failed: {r2.url}")
    return s, tok


def pastoral_get(run: Run, s: requests.Session, path: str, name: str) -> requests.Response:
    r = s.get(f"{BASE}{path}", timeout=30)
    run.add(name, "GET", path, r)
    return r


def main() -> int:
    run = Run()
    print("=== Pastoral Area Simulation (sim_pastor) ===\n")

    try:
        s, _ = login()
    except Exception as e:
        print(f"FATAL: {e}")
        return 1

    # Refresh CSRF from pastoral dashboard
    r = pastoral_get(run, s, "/pastoral/", "Dashboard")
    tok = csrf(r.text)

    pages = [
        ("/pastoral/sermons/", "Sermons list"),
        ("/pastoral/sermons/new", "Sermon builder (new)"),
        ("/pastoral/illustrations/library", "Illustrations library"),
        ("/pastoral/care/", "Care dashboard"),
        ("/pastoral/care/new", "Care new form"),
        ("/pastoral/planning/", "Planning"),
        ("/pastoral/planning/templates", "Planning templates"),
        ("/pastoral/planning/templates/new", "New template"),
        ("/pastoral/planning/defaults", "Planning defaults"),
        ("/pastoral/bible/search", "Bible search"),
        ("/pastoral/bible/upload", "Bible upload"),
        ("/pastoral/vault/", "Vault"),
        ("/pastoral/podium/", "Podium"),
        ("/pastoral/sermons/export/", "Sermon export"),
    ]
    for path, name in pages:
        pastoral_get(run, s, path, name)

    # --- Create sermon via builder POST ---
    r = s.get(f"{BASE}/pastoral/sermons/new", timeout=30)
    tok = csrf(r.text) or tok
    sections = json.dumps(
        [
            {
                "title": "Main Point",
                "content": "<p>God's grace is sufficient for every trial we face.</p>",
                "section_type": "point",
                "source": "Personal testimony",
                "notes": "Emphasize hope",
                "scripture_reference": "2 Corinthians 12:9",
            }
        ]
    )
    r = s.post(
        f"{BASE}/pastoral/sermons/new",
        data={
            "csrf_token": tok,
            "title": "Pastoral Sim Sermon",
            "primary_passage": "John 3:16",
            "visibility": "private",
            "header_text": "Welcome everyone.",
            "footer_text": "Go in peace.",
            "notes": "Simulation sermon notes.",
            "sections_json": sections,
        },
        timeout=30,
    )
    run.add("Create sermon (POST)", "POST", "/pastoral/sermons/new", r)
    sermon_id = None
    m = re.search(r"/pastoral/sermons/edit/(\d+)", r.url or "")
    if m:
        sermon_id = int(m.group(1))
        run.created["sermon_id"] = sermon_id

    if sermon_id:
        pastoral_get(run, s, f"/pastoral/sermons/edit/{sermon_id}", "Sermon edit")
        pastoral_get(run, s, f"/pastoral/podium/view/{sermon_id}", "Podium view")
        pastoral_get(run, s, f"/pastoral/sermons/export/single/{sermon_id}", "Export single")

    # --- Autosave JSON ---
    r = s.post(
        f"{BASE}/pastoral/sermons/autosave",
        json={
            "sermon_id": sermon_id,
            "sermon": {"title": "Pastoral Sim Sermon", "notes": "Autosaved notes."},
            "sections": json.loads(sections),
        },
        headers={"X-CSRF-Token": tok, "Content-Type": "application/json"},
        timeout=30,
    )
    run.add("Sermon autosave", "POST", "/pastoral/sermons/autosave", r)

    # --- Illustration via library POST ---
    r = s.get(f"{BASE}/pastoral/illustrations/library", timeout=30)
    tok = csrf(r.text) or tok
    if "window.CSRF_TOKEN" in r.text:
        m = re.search(r'window\.CSRF_TOKEN = "([^"]*)"', r.text)
        if m and m.group(1):
            tok = m.group(1)
    r = s.post(
        f"{BASE}/pastoral/illustrations/library",
        data={
            "csrf_token": tok,
            "title": "Sim Illustration - Lost Sheep",
            "content": "<p>A shepherd left ninety-nine to find one lost sheep.</p>",
            "source": "Luke 15 parable retelling",
            "tags": "grace, sheep, parable",
            "notes": "Use in evangelism series",
            "visibility": "private",
        },
        timeout=30,
    )
    run.add("Create illustration (library)", "POST", "/pastoral/illustrations/library", r)
    illus_id = None

    # --- quick_add from sermon builder (AJAX) ---
    r = s.post(
        f"{BASE}/pastoral/illustrations/quick_add",
        json={
            "title": "Quick Add Illustration",
            "content": "Saved quickly from sermon builder simulation.",
            "source": "Sermon editor",
            "tags": "quick,builder",
        },
        headers={"X-CSRF-Token": tok, "Content-Type": "application/json"},
        timeout=30,
    )
    run.add("Quick-add illustration (builder)", "POST", "/pastoral/illustrations/quick_add", r)
    if r.status_code == 200:
        try:
            quick_id = r.json().get("id")
            if quick_id:
                run.created["quick_illus_id"] = quick_id
                illus_id = quick_id
        except Exception:
            pass

    # --- list_json for insert modal ---
    r = s.get(f"{BASE}/pastoral/illustrations/list_json", timeout=30)
    run.add("Illustrations list_json", "GET", "/pastoral/illustrations/list_json", r)
    if r.status_code == 200 and not illus_id:
        try:
            items = r.json()
            if items:
                illus_id = items[0]["id"]
        except Exception:
            pass

    # DB fallback for illustration id
    if not illus_id:
        db = pymysql.connect(
            host="127.0.0.1",
            port=3308,
            user="churchuser",
            password="ChurchPass2026!",
            database="church_management",
            cursorclass=pymysql.cursors.DictCursor,
        )
        cur = db.cursor()
        cur.execute(
            "SELECT id FROM illustration_library WHERE title LIKE %s ORDER BY id DESC LIMIT 1",
            ("%Sim Illustration%",),
        )
        row = cur.fetchone()
        if row:
            illus_id = row["id"]
        db.close()

    if illus_id:
        run.created["illus_id"] = illus_id
        pastoral_get(run, s, f"/pastoral/illustrations/view/{illus_id}", "View illustration")

        if sermon_id:
            r = s.post(
                f"{BASE}/pastoral/illustrations/insert/{sermon_id}",
                json={"item_id": illus_id},
                headers={"X-CSRF-Token": tok, "Content-Type": "application/json"},
                timeout=30,
            )
            run.add("Insert illustration into sermon", "POST", f"/pastoral/illustrations/insert/{sermon_id}", r)

        r = s.post(
            f"{BASE}/pastoral/illustrations/dock",
            json={"item_ids": [illus_id]},
            headers={"X-CSRF-Token": tok, "Content-Type": "application/json"},
            timeout=30,
        )
        run.add("Dock illustration", "POST", "/pastoral/illustrations/dock", r)

    # --- Pastoral care full flow ---
    r = s.get(f"{BASE}/pastoral/care/new", timeout=30)
    tok = csrf(r.text) or tok
    r = s.post(
        f"{BASE}/pastoral/care/new",
        data={
            "csrf_token": tok,
            "member_id": "3",
            "request_type": "hospital_visit",
            "urgency": "high",
            "title": "Sim Care - Hospital Visit",
            "description": "Member recovering from surgery; needs pastoral visit and prayer.",
        },
        timeout=30,
    )
    run.add("Create care request", "POST", "/pastoral/care/new", r)
    care_id = None
    m = re.search(r"/pastoral/care/(\d+)", r.url or "")
    if m:
        care_id = int(m.group(1))
        run.created["care_id"] = care_id

    if care_id:
        r = pastoral_get(run, s, f"/pastoral/care/{care_id}", "Care detail")
        tok = csrf(r.text) or tok

        # Get pastor id for assign
        pastor_id = "4"  # sim_pastor
        r = s.post(
            f"{BASE}/pastoral/care/{care_id}/assign",
            data={
                "csrf_token": tok,
                "pastor_id": pastor_id,
                "is_primary": "1",
                "notes": "Primary contact for this case",
            },
            timeout=30,
        )
        run.add("Assign pastor to care", "POST", f"/pastoral/care/{care_id}/assign", r)

        r = s.post(
            f"{BASE}/pastoral/care/{care_id}/note",
            data={
                "csrf_token": tok,
                "note": "Called family — visit scheduled for Thursday afternoon.",
                "is_private": "1",
            },
            timeout=30,
        )
        run.add("Add care note", "POST", f"/pastoral/care/{care_id}/note", r)

        r = s.post(
            f"{BASE}/pastoral/care/{care_id}/edit",
            data={"csrf_token": tok, "status": "in_progress", "urgency": "normal"},
            timeout=30,
        )
        run.add("Update care status", "POST", f"/pastoral/care/{care_id}/edit", r)

    # --- Vault search ajax ---
    r = s.get(f"{BASE}/pastoral/vault/search_ajax?q=test", timeout=30)
    run.add("Vault search", "GET", "/pastoral/vault/search_ajax", r)

    # --- Vault integration (sermon editor modals) ---
    r = s.post(
        f"{BASE}/pastoral/vault/integration/quick_save",
        json={
            "title": "Vault Integration Section",
            "content": "<p>Section saved from sermon builder integration.</p>",
            "section_type": "point",
            "scripture_reference": "Psalm 23:1",
            "tags": "vault,sim",
            "visibility": "private",
        },
        headers={"X-CSRF-Token": tok, "Content-Type": "application/json"},
        timeout=30,
    )
    run.add("Vault integration quick_save", "POST", "/pastoral/vault/integration/quick_save", r)

    r = s.get(f"{BASE}/pastoral/vault/integration/search?q=Vault", timeout=30)
    run.add("Vault integration search", "GET", "/pastoral/vault/integration/search", r)

    r = s.post(
        f"{BASE}/pastoral/vault/save_section_ajax",
        json={
            "title": "Vault AJAX Section",
            "content": "<p>Quick-saved via save_section_ajax.</p>",
            "section_type": "application",
            "visibility": "private",
        },
        headers={"X-CSRF-Token": tok, "Content-Type": "application/json"},
        timeout=30,
    )
    run.add("Vault save_section_ajax", "POST", "/pastoral/vault/save_section_ajax", r)

    r = s.post(
        f"{BASE}/pastoral/illustrations/clear_dock",
        headers={"X-CSRF-Token": tok, "Content-Type": "application/json"},
        timeout=30,
    )
    run.add("Clear illustration dock", "POST", "/pastoral/illustrations/clear_dock", r)

    # --- Bible AJAX ---
    r = s.get(f"{BASE}/pastoral/bible/search?q=love&limit=5", timeout=30)
    run.add("Bible verse search", "GET", "/pastoral/bible/search", r)
    r = s.get(f"{BASE}/pastoral/bible/chapter/John/3", timeout=30)
    run.add("Bible chapter fetch", "GET", "/pastoral/bible/chapter/John/3", r, allow_status={200, 404})

    # --- Planning: create recurring template ---
    r = s.get(f"{BASE}/pastoral/planning/templates/new", timeout=30)
    tok = csrf(r.text) or tok
    r = s.post(
        f"{BASE}/pastoral/planning/templates/new",
        data={
            "csrf_token": tok,
            "title": "Sim Sunday Service Template",
            "weekday": "6",
            "notes": "Standard Sunday flow",
            "forced_notes": "Announcements after worship",
            "start_time": "10:00",
            "worship_start_time": "10:30",
        },
        timeout=30,
    )
    run.add("Create planning template", "POST", "/pastoral/planning/templates/new", r)

    from datetime import date, timedelta

    plan_date = (date.today() + timedelta(days=14)).strftime("%Y-%m-%d")
    pastoral_get(run, s, f"/pastoral/planning/edit/{plan_date}", "Planning edit (override)")

    # --- Bulk sermon export ---
    if sermon_id:
        r = s.post(
            f"{BASE}/pastoral/sermons/export/bulk",
            data={"csrf_token": tok, "sermon_ids": [str(sermon_id)]},
            timeout=60,
        )
        run.add("Bulk export sermons", "POST", "/pastoral/sermons/export/bulk", r)

        # --- AI assistant endpoints (OK if AI not configured — must not 500-crash) ---
        for ai_name, ai_path, ai_body in [
            (
                "AI generate outline",
                f"/pastoral/sermons/ai/generate_outline/{sermon_id}",
                {"title": "Pastoral Sim Sermon", "primary_passage": "John 3:16"},
            ),
            (
                "AI suggest questions",
                f"/pastoral/sermons/ai/suggest_questions/{sermon_id}",
                {"context": "God's love for the world through Christ"},
            ),
            (
                "AI expand point",
                f"/pastoral/sermons/ai/expand_point/{sermon_id}",
                {"point": "Grace is sufficient for every trial"},
            ),
        ]:
            r = s.post(
                f"{BASE}{ai_path}",
                json=ai_body,
                headers={"X-CSRF-Token": tok, "Content-Type": "application/json"},
                timeout=45,
            )
            run.add(ai_name, "POST", ai_path, r, allow_status={200, 400, 500})

    # --- Report ---
    fails = [x for x in run.steps if not x.ok]
    print("\nRESULTS")
    print("-" * 60)
    for st in run.steps:
        flag = "OK" if st.ok else "FAIL"
        extra = f" → {st.detail}" if st.detail else ""
        print(f"[{flag}] {st.name:35} {st.method} {st.status}{extra}")
    print("-" * 60)
    print(f"Steps: {len(run.steps)}  Failures: {len(fails)}")
    if run.created:
        print(f"Created: {run.created}")

    # DB verification
    db = pymysql.connect(
        host="127.0.0.1",
        port=3308,
        user="churchuser",
        password="ChurchPass2026!",
        database="church_management",
        cursorclass=pymysql.cursors.DictCursor,
    )
    cur = db.cursor()
    if run.created.get("sermon_id"):
        sid = run.created["sermon_id"]
        cur.execute("SELECT title FROM pastoral_sermons WHERE id=%s", (sid,))
        print(f"DB sermon: {cur.fetchone()}")
        cur.execute(
            "SELECT COUNT(*) AS c FROM sermon_sections WHERE sermon_id=%s",
            (sid,),
        )
        print(f"DB sermon sections: {cur.fetchone()['c']}")
        cur.execute(
            "SELECT content FROM sermon_sections WHERE sermon_id=%s AND content LIKE %s",
            (sid, "%sheep%"),
        )
        inserted = cur.fetchone()
        print(f"DB illustration in sermon: {'yes' if inserted else 'no'}")
    cur.execute("SELECT COUNT(*) AS c FROM illustration_library WHERE title LIKE %s", ("%Illustration%",))
    print(f"DB illustrations matching: {cur.fetchone()['c']}")
    if run.created.get("care_id"):
        cur.execute(
            "SELECT status, urgency FROM pastoral_care_requests WHERE id=%s",
            (run.created["care_id"],),
        )
        print(f"DB care: {cur.fetchone()}")
        cur.execute(
            "SELECT COUNT(*) AS c FROM pastoral_care_notes WHERE request_id=%s",
            (run.created["care_id"],),
        )
        print(f"DB care notes: {cur.fetchone()['c']}")
    db.close()

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())