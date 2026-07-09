# MYVINECHURCH.ONLINE/app/builddb/pastoral.py
# Full path: WebChurchMan/app/builddb/pastoral.py
# File name: pastoral.py
# Brief, detailed purpose: Creates and safely migrates ALL database tables for the Pastoral Area module (full comprehensive rebuild).
# Includes every table and column that has ever been part of the Pastoral Area design.
# Nothing is removed - this is the longest, most complete version that preserves every historical and planned field.
# Matches exact style of existing builddb modules: explicit CREATE TABLE IF NOT EXISTS,
# safe column additions for migrations, idempotent constraints/indexes via safe_exec.
# ALL IDs/FKs use INT UNSIGNED to match typical users.id (unsigned for larger positive range).
# REMOVED: Drop tables block - this was wiping all your saved plans on every app restart!
# Now data persists between runs - your saved plans will stay and appear in the list.
# NEW: Added service_templates and service_template_assignments tables for central permanent recurring masters.
# One row per recurring service type (Sunday Morning, etc.)
# Change once instantly affects all future matching weekdays
# service_plans preserved for dated overrides/special events
# NEW: Global default role assignments (pre-fill new templates & overrides)
# UPDATED: start_time and worship_start_time on both tables
# NEW: Added forced_notes TEXT to service_templates - critical lines that must appear in every plan.
# REMOVED: Old 52-week row generation - replaced with single default Sunday template seed if none exists
# All previous tables/columns preserved exactly.

from app.models.pastoral.service_plans import seed_default_sunday_template, dedupe_service_templates

def create_tables(cursor):
    """
    Creates/updates all Pastoral Area tables (full rebuild - preserves every column and table).
    Safe for both fresh DB creation and migration of existing databases.
    Tables are created in dependency order to avoid FK constraint errors (errno 150).
    At the very end, seeds default Sunday template if none exists.
    """
    print("Starting FULL Pastoral Area database setup (comprehensive rebuild - nothing removed)...")
    # NO DROP TABLES - removed so your saved plans persist between app restarts!

    # 1. Independent / base tables first
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bible_translations (
            code VARCHAR(20) PRIMARY KEY,
            name TEXT NOT NULL,
            is_default TINYINT(1) DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bible_verses (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            translation VARCHAR(20) NOT NULL,
            book VARCHAR(50) NOT NULL,
            chapter INT UNSIGNED NOT NULL,
            verse INT UNSIGNED NOT NULL,
            text TEXT NOT NULL,
            UNIQUE KEY uniq_verse (translation, book, chapter, verse),
            FOREIGN KEY (translation) REFERENCES bible_translations(code) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bible_books (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(60) NOT NULL UNIQUE,
            abbrev VARCHAR(12) NOT NULL,
            testament ENUM('OT', 'NT') NOT NULL,
            sort_order INT UNSIGNED NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strongs_lexicon (
            number VARCHAR(10) PRIMARY KEY,
            language ENUM('hebrew', 'greek') NOT NULL,
            lemma TEXT,
            transliteration TEXT,
            definition TEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strongs_occurrences (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            strongs_number VARCHAR(10) NOT NULL,
            book VARCHAR(50) NOT NULL,
            chapter INT UNSIGNED NOT NULL,
            verse INT UNSIGNED NOT NULL,
            word_index INT UNSIGNED NOT NULL DEFAULT 0,
            surface_word VARCHAR(120),
            UNIQUE KEY uniq_strongs_occ (strongs_number, book, chapter, verse, word_index),
            FOREIGN KEY (strongs_number) REFERENCES strongs_lexicon(number) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 2. Core sermon table (referenced by sections, collaborators, plans)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pastoral_sermons (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            title TEXT NOT NULL,
            preacher_id INT UNSIGNED,
            primary_passage TEXT,
            service_date DATE,
            visibility VARCHAR(20) DEFAULT 'private',
            header_text TEXT,
            footer_text TEXT,
            conclusion_text TEXT,
            series_tags TEXT,
            notes TEXT,
            created_by INT UNSIGNED NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (preacher_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT chk_sermon_visibility CHECK (visibility IN ('private', 'collaborators', 'pastoral_group'))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # Safe migrations for pastoral_sermons
    cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pastoral_sermons'")
    existing = [row[0] for row in cursor.fetchall()]
    columns_to_add = {
        'preacher_id': "INT UNSIGNED",
        'conclusion_text': "TEXT",
        'header_text': "TEXT",
        'footer_text': "TEXT",
        'series_tags': "TEXT",
        'visibility': "VARCHAR(20) DEFAULT 'private'"
    }
    for col, definition in columns_to_add.items():
        if col not in existing:
            print(f" Migration: Adding column '{col}' to pastoral_sermons")
            cursor.execute(f"ALTER TABLE pastoral_sermons ADD COLUMN {col} {definition}")

    safe_exec(cursor, """
        ALTER TABLE pastoral_sermons
        ADD CONSTRAINT IF NOT EXISTS chk_sermon_visibility
        CHECK (visibility IN ('private', 'collaborators', 'pastoral_group'))
    """)

    # 3. Illustration library
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS illustration_library (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            user_id INT UNSIGNED,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 4. Sermon sections - WITH source TEXT column
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sermon_sections (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            sermon_id INT UNSIGNED NOT NULL,
            sort_order INT UNSIGNED NOT NULL DEFAULT 0,
            section_type VARCHAR(50),
            title TEXT,
            content TEXT,
            scripture_reference TEXT,
            source TEXT,
            illustration_id INT UNSIGNED,
            notes TEXT,
            FOREIGN KEY (sermon_id) REFERENCES pastoral_sermons(id) ON DELETE CASCADE,
            FOREIGN KEY (illustration_id) REFERENCES illustration_library(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # Safe migration: Add source column if missing
    cursor.execute("SHOW COLUMNS FROM sermon_sections LIKE 'source'")
    if not cursor.fetchone():
        print(" Migration: Adding column 'source' (TEXT) to sermon_sections")
        safe_exec(cursor, "ALTER TABLE sermon_sections ADD COLUMN source TEXT AFTER scripture_reference")

    # NEW: Permanent recurring service templates (central "main plan")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_templates (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            title TEXT NOT NULL,
            notes TEXT,
            forced_notes TEXT,
            start_time TIME,
            worship_start_time TIME,
            pastoral_sermon_id INT UNSIGNED,
            weekday TINYINT UNSIGNED NOT NULL,
            created_by INT UNSIGNED NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (pastoral_sermon_id) REFERENCES pastoral_sermons(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # Safe migration: Add forced_notes if missing
    cursor.execute("SHOW COLUMNS FROM service_templates LIKE 'forced_notes'")
    if not cursor.fetchone():
        print(" Migration: Adding column 'forced_notes' (TEXT) to service_templates")
        safe_exec(cursor, "ALTER TABLE service_templates ADD COLUMN forced_notes TEXT AFTER notes")

    # NEW: Template assignments
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_template_assignments (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            template_id INT UNSIGNED NOT NULL,
            role_name TEXT NOT NULL,
            user_id INT UNSIGNED,
            FOREIGN KEY (template_id) REFERENCES service_templates(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 5. Dated service plans - overrides/special events only
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_plans (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            service_date DATE NOT NULL UNIQUE,
            title TEXT,
            notes TEXT,
            pastoral_sermon_id INT UNSIGNED,
            created_by INT UNSIGNED NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            start_time TIME,
            worship_start_time TIME,
            FOREIGN KEY (pastoral_sermon_id) REFERENCES pastoral_sermons(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # Safe migration for time columns on service_plans
    cursor.execute("SHOW COLUMNS FROM service_plans LIKE 'start_time'")
    if not cursor.fetchone():
        print(" Migration: Adding column 'start_time' to service_plans")
        safe_exec(cursor, "ALTER TABLE service_plans ADD COLUMN start_time TIME AFTER updated_at")
    cursor.execute("SHOW COLUMNS FROM service_plans LIKE 'worship_start_time'")
    if not cursor.fetchone():
        print(" Migration: Adding column 'worship_start_time' to service_plans")
        safe_exec(cursor, "ALTER TABLE service_plans ADD COLUMN worship_start_time TIME AFTER start_time")

    # 6. Dated plan assignments
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_plan_assignments (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            service_plan_id INT UNSIGNED NOT NULL,
            role_name TEXT NOT NULL,
            user_id INT UNSIGNED,
            UNIQUE KEY uniq_role_per_plan (service_plan_id, role_name),
            FOREIGN KEY (service_plan_id) REFERENCES service_plans(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # NEW: Global default role assignments (pre-fill new templates & dated overrides)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS default_service_plan_assignments (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            role_name TEXT NOT NULL,
            user_id INT UNSIGNED,
            UNIQUE KEY uniq_default_role (role_name(191))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # Seed default Preacher if table empty
    cursor.execute("SELECT COUNT(*) FROM default_service_plan_assignments")
    row = cursor.fetchone()
    if row and row[0] == 0:
        print(" Seeding default Preacher (user_id=1)")
        try:
            cursor.execute("""
                INSERT INTO default_service_plan_assignments (role_name, user_id)
                VALUES ('Preacher', 1)
            """)
        except Exception as e:
            print(f" Warning: Could not seed default Preacher: {e}")

    # Pastoral Care module tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pastoral_care_requests (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            member_id INT UNSIGNED NOT NULL,
            request_type VARCHAR(50) NOT NULL,
            title TEXT,
            description TEXT NOT NULL,
            urgency VARCHAR(20) DEFAULT 'normal',
            status VARCHAR(30) DEFAULT 'open',
            submitted_by INT UNSIGNED,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (submitted_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pastoral_care_assignments (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            request_id INT UNSIGNED NOT NULL,
            pastor_id INT UNSIGNED NOT NULL,
            notes TEXT,
            is_primary TINYINT(1) DEFAULT 0,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (request_id) REFERENCES pastoral_care_requests(id) ON DELETE CASCADE,
            FOREIGN KEY (pastor_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pastoral_care_notes (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            request_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            note TEXT NOT NULL,
            is_private TINYINT(1) DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (request_id) REFERENCES pastoral_care_requests(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_care_requests_status ON pastoral_care_requests(status)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_care_requests_member ON pastoral_care_requests(member_id)")

    # 7-11. Remaining tables (unchanged)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sermon_collaborators (
            sermon_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            added_by INT UNSIGNED,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (sermon_id, user_id),
            FOREIGN KEY (sermon_id) REFERENCES pastoral_sermons(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sermon_edits (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            sermon_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            change_description TEXT,
            FOREIGN KEY (sermon_id) REFERENCES pastoral_sermons(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sermon_templates (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            name TEXT NOT NULL,
            user_id INT UNSIGNED,
            structure TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pastoral_group_members (
            user_id INT UNSIGNED PRIMARY KEY,
            added_by INT UNSIGNED,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 11. pastoral_vault - FULLY UPDATED for lossless sermon section <-> vault integration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pastoral_vault (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            user_id INT UNSIGNED NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            reference TEXT,
            notes TEXT,
            tags TEXT,
            section_type VARCHAR(50) DEFAULT 'point',
            scripture_reference TEXT,
            source_url TEXT,
            visibility ENUM('private', 'pastoral_group') NOT NULL DEFAULT 'private',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # Safe migration for pastoral_vault
    print(" Migration: Updating pastoral_vault schema...")
    cursor.execute("""
        ALTER TABLE pastoral_vault
            MODIFY COLUMN IF EXISTS user_id INT UNSIGNED NULL,
            MODIFY COLUMN IF EXISTS visibility ENUM('private', 'pastoral_group') NOT NULL DEFAULT 'private',
            ADD COLUMN IF NOT EXISTS title TEXT,
            ADD COLUMN IF NOT EXISTS section_type VARCHAR(50) DEFAULT 'point',
            ADD COLUMN IF NOT EXISTS scripture_reference TEXT,
            ADD COLUMN IF NOT EXISTS source_url TEXT
    """)
    cursor.execute("""
        UPDATE pastoral_vault
        SET title = COALESCE(title, reference, LEFT(content, 200), 'Untitled Legacy Item')
        WHERE title IS NULL OR title = ''
    """)
    cursor.execute("ALTER TABLE pastoral_vault MODIFY COLUMN title TEXT NOT NULL")

    safe_exec(cursor, "ALTER TABLE pastoral_vault DROP CONSTRAINT IF EXISTS chk_vault_type")
    safe_exec(cursor, "ALTER TABLE pastoral_vault DROP CONSTRAINT IF EXISTS chk_vault_visibility")
    safe_exec(cursor, "ALTER TABLE pastoral_vault DROP COLUMN IF EXISTS type")

    # ----- Indexes (idempotent) -----
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_bible_search ON bible_verses(translation, book, chapter, verse)")
    safe_exec(cursor, "CREATE FULLTEXT INDEX IF NOT EXISTS ft_bible_text ON bible_verses(text)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_strongs_occ_ref ON strongs_occurrences(book, chapter, verse)")

    from app.models.pastoral.bible import seed_canon_books, seed_sample_bible_and_strongs
    print("Seeding Bible canon + sample translation (if empty)...")
    seed_canon_books(cursor)
    seed_sample_bible_and_strongs(cursor)
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_sermon_sections_order ON sermon_sections(sermon_id, sort_order)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_service_plans_date ON service_plans(service_date)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_illustration_user ON illustration_library(user_id)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_vault_user ON pastoral_vault(user_id)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_vault_visibility ON pastoral_vault(visibility)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_vault_tags ON pastoral_vault(tags(191))")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_vault_section_type ON pastoral_vault(section_type)")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_vault_source_url ON pastoral_vault(source_url(191))")
    safe_exec(cursor, "CREATE INDEX IF NOT EXISTS idx_sermon_edits_sermon ON sermon_edits(sermon_id)")

    # NEW: Seed default Sunday template if none exist; remove duplicate weekday masters
    print("Seeding default Sunday template (if needed)...")
    dedupe_service_templates()
    seed_default_sunday_template()

# Helper - silently ignore duplicate/already-exists errors
def safe_exec(cursor, sql):
    try:
        cursor.execute(sql)
    except Exception as e:
        if "Duplicate" not in str(e) and "already exists" not in str(e).lower():
            print(f" Warning during index/constraint: {e}")

print("MYVINECHURCH.ONLINE/app/builddb/pastoral.py - fully rebuilt with 100% ASCII-safe strings only")