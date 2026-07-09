🗺️ The Detailed Documentation Roadmap
Section 1: The Vision & Core Mission
The "What" and "Why": Creating a unified digital ecosystem for spiritual and logistical church health.

The "No-Bloat" Architecture: Logic behind the stack (Flask/MariaDB/Vanilla JS).

Section 2: The Gathering Place (The Community Hub)
The public/ ecosystem: How dreams, prophecies, and prayers are shared.

The Public Dashboard: Announcements and community engagement.

Section 3: The Spiritual Intelligence Modules
The Vault: Archiving illustrations, testimonies, and spiritual insights.

Dreams & Prophecies: Structured tracking of spiritual revelations.

The Prayer Engine: Managing requests and communal intercession.

Section 4: The Pastoral Command Center
The Sermon Lifecycle: From the Sectional Editor to Document Export.

Podium Mode: The high-performance teleprompter and preacher UX.

Pastoral Care: Tracking and responding to member needs.

Section 5: Administrative & Financial Stewardship
Membership & Families: Managing the directory and complex household relations.

Financial Integrity: Donations, Recurring Bills, and automated reporting.

Inventory & Assets: Tracking physical resources and locations.

Section 6: Operations & Logistics
The Kiosk System: Secure attendance, check-ins, and session security.

The Ticket System: Internal task management and manager assignments.

Events & Planning: Scheduling and service assignment logic.

Section 7: Infrastructure, Security & AI
BuildDB: The automated schema sync logic.

The "Shield": Audit logs (log_change), IP banning, and hashed security.

Check the docs for more details on sections

## Local Development

To run locally (recommended):

```bash
./myvineos
```

- Creates `.venv` (Python virtualenv) if missing
- Installs dependencies from `requirements.txt`
- Starts MariaDB via `docker compose` (see `docker-compose.yml`)
- Waits for DB readiness
- Launches dev server on http://127.0.0.1:5001 (override with HOST/PORT env)

First run: you will be prompted to register the initial Owner.

### Fresh reset (wipe DB)

```bash
./myvineos --fresh
# or
./myvineos reset
```

This destroys the Docker volume for a clean slate.

### Requirements
- Python 3 + venv
- Docker + Docker Compose (for the dev database; this project uses host port 3308 to coexist with veilbreak on 3306 and driverapp on 3307)
- On first run, the script will guide you.

For production hosting (Passenger / WSGI), use the existing `main.py` + `wsgi.py` / `passenger_wsgi.py` setup. The launcher is dev-only.

### Environment
The script forces dev DB credentials (matching `docker-compose.yml`) via `export` so your existing `.env` (hosting values) won't interfere.

Edit `.env` for custom hosting creds if needed (the app loads it but env vars take precedence for the launcher).

### Notes
- BuildDB runs automatically on startup (see `app/builddb/` and `app/__init__.py`).
- PoweredByTop security wrapper is always active.
- For full local MariaDB without Docker, set the MYSQL_* env vars and skip the docker parts.
