# MyVineOS

**Free, open-source church website & management platform — for everyone.**

MyVineOS is software any church, ministry, or community can **download, run, host, and customize** at no cost. No SaaS lock-in, no seat licenses, no “premium tier” for core features. You own your data and your server.

Built for spiritual life *and* day-to-day operations: public community pages, pastoral tools, membership, events, giving, and more — on a simple **Flask + MariaDB + vanilla JS** stack (no heavy frontend framework required).

> **License:** Free to use, study, share, and improve under open-source terms.  
> **Who it’s for:** Churches of any size, tech volunteers, developers, and anyone who wants a self-hosted church site without renting a black-box product.

---

## Quick start (local)

```bash
./myvineos
```

- Creates `.venv` if missing  
- Installs from `requirements.txt`  
- Starts MariaDB via Docker Compose  
- Serves the app at http://127.0.0.1:5001  

First run walks you through creating the initial Owner account.

```bash
cp .env.example .env   # then set SECRET_KEY / FERNET_KEY for anything beyond local toys
./myvineos --fresh     # wipe DB volume and start clean (dev only)
```

**Requirements:** Python 3.10+, Docker + Docker Compose (dev DB on host port **3308**).

Production: use `main.py` / `wsgi.py` / `passenger_wsgi.py` on your host. The `./myvineos` launcher is for development.

---

## What you get

| Area | Highlights |
|------|------------|
| **Public / community** | Announcements, dreams, prophecies, prayers, sermons, events feed |
| **The Gathering Place** | Manager tools for community content & moderation |
| **Pastoral** | Sermon editor, podium mode, care, vault, planning |
| **Admin** | Members, groups, donations, bills, inventory, tickets |
| **Ops** | Attendance kiosk, events, settings, help, security tooling |

Stack philosophy: **no bloat** — readable Python, SQL-backed MariaDB, and plain static assets you can edit without a Node build pipeline.

---

## Documentation roadmap

**1. Vision & core mission** — Unified digital ecosystem for spiritual and logistical church health; why Flask/MariaDB/vanilla JS.

**2. The Gathering Place** — Public ecosystem (dreams, prophecies, prayers) and community dashboard.

**3. Spiritual modules** — Vault, dreams & prophecies, prayer engine.

**4. Pastoral command center** — Sermon lifecycle, podium mode, pastoral care.

**5. Stewardship** — Membership & families, donations, recurring bills, inventory.

**6. Operations** — Kiosk attendance, tickets, events & service planning.

**7. Infrastructure & security** — BuildDB schema sync, audit logs, IP controls, PoweredByTop hardening.

---

## Contributing & using freely

- **Use it** for your church — fork, brand it, deploy it.  
- **Improve it** — PRs and issues welcome.  
- **Share it** — help other ministries avoid expensive closed platforms.

Please don’t commit secrets. Copy `.env.example` → `.env`, keep keys and DB passwords out of git (see `.gitignore`).

---

## Project links

- **Repository:** https://github.com/ThaFuentes/MyVineOS  
- **Issues:** https://github.com/ThaFuentes/MyVineOS/issues  

---

### Notes for developers

- BuildDB runs on startup (`app/builddb/`, `app/__init__.py`).  
- Local launcher exports dev DB settings so hosting `.env` values don’t break Docker MariaDB.  
- For MariaDB without Docker, set `MYSQL_*` yourself and skip Compose.  
- `poweredbytop/` is a vendored security/session layer shipped with the project.
