# AGENTS.md — MyChurch sandbox (community layer)

This folder is a **copy** of MyVineOS used to build the MySpace-y community layer
without touching live ops at `~/pyprojects/myvinechurch.online`.

| This tree | Live ops (do not edit for this work) |
|-----------|--------------------------------------|
| `myvinechurch.online/MyChurch/` | `myvinechurch.online/` (parent) |
| Dev URL: `:5002` on `0.0.0.0` (127.0.0.1 + Tailscale) | Live / parent launcher: :5001 |
| Docker DB: `mychurch-sandbox-db` on **3311** | Parent DB: `myvinechurch-db` on **3308** |
| Database name: `mychurch_sandbox` | `church_management` |
| Session cookie: `mychurch_sandbox_session` | default Flask session |

**Do not** edit parent `app/`, `static/`, `passenger_wsgi.py`, `.env`, or HostM deploy files for community-layer work.

**Do not** copy this sandbox’s `.env` from the parent (production secrets).

**Do not** deploy this folder to HostM until the operator says to merge back.

Run: `./myvineos` from **this** directory.

Product intent: **main church page** ≠ **branch page** ≠ **Feed** ≠ **member page**.

- Main church page is always the org. If branches exist, a member’s Home is **their branch**, but they can still open the main church, other branches, and follow anyone.
- Feed (Community) is the newspaper: people you follow first, then your branch, then the rest of the church. Other people’s posts live here.
- Member page is MySpace-y: what they created, linked, and follow — not the church-wide feed. Church strip on a member page is **the page owner’s** campus (Tim’s time, not yours).
