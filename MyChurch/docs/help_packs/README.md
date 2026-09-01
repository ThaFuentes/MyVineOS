# MyVineChurch Help Packs

Portable, enterprise Help content for any install.

## Format

- **JSON**, UTF-8  
- **`format`: `myvine_help_v1`**  
- Categories and articles keyed by **`slug`**  
- Articles include **`category_slug`** (not only numeric `category_id`)

## Files

| File | Purpose |
|------|---------|
| `myvine_enterprise_help_v1.json` | Full operator library (pastoral, worship, attendance, accounting+bills, study courses, church apps, tickets, campuses, …) |

## Import in the UI

1. Sign in as Owner/Admin (manage help).  
2. **Help → Manage Help Content**.  
3. **Upload / import pack** → choose the JSON file.  

## Seed from the repo

```bash
cd /path/to/myvinechurch.online
.venv/bin/python scripts/seed_enterprise_help.py
```

Writes/updates `myvine_enterprise_help_v1.json` and merges into the database.

## Export for git

1. Help → Manage → **Download help pack (JSON)**.  
2. Save under `docs/help_packs/` and open a PR.  
3. Other environments pull git and import/seed.

## Design rules

- Merge-only import (never wipe the whole library).  
- Prefer clear numbered steps and exact menu labels.  
- Staff-only topics may set `permission_key`.  
- Study **courses** are built in Curriculum Studio; Help teaches *how* to build and take them.
