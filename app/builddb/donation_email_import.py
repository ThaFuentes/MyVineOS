# Donation email import + recurring gifts + payment provider settings.


def create_tables(cursor):
    # Extend donations with processor linkage + receipt lifecycle
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'donations'
    """)
    cols = {row[0] for row in cursor.fetchall()}
    for name, definition in {
        'external_id': "VARCHAR(128) NULL",
        'source': "VARCHAR(32) NOT NULL DEFAULT 'manual'",
        'processor': "VARCHAR(32) NULL",
        'currency': "VARCHAR(8) NOT NULL DEFAULT 'USD'",
        'receipt_status': "VARCHAR(24) NOT NULL DEFAULT 'none'",
        'receipt_sent_at': "TIMESTAMP NULL",
        'import_message_id': "INT UNSIGNED NULL",
        'fund_label': "VARCHAR(120) NULL",
        'is_recurring': "TINYINT(1) NOT NULL DEFAULT 0",
        'recurring_id': "INT UNSIGNED NULL",
    }.items():
        if name not in cols:
            print(f"Migration: Adding donations.{name}")
            cursor.execute(f"ALTER TABLE donations ADD COLUMN {name} {definition}")

    try:
        cursor.execute(
            "CREATE UNIQUE INDEX idx_donations_external ON donations(processor, external_id)"
        )
    except Exception:
        pass

    # POP3/IMAP mailbox used only for payment notification emails
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_email_mailbox (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            label VARCHAR(120) NOT NULL DEFAULT 'Giving inbox',
            protocol VARCHAR(8) NOT NULL DEFAULT 'pop3',
            host VARCHAR(255) NOT NULL,
            port INT NOT NULL DEFAULT 995,
            username VARCHAR(255) NOT NULL,
            password_enc TEXT NULL,
            use_ssl TINYINT(1) NOT NULL DEFAULT 1,
            enabled TINYINT(1) NOT NULL DEFAULT 0,
            last_scan_at TIMESTAMP NULL,
            last_error VARCHAR(500) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
    """)

    # Ingested messages (raw + parse status)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_email_messages (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            mailbox_id INT UNSIGNED NULL,
            message_uid VARCHAR(255) NOT NULL,
            message_id_header VARCHAR(512) NULL,
            subject VARCHAR(500) NULL,
            from_address VARCHAR(255) NULL,
            received_at TIMESTAMP NULL,
            body_text MEDIUMTEXT NULL,
            body_html MEDIUMTEXT NULL,
            processor VARCHAR(32) NULL,
            parse_status VARCHAR(24) NOT NULL DEFAULT 'pending',
            parse_confidence DECIMAL(5,2) NULL,
            parsed_json MEDIUMTEXT NULL,
            donation_id INT UNSIGNED NULL,
            error_detail VARCHAR(500) NULL,
            is_fixture TINYINT(1) NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_donation_email_uid (mailbox_id, message_uid),
            INDEX idx_donation_email_status (parse_status),
            INDEX idx_donation_email_processor (processor)
        ) ENGINE=InnoDB;
    """)

    # Recurring giving plans (manual, Stripe, ACH, email-discovered)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_recurring (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            donor_name VARCHAR(255) NOT NULL,
            donor_email VARCHAR(255) NULL,
            user_id INT UNSIGNED NULL,
            amount DECIMAL(12,2) NOT NULL,
            currency VARCHAR(8) NOT NULL DEFAULT 'USD',
            frequency VARCHAR(24) NOT NULL DEFAULT 'monthly',
            processor VARCHAR(32) NULL,
            external_subscription_id VARCHAR(128) NULL,
            method VARCHAR(64) NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'active',
            next_charge_date DATE NULL,
            start_date DATE NULL,
            end_date DATE NULL,
            notes TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_recurring_status (status),
            INDEX idx_recurring_processor (processor)
        ) ENGINE=InnoDB;
    """)

    # Online payment provider credentials (Stripe etc.) — secrets encrypted
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_payment_providers (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            provider VARCHAR(32) NOT NULL,
            display_name VARCHAR(120) NOT NULL,
            mode VARCHAR(16) NOT NULL DEFAULT 'test',
            enabled TINYINT(1) NOT NULL DEFAULT 0,
            publishable_key VARCHAR(255) NULL,
            secret_key_enc TEXT NULL,
            webhook_secret_enc TEXT NULL,
            supports_ach TINYINT(1) NOT NULL DEFAULT 0,
            supports_recurring TINYINT(1) NOT NULL DEFAULT 0,
            metadata_json TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_donation_provider (provider, mode)
        ) ENGINE=InnoDB;
    """)

    # Global giving automation flags on settings
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'settings'
    """)
    scols = {row[0] for row in cursor.fetchall()}
    for name, definition in {
        'donation_receipt_mode': "VARCHAR(16) NOT NULL DEFAULT 'test'",
        'donation_email_auto_import': "TINYINT(1) NOT NULL DEFAULT 0",
        'donation_email_auto_post': "TINYINT(1) NOT NULL DEFAULT 0",
        'donation_receipt_test_email': "VARCHAR(255) NULL",
        'donation_email_import_enabled': "TINYINT(1) NOT NULL DEFAULT 1",
        'donation_email_auto_post_min_conf': "INT NOT NULL DEFAULT 90",
        'donation_email_auto_receipt': "TINYINT(1) NOT NULL DEFAULT 0",
        'donation_receipt_policy': "VARCHAR(24) NOT NULL DEFAULT 'all'",
        'donation_receipt_email_list': "MEDIUMTEXT NULL",
        'donation_receipt_staff_notify': "VARCHAR(500) NULL",
        'donation_email_parse_mode': "VARCHAR(16) NOT NULL DEFAULT 'auto'",
    }.items():
        if name not in scols:
            print(f"Migration: Adding settings.{name}")
            cursor.execute(f"ALTER TABLE settings ADD COLUMN {name} {definition}")
