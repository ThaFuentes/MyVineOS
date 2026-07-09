#!/usr/bin/env python3
"""
Simulate real browser-like HTTP sessions against a running MyVine OS dev server.
Creates test accounts via register + admin approval flows (no direct DB writes).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import requests

BASE = "http://127.0.0.1:5001"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

TEST_PASSWORD = "SimTest2026!"
ADMIN_USER = "admin"
ADMIN_PASS = "TestAdmin2026!"

ACCOUNTS = {
    "visitor": {
        "username": "sim_visitor",
        "email": "sim_visitor@testchurch.local",
        "first_name": "Sam",
        "last_name": "Visitor",
        "role": "pending",
    },
    "member": {
        "username": "sim_member",
        "email": "sim_member@testchurch.local",
        "first_name": "Mary",
        "last_name": "Member",
        "role": "Member",
    },
    "pastor": {
        "username": "sim_pastor",
        "email": "sim_pastor@testchurch.local",
        "first_name": "Paul",
        "last_name": "Pastor",
        "role": "Staff",
    },
}


@dataclass
class SimResult:
    role: str
    path: str
    status: int
    ok: bool
    note: str = ""
    error_snippet: str = ""


@dataclass
class SimSession:
    role: str
    session: requests.Session
    results: list[SimResult] = field(default_factory=list)

    def get(self, path: str, *, allow_redirects: bool = True) -> requests.Response:
        url = urljoin(BASE, path)
        r = self.session.get(url, allow_redirects=allow_redirects, timeout=30)
        self._record(path, r)
        return r

    def post(self, path: str, data: dict, *, referer: Optional[str] = None) -> requests.Response:
        url = urljoin(BASE, path)
        headers = {}
        if referer:
            headers["Referer"] = urljoin(BASE, referer)
        r = self.session.post(url, data=data, headers=headers, allow_redirects=True, timeout=30)
        self._record(path, r, method="POST")
        return r

    def _record(self, path: str, r: requests.Response, method: str = "GET") -> None:
        text = re.sub(r"<!--.*?-->", "", r.text or "", flags=re.S)
        err = ""
        for pat in (
            r"Traceback \(most recent call last\)",
            r"Internal Server Error",
            r"UndefinedError:",
            r"TypeError:",
            r"AttributeError:",
            r"KeyError:",
            r"sqlalchemy\.exc",
            r"pymysql\.err",
        ):
            if re.search(pat, text, re.I):
                m = re.search(pat + r".{0,200}", text, re.I | re.S)
                err = (m.group(0) if m else pat)[:300]
                break
        ok = r.status_code < 400 and not err
        self.results.append(
            SimResult(
                role=self.role,
                path=f"{method} {path}",
                status=r.status_code,
                ok=ok,
                note=r.url if r.url != urljoin(BASE, path) else "",
                error_snippet=err,
            )
        )


def extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not m:
        m = re.search(r'value="([^"]+)"\s+name="csrf_token"', html)
    return m.group(1) if m else ""


def register_account(sess: SimSession, key: str) -> bool:
    acc = ACCOUNTS[key]
    r = sess.get("/login?tab=register")
    csrf = extract_csrf(r.text)
    data = {
        "csrf_token": csrf,
        "first_name": acc["first_name"],
        "last_name": acc["last_name"],
        "email": acc["email"],
        "phone": "555-0100",
        "address": "123 Test St",
        "birthday": "1990-01-15",
        "username": acc["username"],
        "password": TEST_PASSWORD,
        "confirm_password": TEST_PASSWORD,
        "accepts_emails": "on",
    }
    r2 = sess.post("/register", data, referer="/login?tab=register")
    return r2.status_code < 400


def login(sess: SimSession, username: str, password: str) -> bool:
    r = sess.get("/login")
    csrf = extract_csrf(r.text)
    r2 = sess.post(
        "/login",
        {"csrf_token": csrf, "username": username, "password": password},
        referer="/login",
    )
    ok = "dashboard" in (r2.url or "") and "pending approval" not in (r2.text or "").lower()
    if not ok:
        print(f"  [{sess.role}] login {username}: failed (url={r2.url})")
    return ok


def logout(sess: SimSession) -> None:
    sess.get("/logout")


def find_user_id_in_directory(html: str, email: str) -> Optional[int]:
    """Match member edit link to row containing the account email."""
    chunks = html.split("<tr")
    for chunk in chunks:
        if email.lower() not in chunk.lower():
            continue
        m = re.search(r'/members/member/(\d+)', chunk)
        if m:
            return int(m.group(1))
    return None


def find_pastoral_group_id(html: str) -> Optional[int]:
    m = re.search(
        r'<input[^>]+name="groups"[^>]+value="(\d+)"[^>]*>[^<]*Pastoral Group',
        html,
        re.I | re.S,
    )
    if m:
        return int(m.group(1))
    m = re.search(
        r'value="(\d+)"[^>]*>[\s\S]{0,80}Pastoral Group',
        html,
        re.I,
    )
    return int(m.group(1)) if m else None


def admin_approve_user(admin: SimSession, username: str, role: str, pastoral: bool = False) -> bool:
    acc = next((a for a in ACCOUNTS.values() if a["username"] == username), None)
    if not acc:
        return False

    r = admin.get(f"/members/directory?search_term={username}")
    user_id = find_user_id_in_directory(r.text, acc["email"])
    if not user_id:
        r = admin.get("/members/directory")
        user_id = find_user_id_in_directory(r.text, acc["email"])
    if not user_id:
        print(f"  [admin] could not find user {username} in directory")
        return False

    r = admin.get(f"/members/member/{user_id}")
    csrf = extract_csrf(r.text)
    pastoral_gid = find_pastoral_group_id(r.text) if pastoral else None
    data = {
        "csrf_token": csrf,
        "first_name": acc["first_name"],
        "last_name": acc["last_name"],
        "email": acc["email"],
        "phone": "555-0100",
        "address": "123 Test St",
        "birthday": "1990-01-15",
        "role": role,
        "accepts_emails": "on",
    }
    if pastoral_gid:
        data["groups"] = str(pastoral_gid)
    admin.post(f"/members/member/{user_id}", data, referer=f"/members/member/{user_id}")
    print(f"  [admin] approved {username} (id={user_id}) as {role}" + (" + Pastoral Group" if pastoral_gid else ""))
    return True


def browse_pages(sess: SimSession, paths: list[str]) -> None:
    for p in paths:
        sess.get(p)


def print_report(all_results: list[SimResult]) -> int:
    failures = [r for r in all_results if not r.ok]
    print("\n" + "=" * 72)
    print("SIMULATION REPORT")
    print("=" * 72)
    for r in all_results:
        flag = "OK" if r.ok else "FAIL"
        line = f"[{flag}] {r.role:8} {r.path:40} -> {r.status}"
        if r.note:
            line += f"  ({r.note})"
        print(line)
        if r.error_snippet:
            print(f"       ERROR: {r.error_snippet[:200]}")
    print("-" * 72)
    print(f"Total: {len(all_results)}  Failures: {len(failures)}")
    return len(failures)


def main() -> int:
    all_results: list[SimResult] = []

    # --- Guest ---
    guest = SimSession("guest", requests.Session())
    guest.session.headers.update({"User-Agent": UA})
    browse_pages(
        guest,
        [
            "/public/",
            "/public/events/",
            "/public/prayers/",
            "/public/sermons/",
            "/public/announcements/",
            "/login",
            "/login?tab=register",
        ],
    )
    all_results.extend(guest.results)

    # --- Register test accounts (as guest) ---
    reg = SimSession("register", requests.Session())
    reg.session.headers.update({"User-Agent": UA})
    for key in ("visitor", "member", "pastor"):
        ok = register_account(reg, key)
        print(f"Register {ACCOUNTS[key]['username']}: {'ok' if ok else 'already exists or failed'}")
    all_results.extend(reg.results)

    # Pending visitor cannot login
    visitor_sess = SimSession("visitor", requests.Session())
    visitor_sess.session.headers.update({"User-Agent": UA})
    login(visitor_sess, ACCOUNTS["visitor"]["username"], TEST_PASSWORD)
    visitor_sess.get("/dashboard")
    all_results.extend(visitor_sess.results)

    # --- Admin ---
    admin = SimSession("admin", requests.Session())
    admin.session.headers.update({"User-Agent": UA})
    if not login(admin, ADMIN_USER, ADMIN_PASS):
        print("ERROR: Admin login failed — is password TestAdmin2026! ?")
        print_report(all_results + admin.results)
        return 1

    admin_approve_user(admin, ACCOUNTS["member"]["username"], "Member")
    admin_approve_user(admin, ACCOUNTS["pastor"]["username"], "Staff", pastoral=True)

    browse_pages(
        admin,
        [
            "/dashboard",
            "/members/directory",
            "/settings/general",
            "/settings/",
            "/groups/",
            "/announcements/",
        ],
    )
    all_results.extend(admin.results)
    logout(admin)

    # --- Member ---
    member = SimSession("member", requests.Session())
    member.session.headers.update({"User-Agent": UA})
    login(member, ACCOUNTS["member"]["username"], TEST_PASSWORD)
    browse_pages(
        member,
        [
            "/dashboard",
            "/prayers/",
            "/prayers/add",
            "/events/",
            "/profile/",
            "/dreams/",
            "/announcements/",
        ],
    )
    # Submit a prayer
    r = member.get("/prayers/add")
    csrf = extract_csrf(r.text)
    if csrf:
        member.post(
            "/prayers/add",
            {
                "csrf_token": csrf,
                "title": "Sim Test Prayer",
                "description": "Please pray for our simulation test.",
                "visibility": "public",
            },
            referer="/prayers/add",
        )
    all_results.extend(member.results)
    logout(member)

    # --- Pastor ---
    pastor = SimSession("pastor", requests.Session())
    pastor.session.headers.update({"User-Agent": UA})
    login(pastor, ACCOUNTS["pastor"]["username"], TEST_PASSWORD)
    browse_pages(
        pastor,
        [
            "/dashboard",
            "/pastoral/",
            "/pastoral/care/",
            "/pastoral/care/new",
            "/pastoral/illustrations/library",
            "/pastoral/sermons/",
            "/pastoral/planning/",
            "/pastoral/bible/search",
        ],
    )
    r = pastor.get("/pastoral/care/new")
    csrf = extract_csrf(r.text)
    if csrf:
        pastor.post(
            "/pastoral/care/new",
            {
                "csrf_token": csrf,
                "member_id": "1",
                "request_type": "prayer",
                "urgency": "normal",
                "description": "Simulation pastoral care request.",
                "is_confidential": "on",
            },
            referer="/pastoral/care/new",
        )
    all_results.extend(pastor.results)
    logout(pastor)

    fail_count = print_report(all_results)
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())