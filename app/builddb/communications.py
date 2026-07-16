# Mass email, SMS, automated workflows & drip campaigns.


def create_tables(cursor):
    # SMS / email prefs on users
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
    """)
    ucols = {row[0] for row in cursor.fetchall()}
    for name, definition in {
        'accepts_sms': "TINYINT(1) NOT NULL DEFAULT 0",
        'accepts_mass_emails': "TINYINT(1) NOT NULL DEFAULT 1",
    }.items():
        if name not in ucols:
            print(f"Migration: Adding users.{name}")
            cursor.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")

    # Provider settings on settings row
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'settings'
    """)
    scols = {row[0] for row in cursor.fetchall()}
    for name, definition in {
        'sms_enabled': "TINYINT(1) NOT NULL DEFAULT 0",
        'sms_provider': "VARCHAR(32) NOT NULL DEFAULT 'twilio'",
        'sms_account_sid': "VARCHAR(128) NULL",
        'sms_auth_token_enc': "TEXT NULL",
        'sms_from_number': "VARCHAR(40) NULL",
        'sms_test_mode': "TINYINT(1) NOT NULL DEFAULT 1",
        'comm_default_from_name': "VARCHAR(120) NULL",
    }.items():
        if name not in scols:
            print(f"Migration: Adding settings.{name}")
            cursor.execute(f"ALTER TABLE settings ADD COLUMN {name} {definition}")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comm_campaigns (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            channel VARCHAR(16) NOT NULL DEFAULT 'email',
            title VARCHAR(255) NOT NULL,
            subject VARCHAR(500) NULL,
            body MEDIUMTEXT NOT NULL,
            audience_type VARCHAR(32) NOT NULL DEFAULT 'all_opt_in',
            audience_ref VARCHAR(64) NULL,
            audience_ids_json MEDIUMTEXT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'draft',
            scheduled_at TIMESTAMP NULL,
            started_at TIMESTAMP NULL,
            completed_at TIMESTAMP NULL,
            total_recipients INT NOT NULL DEFAULT 0,
            sent_count INT NOT NULL DEFAULT 0,
            failed_count INT NOT NULL DEFAULT 0,
            skipped_count INT NOT NULL DEFAULT 0,
            created_by INT UNSIGNED NULL,
            notes VARCHAR(500) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_comm_camp_status (status),
            INDEX idx_comm_camp_sched (status, scheduled_at),
            INDEX idx_comm_camp_channel (channel)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comm_campaign_recipients (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            campaign_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NULL,
            address VARCHAR(255) NOT NULL,
            display_name VARCHAR(160) NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            error_detail VARCHAR(500) NULL,
            sent_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_comm_recip_camp (campaign_id, status),
            CONSTRAINT fk_comm_recip_camp
                FOREIGN KEY (campaign_id) REFERENCES comm_campaigns(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comm_workflows (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(255) NOT NULL,
            description TEXT NULL,
            trigger_type VARCHAR(40) NOT NULL DEFAULT 'manual',
            trigger_config_json MEDIUMTEXT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'draft',
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_comm_wf_status (status),
            INDEX idx_comm_wf_trigger (trigger_type, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # Safe migrations for existing installs
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'comm_workflows'
    """)
    wf_cols = {row[0] for row in cursor.fetchall()}
    if 'trigger_config_json' not in wf_cols:
        print("Migration: Adding comm_workflows.trigger_config_json")
        cursor.execute("ALTER TABLE comm_workflows ADD COLUMN trigger_config_json MEDIUMTEXT NULL")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comm_workflow_steps (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            workflow_id INT UNSIGNED NOT NULL,
            step_order INT NOT NULL DEFAULT 0,
            delay_days INT NOT NULL DEFAULT 0,
            channel VARCHAR(24) NOT NULL DEFAULT 'email',
            subject VARCHAR(500) NULL,
            body MEDIUMTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_comm_steps_wf (workflow_id, step_order),
            CONSTRAINT fk_comm_steps_wf
                FOREIGN KEY (workflow_id) REFERENCES comm_workflows(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comm_workflow_enrollments (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            workflow_id INT UNSIGNED NOT NULL,
            user_id INT UNSIGNED NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'active',
            current_step INT NOT NULL DEFAULT 0,
            context_json MEDIUMTEXT NULL,
            enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            next_run_at TIMESTAMP NULL,
            completed_at TIMESTAMP NULL,
            last_error VARCHAR(500) NULL,
            UNIQUE KEY uq_comm_enroll (workflow_id, user_id),
            INDEX idx_comm_enroll_due (status, next_run_at),
            CONSTRAINT fk_comm_enroll_wf
                FOREIGN KEY (workflow_id) REFERENCES comm_workflows(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'comm_workflow_enrollments'
    """)
    en_cols = {row[0] for row in cursor.fetchall()}
    if 'context_json' not in en_cols:
        print("Migration: Adding comm_workflow_enrollments.context_json")
        cursor.execute("ALTER TABLE comm_workflow_enrollments ADD COLUMN context_json MEDIUMTEXT NULL")

    # Scheduler throttle for automation (shorter than bill reminders)
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'settings'
    """)
    scols2 = {row[0] for row in cursor.fetchall()}
    if 'automation_last_run' not in scols2:
        print("Migration: Adding settings.automation_last_run")
        cursor.execute("ALTER TABLE settings ADD COLUMN automation_last_run TIMESTAMP NULL")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comm_message_log (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            channel VARCHAR(16) NOT NULL,
            source VARCHAR(40) NOT NULL DEFAULT 'campaign',
            campaign_id INT UNSIGNED NULL,
            workflow_id INT UNSIGNED NULL,
            enrollment_id INT UNSIGNED NULL,
            user_id INT UNSIGNED NULL,
            to_address VARCHAR(255) NOT NULL,
            subject VARCHAR(500) NULL,
            body_preview VARCHAR(500) NULL,
            status VARCHAR(24) NOT NULL,
            error_detail VARCHAR(500) NULL,
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_comm_log_created (created_at),
            INDEX idx_comm_log_channel (channel, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
