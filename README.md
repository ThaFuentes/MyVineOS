# MyVineOS

### A free, open church operating system — website, community, pastoral tools, and admin in one place

**Anyone can download it.** Churches, small groups, tech volunteers, and developers are welcome. There is no paid “core” tier, no seat license for members, and no vendor lock-in. You run it on **your** server (or a host you choose), with **your** data, under **your** control.

MyVineOS is a full-stack platform built like serious software for real ministry work: a public-facing church site, member tools, pastoral planning, worship, giving records, bills, inventory, attendance, and more — modular Flask backend, MariaDB, and a mobile-friendly web UI.

> **Who it’s for:** Any church that wants one system instead of five disconnected apps.  
> **What you get:** Public pages **and** private operations — not just a brochure site.  
> **How you get it:** Clone this repo, run the local launcher, or deploy with standard Python/WSGI hosting.

---

## Why MyVineOS

| Need | What MyVineOS offers |
|------|----------------------|
| **All-in-one** | Public portal + members + pastoral + worship + finance ops + community moderation |
| **Ownership** | Full source code — fork it, brand it, host it, audit it |
| **Cost control** | Free to download and run; you only pay for hosting if you choose hosted infrastructure |
| **Security-minded** | Encryption for sensitive credentials, CSRF, rate limits, RBAC, optional 2FA, re-auth for vault reveals, secure cookies & headers |
| **Practical stack** | Python **Flask**, **MariaDB/MySQL**, vanilla JS/CSS — no mandatory Node frontend build |
| **Maintainable** | Clear `app/routes`, `app/models`, `app/templates`, and `builddb` schema modules |

If you only need a static webpage, this is more than that. If you need a **church operating system** — from the welcome page visitors see to the podium and bills your staff use — this is built for that.

---

## Quick start (local)

Anyone with a normal developer laptop can try it:

```bash
git clone https://github.com/ThaFuentes/MyVineOS.git
cd MyVineOS
./myvineos
```

What `./myvineos` does:

1. Creates a Python virtualenv if needed  
2. Installs `requirements.txt`  
3. Starts **MariaDB** via Docker Compose (dev)  
4. Serves the app (default **http://127.0.0.1:5001**)

First visit walks you through creating the initial **Owner** account.

```bash
cp .env.example .env   # set SECRET_KEY and FERNET_KEY for real use
./myvineos --fresh     # wipe the dev DB volume and start clean (dev only)
```

**Requirements:** Python **3.10+** (developed on 3.12), Docker + Docker Compose for the local DB (host port **3308** → container 3306).

**Production:** use `main.py` / `wsgi.py` / `passenger_wsgi.py` on your host. Point `MYSQL_*`, `SECRET_KEY`, and `FERNET_KEY` at real values. The `./myvineos` script is the **development** launcher.

---

## What is included (feature map)

This is software that ships **modules you can turn on for real church life** — public website surfaces and private tools together.

### Public website & community

- Welcome / church overview (services, events, contact)  
- Public **events**, **sermons**, **announcements**, **prayers**, **prophecies**, **dreams**  
- Community feed and guest-friendly navigation  
- Display themes (theme + text size) available to visitors and members  
- Comments / contributions where enabled, with moderation paths for managers  

### Members, groups & attendance

- Member directory and profiles  
- Groups, roles, pending registration workflows  
- Attendance tools including **kiosk** sign-in flows  
- Email roster and bulk communication hooks  
- Security lockouts / admin moderation helpers  

### Dashboard & day-to-day UX

- Role-aware private dashboard tiles  
- Birthdays, prayers, announcements, upcoming events widgets  
- Personal display preferences (theme, page text, Bible text size)  
- Mobile-first shell (top bar + bottom nav on phones)  

### Pastoral command center

- Sermon builder, sections, export tooling (**DOCX** / package exports via project libraries)  
- Illustrations library  
- Service planning (templates, roles, times, overrides)  
- **Podium mode** for live preaching  
- Care dashboard and pastoral follow-up flows  
- Pastoral vault library for notes and shared pastoral content  

### Worship team

- Weekly defaults and date overrides  
- Song library with sections and play order  
- Setlists, notes, public/prompter-style links where configured  
- Import/export oriented workflows for plans  

### Bible & study

- Scripture viewing and navigation  
- **Strong’s** lexicon / occurrence data support (seed + import paths in the Bible models)  
- Member study surfaces  

### Donations, bills & inventory

- Donations dashboard, records, export-oriented reporting  
- Online giving **settings** (options, copy, images, enable/disable) — configure how you present giving; wire your processor links as your church uses them  
- Recurring **bills** dashboard, assignment, reminders  
- **Encrypted bill credentials** (utility logins, etc.) with **password re-auth** before reveal  
- Inventory catalog, receive/scan style workflows, dashboards  

### Events, tickets & operations

- Event management, contributions / potluck-style participation  
- Tickets / support ticket modules  
- The Gathering Place manager area for community moderation  
- Settings: timezone, email, notifications, censored words, custom modules, AI-related settings hooks  

### Auth & admin

- Login / register, email verification flows (configurable)  
- Optional **TOTP 2FA** (`pyotp`)  
- Roles such as Owner / Admin / Staff / Member (plus pending/banned workflows)  
- Permission helpers and group-aware gates across modules  
- Audit-style **change logging** for important actions  

---

## Security (honest overview)

Open source is not “insecure by default.” Security comes from design, operation, and review. MyVineOS includes **real controls in the codebase**, and the source is fully auditable by your team or a contractor.

### Built into the project today

| Control | What it means in MyVineOS |
|---------|---------------------------|
| **Password hashing** | Passwords are hashed with Werkzeug’s secure password helpers (not stored as plain text). |
| **Optional 2FA** | TOTP second factor on login when enabled for a user. |
| **CSRF protection** | Form/state-changing requests checked by the PoweredByTop security pipeline; signed tokens for resilience. |
| **Request pipeline** | Rate limiting, reputation-oriented blocking, HTTPS enforcement options, security event logging (`poweredbytop/`). |
| **Secure cookies & headers** | HttpOnly / SameSite session cookies; headers such as `X-Content-Type-Options`, `X-Frame-Options`, CSP baseline, HSTS when HTTPS is on. |
| **Credential encryption** | Sensitive stored credentials (e.g. bill vault fields, related secrets) use **Fernet** (`cryptography`) with keys from environment / key material — not plain text in the DB. |
| **Re-authentication** | Revealing encrypted bill credentials requires the user to re-enter their password; access is intentional, not one-click. |
| **RBAC & permissions** | Role checks and permission/group helpers gate admin and ministry tools. |
| **Parameterized SQL** | PyMySQL queries use parameter binding (`%s`) to reduce SQL injection risk. |
| **HTML sanitization** | Bleach used where rich/community content needs cleaning. |
| **Schema on deploy** | `builddb` modules create/update tables on startup so installs stay consistent. |

### What this is *not* claiming

To stay honest:

- **One install ≈ one church database.** This is self-hosted software you deploy for your ministry. It is **not** a SaaS multi-tenant product with automatic cross-church isolation via `church_id` rows. Isolation between churches = separate deployments (or separate DBs/hosts you configure).  
- **Not a certified PCI provider.** Donation *records* and online-giving *configuration* exist; card processing is not “MyVineOS is a bank.” Use a proper processor and their compliance model if you take cards online.  
- **Not a substitute for ops discipline.** Strong keys, HTTPS, updates, backups, and least-privilege DB users are **your** production responsibilities.  
- **Open source transparency ≠ automatic pentest certificate.** Anyone can read the code (including attackers and defenders). That is a feature for trust; you still should harden and review for production.

### Recommended hardening for production (you / your host)

These are best practices — do them when going live:

1. Set strong unique `SECRET_KEY` and `FERNET_KEY` (never commit `.env`).  
2. Serve only over **HTTPS**; keep `DEBUG_MODE=false`.  
3. Use a dedicated MariaDB user with least privilege.  
4. Enable **2FA** for Owner/Admin accounts.  
5. Encrypted offsite **backups** and a tested restore.  
6. Keep OS packages and `requirements.txt` dependencies updated.  
7. Optional: WAF / reverse proxy rate limits, monitoring (e.g. error tracking), and a periodic security review.  

---

## Architecture (for tech volunteers)

```
MyVineOS/
├── app/                 # Flask application
│   ├── routes/          # Feature modules (public, pastoral, worship, …)
│   ├── models/          # Data access
│   ├── templates/       # Jinja HTML
│   ├── builddb/         # Schema bootstrap / migrations-style builders
│   └── utils/           # Email, permissions, crypto helpers, prefs
├── poweredbytop/        # Vendored security/session/rate-limit layer
├── static/              # CSS, JS, images (no required Node build)
├── main.py / wsgi.py / passenger_wsgi.py
├── docker-compose.yml   # Dev MariaDB
├── requirements.txt
└── myvineos             # One-command local launcher
```

**Stack:** Flask 3 · PyMySQL · MariaDB · cryptography · pyotp · python-docx · bleach · python-dotenv  

---

## Download, use, share

1. **Download** from GitHub: https://github.com/ThaFuentes/MyVineOS  
2. **Run** locally with `./myvineos` or deploy to any Python-friendly host with MariaDB.  
3. **Customize** branding, themes, modules, and workflows in source — it is your install.  
4. **Contribute** issues and pull requests if you improve something that helps other churches.  

Please **never** commit secrets (`.env`, production keys, real member data dumps). Use `.env.example` as the template.

---

## Practical adoption path

1. **Pilot** — one campus / one ministry team for a few weeks.  
2. **Secure** — production keys, HTTPS, 2FA for admins, backups.  
3. **Onboard** — Owner setup, church settings, first events/services, first members.  
4. **Grow** — enable worship, pastoral, bills, inventory as you need them.  
5. **Share** — if MyVineOS helps you, tell another church they can run the same stack for free.

---

## Project links

| | |
|--|--|
| **Repository** | https://github.com/ThaFuentes/MyVineOS |
| **Issues** | https://github.com/ThaFuentes/MyVineOS/issues |

---

### A note of encouragement

You do not need a Silicon Valley budget to run a serious church platform. MyVineOS is written to be **downloadable, runnable, and ownable** — a full operating system for ministry work and public presence, with security controls you can read in the source. Host it carefully, keep your keys safe, and use it to serve people.

*Built for churches. Free to download. Yours to run.*
