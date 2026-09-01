#!/usr/bin/env python3
"""Capture FRESH viewport screenshots of the running MyVineOS app for GitHub marketing.

Requires: app at BASE (default http://127.0.0.1:5001), playwright installed.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5001"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "marketing" / "screenshots"
GALLERY = OUT / "gallery"
MOBILE = OUT / "mobile"
ADS = OUT / "best_for_ads"

# Demo accounts from local seed / sim tools
ADMIN = ("admin", "TestAdmin2026!")
PASTOR = ("sim_pastor", "SimTest2026!")

DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}


def clean_dirs():
    for d in (GALLERY, MOBILE, ADS):
        d.mkdir(parents=True, exist_ok=True)
        for p in d.glob("*.jpg"):
            p.unlink()
        for p in d.glob("*.png"):
            p.unlink()


def shot(page, path: Path, full_page: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), type="jpeg", quality=88, full_page=full_page)
    print(f"  saved {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


def login(page, username: str, password: str) -> bool:
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(500)
    form = page.locator("#login-form")
    form.wait_for(state="visible", timeout=10000)
    form.locator('input[name="username"]').fill(username)
    form.locator('input[name="password"]').fill(password)
    with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
        form.locator('button[type="submit"]').click()
    page.wait_for_timeout(800)
    ok = "/login" not in page.url
    if not ok:
        # one more try after full page reload (fresh CSRF)
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.wait_for_timeout(500)
        form = page.locator("#login-form")
        form.locator('input[name="username"]').fill(username)
        form.locator('input[name="password"]').fill(password)
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
            form.locator('button[type="submit"]').click()
        page.wait_for_timeout(800)
        ok = "/login" not in page.url
    print(f"  login {username}: {'OK' if ok else 'FAIL'} url={page.url}")
    return ok


def safe_goto(page, path: str, wait_ms: int = 800):
    url = path if path.startswith("http") else f"{BASE}{path}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait_ms)
        return True
    except Exception as e:
        print(f"  skip {path}: {e}")
        return False


def capture_guest(page):
    print("=== GUEST (public) ===")
    shots = [
        ("/login", "01_login.jpg"),
        ("/login?tab=register", "02_register.jpg"),
        ("/public/", "03_public_welcome.jpg"),
        ("/public/events", "04_public_events.jpg"),
        ("/public/prayers", "05_public_prayers.jpg"),
        ("/public/sermons", "06_public_sermons.jpg"),
        ("/public/announcements", "07_public_announcements.jpg"),
        ("/public/prophecies", "08_public_prophecies.jpg"),
        ("/public/dreams", "09_public_dreams.jpg"),
        ("/bible", "09b_public_bible.jpg"),
    ]
    for path, name in shots:
        if safe_goto(page, path):
            # click register tab if needed
            if "register" in name:
                try:
                    page.evaluate("typeof showForm==='function' && showForm('register')")
                    page.wait_for_timeout(300)
                except Exception:
                    pass
            shot(page, GALLERY / name)


def capture_logged_in(page, prefix_start: int = 10):
    print("=== LOGGED-IN (admin) ===")
    routes = [
        ("/dashboard", "10_private_dashboard.jpg"),
        ("/members/directory", "11_members_directory.jpg"),
        ("/events", "12_events_dashboard.jpg"),
        ("/prayers", "13_prayers_dashboard.jpg"),
        ("/sermons", "14_sermons_dashboard.jpg"),
        ("/announcements", "15_announcements.jpg"),
        ("/attendance", "16_attendance.jpg"),
        ("/donations", "17_donations.jpg"),
        ("/bills", "18_bills.jpg"),
        ("/inventory", "19_inventory.jpg"),
        ("/support-tickets", "20_tickets.jpg"),
        ("/groups", "21_groups.jpg"),
        ("/profile", "22_profile.jpg"),
        ("/settings/general", "23_settings.jpg"),
        ("/pastoral", "24_pastoral_hub.jpg"),
        ("/pastoral/sermons", "25_pastoral_sermons.jpg"),
        ("/pastoral/podium", "26_podium.jpg"),
        ("/pastoral/planning", "27_service_planning.jpg"),
        ("/pastoral/bible", "28_bible_study.jpg"),
        ("/pastoral/care", "29_pastoral_care.jpg"),
        ("/pastoral/vault", "30_pastoral_vault.jpg"),
        ("/pastoral/illustrations", "31_illustrations.jpg"),
        ("/worship", "32_worship.jpg"),
        ("/the_gathering", "33_gathering_manager.jpg"),
        ("/dreams", "34_dreams_private.jpg"),
        ("/prophecies", "35_prophecies_private.jpg"),
        ("/help", "36_help.jpg"),
        ("/public/community", "37_community_feed.jpg"),
    ]
    for path, name in routes:
        if safe_goto(page, path):
            # dismiss security flash if any
            shot(page, GALLERY / name)


def capture_mobile(page):
    print("=== MOBILE ===")
    page.set_viewport_size(PHONE)
    routes = [
        ("/dashboard", "01_dashboard.jpg"),
        ("/pastoral", "02_pastoral.jpg"),
        ("/pastoral/bible", "03_bible.jpg"),
        ("/public/", "04_public.jpg"),
        ("/events", "05_events.jpg"),
        ("/prayers", "06_prayers.jpg"),
        ("/worship", "07_worship.jpg"),
    ]
    for path, name in routes:
        if safe_goto(page, path):
            shot(page, MOBILE / name)
    page.set_viewport_size(DESKTOP)


def main():
    clean_dirs()
    print(f"Capturing from {BASE}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=DESKTOP,
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            device_scale_factor=1,
        )
        page = context.new_page()
        page.set_default_timeout(45000)

        capture_guest(page)

        # Prefer Owner for full UI; fall back to pastor
        logged = login(page, *ADMIN)
        if not logged:
            context.clear_cookies()
            logged = login(page, *PASTOR)
        if not logged:
            print("ERROR: could not log in — guest shots only")
        else:
            capture_logged_in(page)
            capture_mobile(page)

        browser.close()

    # Mirror gallery → best_for_ads
    for p in sorted(GALLERY.glob("*.jpg")):
        dest = ADS / p.name
        dest.write_bytes(p.read_bytes())

    (OUT / "README.txt").write_text(
        "MyVineOS FRESH screenshots — captured live from local app\n"
        f"Source: {BASE}\n"
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        "Demo accounts used (local DB only). Not production passwords.\n"
        "Folders: gallery/ (full), best_for_ads/ (same), mobile/ (phone frames)\n",
        encoding="utf-8",
    )
    n = len(list(GALLERY.glob("*.jpg")))
    m = len(list(MOBILE.glob("*.jpg")))
    print(f"DONE: {n} gallery + {m} mobile shots")


if __name__ == "__main__":
    main()
