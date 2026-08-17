# AGENTS.md — MyVineOS self-host (myvinechurch.online)

## Product boundary (mandatory)

| This product | NOT this product |
|--------------|------------------|
| **Self-host / open-source MyVineOS** | **MyVineOS Cloud** multi-tenant SaaS |
| Folder: `~/pyprojects/myvinechurch.online` | Folder: `~/pyprojects/MyVineOSCloud` |
| Repo: public `ThaFuentes/MyVineOS` | Repo: private `ThaFuentes/MyVineOSCloud` |
| **One church per install** | **Many churches**, `church_id` isolation |
| Typical host: myvinechurch.online | Host: **myvineos.poweredby.top** |

**Never** push this tree as Cloud. **Never** overwrite Cloud’s `tenant.py` / `platform/*` with this app.  
If the user says “Cloud” or “myvineos.poweredby.top”, work in **MyVineOSCloud** and read that folder’s `AGENTS.md`.

## Security note

Login-safe CSRF lives in `poweredbytop/core/security.py`. Device-first hard blocks may be added; **do not** replace Vine CSRF with Aegis-only CSRF (breaks mobile login).
