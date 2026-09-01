# Child Check-In: profiles, guardians, classrooms, secure pickup, attendance.


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS child_classrooms (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(120) NOT NULL,
            short_code VARCHAR(16) NULL,
            description VARCHAR(500) NULL,
            location VARCHAR(120) NULL,
            age_label VARCHAR(80) NULL,
            age_min_months INT UNSIGNED NULL,
            age_max_months INT UNSIGNED NULL,
            capacity INT UNSIGNED NULL,
            color VARCHAR(24) NOT NULL DEFAULT '#22d3ee',
            sort_order INT NOT NULL DEFAULT 0,
            active TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_child_rooms_active (active, sort_order)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS child_profiles (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            nickname VARCHAR(80) NULL,
            birthdate DATE NULL,
            gender VARCHAR(24) NULL,
            allergies TEXT NULL,
            medical_notes TEXT NULL,
            special_needs TEXT NULL,
            photo_path VARCHAR(500) NULL,
            pin_code VARCHAR(12) NULL,
            default_classroom_id INT UNSIGNED NULL,
            notes TEXT NULL,
            active TINYINT(1) NOT NULL DEFAULT 1,
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_child_name (last_name, first_name),
            INDEX idx_child_pin (pin_code),
            INDEX idx_child_active (active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS child_guardians (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            child_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NULL,
            full_name VARCHAR(160) NULL,
            relationship VARCHAR(40) NOT NULL DEFAULT 'parent',
            phone VARCHAR(40) NULL,
            email VARCHAR(255) NULL,
            family_pin VARCHAR(12) NULL,
            is_primary TINYINT(1) NOT NULL DEFAULT 0,
            can_pickup TINYINT(1) NOT NULL DEFAULT 1,
            notify_email TINYINT(1) NOT NULL DEFAULT 1,
            notify_checkin TINYINT(1) NOT NULL DEFAULT 1,
            notify_checkout TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_child_user (child_id, user_id),
            INDEX idx_guardian_user (user_id),
            INDEX idx_guardian_pin (family_pin),
            INDEX idx_guardian_phone (phone),
            CONSTRAINT fk_guardian_child
                FOREIGN KEY (child_id) REFERENCES child_profiles(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS child_checkins (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            child_id INT UNSIGNED NOT NULL,
            classroom_id INT UNSIGNED NULL,
            service_date DATE NOT NULL,
            event_label VARCHAR(120) NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'checked_in',
            pickup_code VARCHAR(12) NOT NULL,
            security_code VARCHAR(12) NOT NULL,
            check_in_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            check_out_at TIMESTAMP NULL,
            guardian_user_id INT UNSIGNED NULL,
            guardian_name VARCHAR(160) NULL,
            checked_in_by INT UNSIGNED NULL,
            checked_out_by INT UNSIGNED NULL,
            checkout_method VARCHAR(40) NULL,
            label_printed TINYINT(1) NOT NULL DEFAULT 0,
            notes VARCHAR(500) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_checkin_date_status (service_date, status),
            INDEX idx_checkin_child_date (child_id, service_date),
            INDEX idx_checkin_pickup (pickup_code, service_date),
            INDEX idx_checkin_security (security_code, service_date),
            INDEX idx_checkin_room (classroom_id, service_date, status),
            CONSTRAINT fk_checkin_child
                FOREIGN KEY (child_id) REFERENCES child_profiles(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # Settings flags on settings table
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'settings'
    """)
    scols = {row[0] for row in cursor.fetchall()}
    for name, definition in {
        'child_checkin_enabled': "TINYINT(1) NOT NULL DEFAULT 1",
        'child_checkin_require_code': "TINYINT(1) NOT NULL DEFAULT 1",
        'child_checkin_notify_default': "TINYINT(1) NOT NULL DEFAULT 1",
        'child_checkin_label_footer': "VARCHAR(255) NULL",
    }.items():
        if name not in scols:
            print(f"Migration: Adding settings.{name}")
            cursor.execute(f"ALTER TABLE settings ADD COLUMN {name} {definition}")

    # Seed starter classrooms if empty
    cursor.execute("SELECT COUNT(*) AS n FROM child_classrooms")
    row = cursor.fetchone()
    n = row[0] if not isinstance(row, dict) else row.get('n', 0)
    if not n:
        seeds = [
            ('Nursery', 'NUR', '0–12 months', 0, 12, 8, '#f472b6', 10),
            ('Toddlers', 'TOD', '1–2 years', 12, 36, 12, '#fb923c', 20),
            ('Preschool', 'PRE', '3–5 years', 36, 72, 16, '#a78bfa', 30),
            ('Elementary', 'ELEM', 'K–5th', 72, 144, 24, '#22d3ee', 40),
            ('Kids Church', 'KIDS', 'All kids service', None, None, 40, '#34d399', 50),
        ]
        for name, code, age, amin, amax, cap, color, sort in seeds:
            cursor.execute(
                """
                INSERT INTO child_classrooms
                    (name, short_code, age_label, age_min_months, age_max_months, capacity, color, sort_order)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (name, code, age, amin, amax, cap, color, sort),
            )
