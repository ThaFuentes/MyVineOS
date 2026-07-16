# Enterprise Help Pack — detailed guides for every major MyVineChurch area.
# Portable: export as JSON, commit under docs/help_packs/, import on any install.

from __future__ import annotations

from app.models.help_pack import FORMAT_ID, PACK_VERSION


def _a(slug, title, summary, category_slug, body_md, sort_order=10, permission_key=None):
    return {
        "slug": slug,
        "title": title,
        "summary": summary,
        "category_slug": category_slug,
        "body_md": body_md.strip(),
        "sort_order": sort_order,
        "is_published": 1,
        "permission_key": permission_key,
    }


def _c(slug, name, description, sort_order):
    return {
        "slug": slug,
        "name": name,
        "description": description,
        "sort_order": sort_order,
        "is_published": 1,
    }


CATEGORIES = [
    _c("getting-started", "Getting Started", "First login, navigation, themes, and Help packs.", 5),
    _c("community", "Community", "Events, prayers, sermons, announcements, dreams, prophecies, Bible.", 15),
    _c("church-office", "Church Office", "Members, donations, inventory, groups, office tools.", 25),
    _c("attendance-kids", "Attendance & Kids", "Attendance sessions, reports, self check-in, child check-in.", 35),
    _c("finance", "Finance & Accounting", "Bills, accounting, donations, bill reminders, and how they connect.", 45),
    _c("volunteers-tickets", "Serving & Tickets", "Volunteer schedule, My Serving, support tickets, ticket manager.", 55),
    _c("worship", "Worship Team", "Songs, setlists, plans, band and display tools.", 65),
    _c("pastoral", "Pastoral Area", "Sermons, Bible study, illustrations, planning, vault, care.", 75),
    _c("study-courses", "Study Courses", "Curriculum Studio and member study paths with quizzes and media.", 85),
    _c("church-apps", "Church Apps", "Bus routes, youth group, equipment, ministry calendar, custom apps.", 95),
    _c("admin-settings", "Admin & Settings", "Modules, campuses/branches, security, communications, AI.", 105),
    _c("account-login", "Account & Login", "Register, login, password recovery, profile.", 115),
]


def _articles():
    return [
        # ── Getting started ─────────────────────────────────────────────
        _a(
            "welcome-enterprise-help",
            "Welcome — Enterprise Help Center",
            "How Help is organized, how to search and pin guides, and how leaders share packs.",
            "getting-started",
            """
## What this Help Center is

This is your church's **instruction library** for MyVineChurch / MyVineOS. Guides are written for real operators: greeters, treasurers, pastors, worship leaders, and admins.

## How to find answers

1. Open **My Stuff → Help** (or **Help** on the dashboard).
2. Use **Browse** to open a category folder.
3. Use **Search** with plain words: `bill`, `setlist`, `course`, `campus`, `kiosk`.
4. **Pin** guides you use weekly so they stay under the **Pinned** tab.

## Who can edit Help

Users with **manage help** permission (typically Owner/Admin) open **Manage Help Content** to:

- Add **categories** (folders)
- Write **guides** in Markdown (headings, lists, bold, code, callouts)
- **Download backup (JSON)** and **Re-upload / import** packs
- Optionally restrict a guide with a **permission key** (staff-only topics)

## Sharing Help with other churches or git

Help packs use format **`myvine_help_v1`** and are **slug-based** (not hard-coded database IDs), so they work on any install:

1. **Download** from Help → Manage → Download backup (JSON).
2. Commit the file under `docs/help_packs/` in git, or email/Slack it.
3. On another site: Help → Manage → choose file → **Re-upload / import**.
4. Import **merges by slug** (updates existing guides, adds new ones). It does **not** delete local-only guides.

> Tip: After major product updates, re-import the official enterprise pack so every church gets the new guides without rebuilding them by hand.
""",
            1,
        ),
        _a(
            "help-packs-download-upload-git",
            "Help packs: download, upload, and git workflow",
            "Enterprise sharing of Help content between campuses, environments, and churches.",
            "getting-started",
            """
## Portable pack format

File type: JSON  
Format field: `myvine_help_v1`

Each category and guide has a stable **`slug`** (example: `pastoral-sermon-library`). Articles also include **`category_slug`** so categories re-link correctly on another database.

## Download (export)

1. Sign in as Owner/Admin (or user with manage help).
2. **Help → Manage Help Content**.
3. Click **Download backup (JSON)**.
4. Save as e.g. `help_export_YYYY-MM-DD.json`.

## Upload (import)

1. **Help → Manage**.
2. Choose a `.json` pack file.
3. Click **Re-upload / import**.
4. Review the success counts: categories/guides created vs updated.

### What import does

- Creates missing categories and articles by slug
- Updates title, summary, body, sort order, publish flag, permission key
- Re-maps articles to categories via `category_slug`
- **Never** wipes the whole Help library

### What import does not do

- Does not delete guides that exist only on your site
- Does not overwrite file uploads outside Help (images live in their own modules)

## Git workflow (recommended)

```
docs/help_packs/
  myvine_enterprise_help_v1.json
  README.md
```

1. Export or use the official pack in the repo.
2. PR/review changes to guide wording like any docs change.
3. Deploy code, then import the pack on each environment (staging, production).
4. Or run the seed script on deploy if you automate content loads.

## Quality checklist before sharing a pack

- Every article has a unique slug and a real category_slug
- Bodies use clear **numbered steps** and exact menu names
- Staff-only guides set `permission_key` when needed
- Spot-check import on a staging site first
""",
            2,
        ),
        _a(
            "navigation-dashboard-themes",
            "Navigation, dashboard tiles, and display themes",
            "Desktop menus, mobile sheets, Modules toggles, and church-wide theme.",
            "getting-started",
            """
## Desktop vs phone

- **Desktop:** top nav groups — Community, Church Office, Ministry, My Stuff.
- **Phone:** bottom bar — Home, Community, Office, My Stuff, More. Tap a tab to open a sheet of links.

## Dashboard tiles

Home shows **tiles** for modules you can use, based on:

1. **Modules & Apps** toggles (Owner/Admin: Settings → Modules & Apps)
2. Your **role / permissions** (example: inventory managers only)
3. Whether the feature is installed

Tiles are shortcuts. Full lists stay in the menus.

## Church default theme vs personal theme

- **Settings → Church & General → Default display theme** sets the look for **visitors** and anyone following church default.
- **Display** (palette icon) lets each person pick their own theme or **Church default**.
- Logged-in personal themes save to the account; guests save for the browser session only.

## If something is missing from menus

1. Confirm **Settings → Modules & Apps** has the module enabled.
2. Confirm your user has the right **group permission**.
3. Hard-refresh the browser (Ctrl+Shift+R).
""",
            3,
        ),

        # ── Community ───────────────────────────────────────────────────
        _a(
            "community-overview",
            "Community content overview",
            "Events, prayers, sermons, announcements, dreams, prophecies, and Bible study.",
            "community",
            """
## What Community covers

Shared church life content members and (when published publicly) visitors can use:

| Area | Typical use |
|------|-------------|
| Events | Services, potlucks, calendar items |
| Prayers | Prayer wall and responses |
| Sermons | Public sermon library |
| Announcements | Bulletin-style notices |
| Dreams / Prophecies | Optional sharing modules |
| Bible | In-app reader for members |

## Visibility

Most posts support visibility levels (public / members / private as configured). Public pages live under `/public/...` when enabled.

## Good practice

- Write clear titles and dates for events.
- Use announcements for short, time-sensitive news.
- Keep pastoral counseling content in **Pastoral** tools, not the public prayer wall.
""",
            10,
        ),

        # ── Church office ───────────────────────────────────────────────
        _a(
            "members-directory",
            "Members directory and registrations",
            "Find people, review pending signups, and manage directory access.",
            "church-office",
            """
## Open the directory

**Church Office → Members** (permission-gated).

## Everyday tasks

1. Search by name, email, phone, or username.
2. Open a profile to view contact details and admin tools (if allowed).
3. Review **pending registrations** from the dashboard banner when people sign up.

## Roles

- **Owner / Admin** — full user management
- Staff with **view/manage members** permissions — directory as granted
- Members — usually cannot open the full directory

## Multi-campus

When multi-campus is on, the directory can filter by the campus selected in the top bar. Link members to campuses under **Settings → Campuses / Branches**.
""",
            10,
        ),
        _a(
            "inventory-kits-stock",
            "Inventory: catalog, kits/sets, and stock moves",
            "Build lasting inventory with kits, receive stock, and audit.",
            "church-office",
            """
## Open Inventory

**Church Office → Inventory** (manage inventory permission).

## Catalog

1. Create **items** (supplies, equipment).
2. Optionally mark an item as a **kit / set**.
3. On a kit, add **components** with quantity per kit.
4. **Deploy kit** consumes component stock via FIFO.

## Stock operations

- **Receive** stock with optional batch/lot and expiration
- **Transfer / move** between locations
- **Audit** and barcode scan tools when enabled

## Tips

- Name items the way greeters and facilities staff say them.
- Use locations (closet, kitchen, AV booth) consistently.
- Kits are for “Sunday hospitality pack” style bundles, not accounting assets.
""",
            20,
        ),

        # ── Attendance & kids ───────────────────────────────────────────
        _a(
            "attendance-full-guide",
            "Attendance: sessions, kiosk, self check-in, and reports",
            "Full operator guide for attendance at every scale.",
            "attendance-kids",
            """
## Where to go

| Task | Path |
|------|------|
| Staff dashboard | **Church Office → Attendance** |
| Full reports | **Attendance → Reports** (also linked from the dashboard) |
| Member self check-in | **My Stuff → Self Check-In** or Home tile **Check In** |

## Recording attendance

1. Open the attendance dashboard.
2. Choose or create the service/session date as your church defines it.
3. Check people in (search, list, or kiosk flow).
4. Use **Self Check-In** for members who mark themselves present.

## Reports (enterprise scale)

Open **Reports** for:

- Today / week / month / year / multi-year views
- Day grain vs month grain
- CSV export when offered
- Drill into a single day for who was present

> Reports use stable date formatting so monthly and yearly charts remain correct under MariaDB.

## Kiosk mode

Kiosk routes are token-protected for lobby tablets. Do not share kiosk URLs publicly. Configure kiosk access according to your security policy.

## Best practices

- Standardize service names/dates so year-over-year reports line up.
- Train greeters on one flow (dashboard vs kiosk) per campus.
- Pair with **Child Check-In** for kids ministry, not the adult attendance list alone.
""",
            10,
        ),
        _a(
            "child-checkin-guide",
            "Child Check-In: rooms, parents, and staff station",
            "Secure kids check-in for staff and parent My Kids portal.",
            "attendance-kids",
            """
## Two sides

1. **Staff station** — Church Office → **Child Check-In** (rooms, live board, check-in/out).
2. **Parents** — My Stuff → **My Kids** (manage children, see status).

## Staff flow

1. Set up **classrooms / rooms** with age labels and capacity.
2. Add or load **child profiles** (allergies, notes, photo if used).
3. Check children into a room; monitor the **live board**.
4. Secure pickup with your configured code/policy.

## Parent flow

1. Open **My Kids**.
2. Add children linked to the parent account.
3. View check-in status during service.

## Safety notes

- Treat allergy and medical notes as sensitive.
- Only trained workers should run the staff station.
- Enable the module under **Settings → Modules & Apps** if links are missing.
""",
            20,
        ),

        # ── Finance ─────────────────────────────────────────────────────
        _a(
            "accounting-full-guide",
            "Accounting: chart of accounts, ledger, expenses, budgets, payroll",
            "End-to-end church accounting suite usage.",
            "finance",
            """
## Open Accounting

**Church Office → Accounting** (or Home tile when the module is on).

## Building blocks

### Chart of Accounts

1. Open **Chart of Accounts**.
2. Review system defaults (assets, liabilities, equity, income, expense).
3. Add accounts with clear **codes** (example: `5200 Utilities`).
4. Keep income vs expense types accurate — reports depend on them.

### Ledger / journal entries

1. Open **Ledger**.
2. Create a journal entry with balanced debits and credits.
3. Use memos and references so audits are readable later.
4. Open an entry to review lines.

### Expenses

1. **Expenses → Record expense**.
2. Pick vendor (or free-text), amount, **expense account**, payment account.
3. Save — the system posts the related journal when configured.

### Vendors

Maintain vendor names, contacts, and default expense accounts for repeat bills.

### Budgets

1. Create a budget period.
2. Assign lines to expense/income accounts.
3. Compare budget vs actual on the budget detail and reports screens.

### Payroll (if used)

1. Maintain **employees** with pay type/rate.
2. Create a **pay run**, review lines, post when ready.
3. Posted runs link to journal entries.

### Reports

Use **Reports** for income/expense style summaries by account type and period.

## Permissions & modules

Enable **Accounting** under Modules & Apps. Restrict access to finance staff via roles/permissions.

## Coherence with Bills

See the guide **Bills and Accounting together** so recurring bills post cleanly into the same chart of accounts.
""",
            10,
        ),
        _a(
            "bills-and-accounting-together",
            "Bills and Accounting together (reminders + posting)",
            "How recurring bills, email reminders, expense accounts, and the ledger stay coherent.",
            "finance",
            """
## Goal

One coherent money trail:

**Recurring bill → due date → reminder emails → payment → accounting journal / expense**

## Setup checklist

1. Enable **Bills** and **Accounting** modules.
2. Open **Accounting** once so the chart of accounts seeds.
3. Open **Bills** and create/edit a bill.
4. In the bill's **Accounting** section:
   - Choose **Default expense account** (example Utilities 5200)
   - Choose **Payment account** (bank/cash asset) when paying
   - Leave **Post to accounting** checked if you want payments to hit the ledger
5. Set **reminder days before** on the bill and ensure email notifications allow bill reminders.

## Paying a bill

1. Open the bill detail.
2. Enter payment amount and date.
3. Confirm expense account + payment account.
4. Submit payment — the bridge creates an accounting entry when posting is enabled.

## Bill reminders

Background/email jobs send reminders based on:

- Bill `next_due_date`
- `reminder_days_before`
- Site notification settings (auto bill reminders)

Reminders do **not** replace accounting; they only notify payers/managers.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No expense account dropdown | Open Accounting once; seed COA; re-edit bill |
| Payment did not post | Check Post to accounting; verify accounts selected; check logs |
| No reminder emails | Confirm SMTP/email settings; notification toggles; due dates |
| Wrong expense category | Edit bill default expense account; fix COA naming |

## Best practice

- Use the **same** expense accounts on vendor bills and manual expenses.
- Reconcile monthly: Bills paid vs Accounting expenses report.
- Keep one primary bank account in the COA for clear payment account selection.
""",
            20,
        ),
        _a(
            "donations-overview",
            "Donations entry and reports",
            "Record gifts, import when available, and respect privacy.",
            "finance",
            """
## Open Donations

**Church Office → Donations** (view/manage donations permission).

## Typical flow

1. Add a donation with donor, amount, fund/category, date.
2. Use receipts when email receipts are enabled in settings.
3. Run reports for periods your board needs.

## Online giving page

If **Online Giving** is enabled in Settings, the public Donate page shows links/embeds you configured. That page is for external processors; recorded gifts still need entry/import into Donations as your process defines.

## Privacy

Treat donor data as confidential. Limit manage permissions to finance staff.
""",
            30,
        ),

        # ── Volunteers & tickets ────────────────────────────────────────
        _a(
            "volunteers-and-my-serving",
            "Volunteers and My Serving",
            "Teams, rotations, schedule, accept/decline, and tickets on My Serving.",
            "volunteers-tickets",
            """
## Staff scheduling console

**Volunteers** (module on) → dashboard:

1. Create **teams** and **roles**.
2. Track **skills** if you use skill-based placement.
3. Build **events** (date, team, times).
4. **Assign** people or fill from **rotations**.
5. Notify volunteers; they respond by email link or **My Serving**.

## My Serving (everyone)

**My Stuff → My Serving** (or Home tile):

### Volunteer schedule

- See upcoming assignments
- **Accept** or **Decline** pending requests
- Past assignments listed for history

### Tickets assigned to me

When Ticket Manager assigns you a ticket, it appears here with **Answer / update**.

## Tips

- Name teams the way people talk (“Parking”, “Kids 1st hour”).
- Use rotations for recurring Sunday roles.
- Keep My Serving as the one place greeters and volunteers check each week.
""",
            10,
        ),
        _a(
            "tickets-full-workflow",
            "Support tickets: open, assign, answer, export",
            "Member My Tickets plus staff Ticket Manager and My Serving.",
            "volunteers-tickets",
            """
## Roles

| Who | Where | What |
|-----|-------|------|
| Any member | **My Tickets** / **Submit ticket** | Open and follow their own tickets |
| Ticket managers | **Ticket Manager** (`/tickets/manage`) | See all tickets, assign, priority, status |
| Assignees | **My Serving** + ticket detail | Comment and update status |

## Member flow

1. My Stuff → **My Tickets** → submit.
2. Choose category and priority.
3. Watch for staff replies on the ticket thread.

## Manager flow

1. Open **Ticket Manager**.
2. Click a ticket.
3. **Assign** to a staff user.
4. Set **priority** and **status** (open → in progress → resolved/closed).
5. Add **comments** (optionally notify the creator).
6. **Download backup (JSON)** for archive or transfer.

## Assignee flow

1. Open **My Serving**.
2. Under **Tickets assigned to me**, click **Answer / update**.
3. Reply in comments; set status when done.

## Categories

Ticket categories are managed in the database seed (IT, Maintenance, Membership, General, etc.). Use clear titles so the right team can claim work.

## Export

Ticket Manager → **Download backup (JSON)** exports tickets and comments for backup or offline review.
""",
            20,
        ),

        # ── Worship ─────────────────────────────────────────────────────
        _a(
            "worship-team-full-guide",
            "Worship Team: songs, setlists, plans, and displays",
            "Full guide for worship leaders and band tech.",
            "worship",
            """
## Open Worship

**Church Office → Worship Team** (worship access required).

## Songs library

1. Add songs with titles, keys, and lyrics as your team needs.
2. Import tools may be available for bulk song entry.
3. Keep one canonical song entry per arrangement when possible.

## Setlists & weekly plans

1. Create a setlist for a service date.
2. Order songs for the service flow.
3. Use templates/history if your install tracks play history.

## Live / display tools

Depending on configuration:

- **Band sheet** links for tablets (often secret link, limited login)
- **Auditorium / prompter** views for titles or lyrics
- Share only with trusted devices

## Best practices

- Standardize keys and tempo notes in the song record.
- Freeze the Sunday setlist before soundcheck.
- Train volunteers on one display mode per room.
""",
            10,
        ),

        # ── Pastoral ────────────────────────────────────────────────────
        _a(
            "pastoral-area-overview",
            "Pastoral Area overview",
            "Map of sermon tools, Bible study, illustrations, planning, vault, and care.",
            "pastoral",
            """
## Who can access

Pastoral Group members and Staff/Admin/Owner typically see **Ministry → Pastoral**.

## Major tools

| Tool | Purpose |
|------|---------|
| Pastoral dashboard | Launch pad for all pastoral tools |
| Sermon Library | Draft/edit sermons and sections |
| Sermon Export | DOCX / bulk ZIP export |
| Bible Study | Read, notes, highlights, cross-links |
| Illustrations Library | Stories and reusable illustrations |
| Service Planning | Weekly plan and templates |
| Podium / plans | Service delivery views |
| Vault | Secure pastoral documents (as configured) |
| Care | Pastoral care records (sensitive) |
| Curriculum Studio | Build study courses (see Study Courses guides) |

## Sensitivity

Pastoral care and vault content can be highly confidential. Use least-privilege groups. Do not copy care notes into public Community modules.
""",
            10,
        ),
        _a(
            "pastoral-sermon-library-export",
            "Sermon Library and export",
            "Create sermons, sections, and export DOCX or bulk packages.",
            "pastoral",
            """
## Sermon Library

1. Open **Pastoral → Sermon Library** (or Pastoral dashboard tile).
2. Create a sermon with title, date, and header defaults as needed.
3. Add **sections** (points, scripture, illustrations).
4. Link illustrations or Bible study notes when helpful.
5. Save often.

## Export

1. Open **Sermon Export** from Pastoral dashboard or sermon list actions.
2. Export a **single** sermon (DOCX) or **bulk** ZIP as offered.
3. Store exports in your church's document process (not only on a laptop).

## Tips

- Keep a consistent sermon header for printed copies.
- Use sections so export layout stays readable.
- For series, name sermons with series + part numbers.
""",
            20,
        ),
        _a(
            "pastoral-bible-illustrations-planning",
            "Pastoral Bible Study, Illustrations, and Service Planning",
            "Study workflow, illustration library, and weekly planning templates.",
            "pastoral",
            """
## Bible Study (pastoral)

1. Open **Pastoral → Bible Study**.
2. Choose translation (online or installed).
3. Read chapters; save **notes** and **highlights**.
4. Send selections to **illustrations** or quick sermon tools when available.
5. Download notes when bulk export is offered.

## Illustrations Library

1. Store stories, analogies, and reusable content.
2. Tag/search so sermon prep is fast.
3. Link into sermon sections instead of pasting twice.

## Service Planning

1. Open planning list for upcoming dates.
2. Edit a week’s plan or apply a **template**.
3. Assign pieces (message, worship, announcements) as your church defines.
4. Refresh templates carefully — they can overwrite defaults.

## Vault & care

Use vault for confidential documents and care tools for pastoral care cases. Follow your legal/privacy policies.
""",
            30,
        ),

        # ── Study courses ───────────────────────────────────────────────
        _a(
            "study-courses-member-guide",
            "Study Courses for members (catalog and lessons)",
            "How learners find courses, complete lessons, and quizzes.",
            "study-courses",
            """
## Open the catalog

**Community / Home → Study Courses** (module **Study Courses** enabled) or go to `/study/`.

## Taking a course

1. Browse published courses (filter by audience if shown).
2. Open a course to see lessons and your progress.
3. Open a **lesson**.
4. Read text blocks, view images/video when present.
5. Answer **multiple choice**, **true/false**, or **fill in the blank** blocks.
6. Continue until the course marks progress complete.

## Tips for learners

- Use a stable device for longer lessons.
- Wrong quiz answers usually allow review and retry depending on the block settings.
- Only **published** courses and lessons appear here — drafts stay in Curriculum Studio.
""",
            10,
        ),
        _a(
            "curriculum-studio-build-course",
            "Curriculum Studio: build a course with text, images, and Q&A",
            "Step-by-step: series, lessons, media, multiple choice, true/false, fill-blank — plus a mock course recipe.",
            "study-courses",
            """
## Who builds courses

Pastoral / staff with access to **Pastoral → Curriculum Studio** (`/pastoral/curriculum/`).

Members **take** courses under **Study Courses** (`/study/`). Builders use the Studio.

## Mental model

```
Series (Course)
  └── Lesson 1
        ├── Text block
        ├── Image / video block
        ├── Multiple choice block
        └── True/false or fill-blank block
  └── Lesson 2
        └── ...
```

## Build a mock course (full walkthrough)

### 1) Create the series (course shell)

1. Pastoral dashboard → **Curriculum Studio**.
2. **New series** (or New course).
3. Fill in:
   - **Title**: e.g. `Foundations of Faith — Sample Course`
   - **Subtitle / description**: who it is for
   - **Audience**: everyone / youth / leaders (as offered)
   - **Visibility**: `members` or `public` when ready for learners; keep `pastoral` while drafting
   - **Status**: `draft` until content is ready
4. Save.

### 2) Add lessons

1. Open the series editor.
2. **Add lesson** — e.g. `Lesson 1: Who is God?`
3. Set lesson status to **draft** while writing.
4. Add Lesson 2, Lesson 3 the same way.
5. Reorder lessons if the Studio provides reorder controls.

### 3) Add teaching content (text)

1. Open a lesson editor.
2. Add a **text** block.
3. Write short paragraphs or bullet points (keep mobile readable).
4. Save.

### 4) Add images or media

1. Add an **image** or **video** block (labels may vary slightly).
2. Upload or link media as the form allows.
3. Add a caption in surrounding text blocks if there is no caption field.
4. Prefer compressed images for phones.

### 5) Add Q&A — multiple choice

1. Add a **multiple choice** block.
2. Enter the question.
3. Add choices (A/B/C/D).
4. Mark the correct answer.
5. Optional feedback text for correct/incorrect.
6. Save and preview.

### 6) Add Q&A — true/false

1. Add a **true/false** block.
2. Enter the statement.
3. Set whether True or False is correct.
4. Optional feedback.

### 7) Add Q&A — fill in the blank

1. Add a **fill blank** block.
2. Write the prompt (e.g. `Jesus is _______.`).
3. Provide accepted answer(s) as the form allows.
4. Save.

### 8) Preview as a learner

1. Use **Preview** on the lesson if available.
2. Or publish a test lesson to **members** visibility and open `/study/` with a test account.

### 9) Publish

1. Set each lesson **status = published**.
2. Set series **status = published**.
3. Set **visibility** to `members` or `public`.
4. Confirm the course appears under **Study Courses** for a normal member login.

## Sample outline you can copy

**Course:** Walking with Jesus (4 lessons)

1. **Who is Jesus?** — text + image + 3 multiple choice  
2. **Prayer basics** — text + true/false  
3. **Scripture habit** — text + fill blank  
4. **Living it out** — text + mixed quiz  

## Quality bar (enterprise)

- One idea per lesson (15–25 minutes)
- Every lesson ends with at least one check-for-understanding question
- No unpublished dangling lessons in a published series
- Accessibility: readable contrast on images; avoid text-only-in-image
- Review theology/content with pastoral leadership before public publish

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Course missing on `/study/` | Publish series + lessons; visibility members/public |
| Media broken | Re-upload; check file permissions/path |
| Quiz not scoring | Ensure correct answer set on the block |
| Members see pastoral-only | Change visibility off pastoral-only |
""",
            20,
        ),
        _a(
            "study-courses-help-and-ops",
            "Study Courses operations and Help integration",
            "How courses relate to Help packs, permissions, and multi-campus teaching.",
            "study-courses",
            """
## Courses vs Help articles

| | **Help Center** | **Study Courses** |
|--|-----------------|-------------------|
| Purpose | How to use the software / church processes | Discipleship teaching paths |
| Editor | Help Manage | Curriculum Studio |
| Learner UI | Browse/search guides | Catalog → lessons → blocks |
| Pack share | JSON help packs | Course content stays in curriculum tables (export separately if you add it later) |

Use **Help** to teach staff *how to build courses*. Use **Curriculum Studio** for the actual spiritual formation content.

## Permissions

- Building: pastoral/staff access to Curriculum Studio
- Taking: any logged-in member when module is enabled and course is published

## Multi-campus

If campuses are enabled, decide whether a course is org-wide or campus-specific in your operational policy. Tag course titles with campus names when content differs by location.

## Recommended SOP

1. Draft in Studio (pastoral visibility).
2. Peer review lesson content.
3. Publish to members.
4. Announce via Community announcement.
5. Review completion informally after 30 days; revise lessons.
""",
            30,
        ),

        # ── Church apps ─────────────────────────────────────────────────
        _a(
            "church-apps-bus-youth-equipment",
            "Church Apps: Bus Routes, Youth Group, Equipment & Rooms, Ministry Calendar",
            "Install, name, and run schema-driven church apps.",
            "church-apps",
            """
## What Church Apps are

Configurable mini-apps (custom modules) with a type template:

| Type | Typical use |
|------|-------------|
| **Bus Routes** | Stops, pickup times, drivers, notes |
| **Youth Group** | Youth events, leaders, locations |
| **Equipment & Rooms** | Shared resources list |
| **Ministry Calendar** | Weekly meeting pattern (bulletin style) |

## Install / manage

1. **Settings → Church Apps** (Owner/Admin).
2. Install a type, set **name** (use clear titles like **Bus Routes**, not `bus`).
3. Choose theme, visibility, and which **group** can manage records.
4. Enable **show on dashboard** if you want a tile.
5. Members open the app from **Church Office** menu or dashboard.

## Bus Routes — operating guide

1. Open **Bus Routes**.
2. Add a stop: stop name, pickup time, drop-off, driver, notes.
3. Keep drivers’ phone notes current.
4. Print or share the list with volunteers before Sunday.

## Youth Group — operating guide

1. Add events with date, time, location, leader.
2. Use description for permission slips / what to bring.
3. Archive past events by unpublishing or deleting per your process.

## Equipment & Rooms

Track sound board, van, Room 3, etc. Assign a contact person so people know who to ask.

## Ministry Calendar

List recurring ministry meetings (day of week + time). This is not a chat and not full events RSVP — use **Events** for public calendar items.

## Permissions

Manage-group users edit records; wider visibility can read. Review group membership when leaders change.
""",
            10,
        ),

        # ── Admin ───────────────────────────────────────────────────────
        _a(
            "modules-apps-toggles",
            "Modules & Apps toggles",
            "Turn optional features on/off for the whole church.",
            "admin-settings",
            """
## Open

**Settings → Modules & Apps** (Owner/Admin).

## What toggles do

Optional modules (attendance, inventory, accounting, worship, dreams, study courses, AI, etc.) can be:

- **Enabled** — appear in nav and dashboard (subject to permissions)
- **Disabled** — hidden and soft-blocked if someone hits an old URL

Core tools (Home, Profile, Groups, Pastoral core, Events, Prayers, etc.) stay available.

## After saving

1. Hard-refresh browsers.
2. Confirm tiles and menus for a normal member account, not only Owner.
3. Pair with **Church Apps** for custom bus/youth modules.
""",
            10,
        ),
        _a(
            "multi-campus-branches",
            "Campuses and branches (multi-site)",
            "Enable multi-campus, add locations, link members, switch scope.",
            "admin-settings",
            """
## Enable

1. **Settings → Campuses / Branches**.
2. Check **Enable multi-campus mode**.
3. Choose a **default campus**.
4. Save.

## Add a campus

1. Fill code (e.g. `NORTH`), name, short name, address, timezone.
2. Optionally mark **Primary**.
3. **Save campus**.

## Link members

1. Choose campus + member.
2. Optionally set as **home campus**.
3. Link.

## Daily use

When multi-campus is on, a **campus switcher** appears in the top bar:

- Pick a campus to filter operational data
- Or **All campuses** for org-wide view

## Tips

- Use short names that fit the switcher.
- Train staff to check the switcher before running reports.
- Not every historical table is campus-scoped; treat campus as a roll-out, not magic isolation for every legacy record.
""",
            20,
        ),
        _a(
            "communications-automation",
            "Communications: campaigns, workflows, and automation",
            "Mass email/SMS and drip-style workflows when the module is enabled.",
            "admin-settings",
            """
## Open

**Communications** (module enabled; staff permissions).

## Campaigns

1. Create a campaign (email or SMS as configured).
2. Write subject/body.
3. Choose audience (opt-in lists, etc.).
4. Schedule or send.
5. Review logs.

## Workflows / drips

1. Define steps and timing.
2. Enroll people manually or via triggers (e.g. new member approval hooks when configured).
3. Monitor enrollments.

## SMS

Requires provider settings (Twilio-style) on the settings/communications configuration. Keep test mode on until verified.

## Compliance

Only message people who opted in. Keep unsubscribe/opt-out behavior intact.
""",
            30,
        ),
        _a(
            "ai-insights-guide",
            "AI Insights reports",
            "Run staff AI insight reports when configured.",
            "admin-settings",
            """
## Open

**AI Insights** (module on; Staff/Admin/Owner).

## Setup

1. **Settings → AI Insights** — provider, API key, base URL as required.
2. Confirm the key works via status tools if shown.

## Run a report

1. Open AI Insights home.
2. Choose a report type (overview, donations, attendance, etc. as listed).
3. Optionally add a question.
4. Generate and read the report page.

## Guardrails

- AI can be wrong — verify numbers against native reports.
- Do not paste confidential pastoral care notes into prompts.
- Limit access to leadership.
""",
            40,
        ),

        # ── Account ─────────────────────────────────────────────────────
        _a(
            "account-login-profile",
            "Account, login, and profile",
            "Register, sign in, recover access, and update profile.",
            "account-login",
            """
## Register / login

1. Public site → **Login / Register**.
2. Complete registration; some churches require email verification and/or admin approval.
3. Sign in with username and password.

## Profile

**My Stuff → Profile** to update personal details and preferences.

## Display preferences

Use the **Display** control (palette) for theme and text size. Choose **Church default** to follow the site theme.

## Password recovery

Use forgot password / forgot username flows on the login screens. Ensure church email settings work so reset messages deliver.
""",
            10,
        ),
    ]


def build_enterprise_pack() -> dict:
    return {
        "format": FORMAT_ID,
        "pack_version": PACK_VERSION,
        "title": "MyVineChurch Enterprise Help Pack",
        "description": (
            "Detailed operator guides: pastoral, worship, attendance, accounting+bills, "
            "study courses (Curriculum Studio), church apps, tickets, campuses, and more. "
            "Import via Help → Manage → Re-upload, or seed from docs/help_packs/."
        ),
        "exported_at": "built-in",
        "categories": CATEGORIES,
        "articles": _articles(),
    }
