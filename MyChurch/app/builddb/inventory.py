# app/builddb/inventory.py
# Full path: WebChurchMan/app/builddb/inventory.py
# File name: inventory.py
# Brief, detailed purpose: Creates/updates all inventory-related tables for MariaDB.
# Supports categories (hierarchical), vendors, storage locations, master items catalog,
# batch/lot tracking (with expiration), full transaction audit trail, and optional barcode scan logging.
# Standardized timestamps: created_at/updated_at where appropriate.
# Safe schema evolution - adds missing columns/constraints/indexes without data loss.
# Isolated module - called from builddb.py during DB initialization.
# Multi-line CREATE TABLE strings dedented to prevent MariaDB syntax errors from Python indentation.

import textwrap

def create_tables(cursor):
    """
    Creates/updates the inventory management tables with full support for barcode-driven workflows,
    perishable tracking, low-stock alerts, purchase history, and complete audit trail.
    Designed for both fresh DB creation and safe migration of existing databases.
    All SQL strings dedented to avoid whitespace-induced syntax errors.
    """

    # ----- CATEGORIES TABLE -----
    cursor.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS categories (
            id          INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name        VARCHAR(100) NOT NULL UNIQUE,
            parent_id   INT UNSIGNED NULL,
            description TEXT NULL,
            icon        VARCHAR(50) NULL,
            FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """).strip())

    # Indexes for categories
    try:
        cursor.execute("CREATE INDEX idx_categories_parent ON categories(parent_id)")
    except: pass

    # ----- VENDORS TABLE -----
    cursor.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS vendors (
            id                   INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name                 VARCHAR(150) NOT NULL,
            website              VARCHAR(255) NULL,
            contact_phone        VARCHAR(30) NULL,
            contact_email        VARCHAR(100) NULL,
            default_shipping_days SMALLINT NULL,
            notes                TEXT NULL
        ) ENGINE=InnoDB;
    """).strip())

    # ----- LOCATIONS TABLE -----
    cursor.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS locations (
            id             INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name           VARCHAR(100) NOT NULL,
            description    TEXT NULL,
            building_area  VARCHAR(50) NULL
        ) ENGINE=InnoDB;
    """).strip())

    # ----- ITEMS TABLE (Master Catalog) -----
    cursor.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS items (
            id                     INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name                   VARCHAR(200) NOT NULL,
            description            TEXT NULL,
            category_id            INT UNSIGNED NOT NULL,
            preferred_vendor_id    INT UNSIGNED NULL,
            barcode_upc_ean        VARCHAR(30) NULL,
            pack_quantity          INT NULL,
            unit_of_measure        VARCHAR(30) NOT NULL DEFAULT 'each',
            typical_cost_per_unit  DECIMAL(8,2) NULL,
            min_stock_level        INT NULL,
            max_stock_level        INT NULL,
            is_perishable          BOOLEAN DEFAULT FALSE,
            shelf_life_days        INT NULL,
            image_path             VARCHAR(255) NULL,
            notes                  TEXT NULL,
            created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by             INT UNSIGNED NULL,
            FOREIGN KEY (category_id)         REFERENCES categories(id) ON DELETE RESTRICT,
            FOREIGN KEY (preferred_vendor_id) REFERENCES vendors(id)     ON DELETE SET NULL,
            FOREIGN KEY (created_by)          REFERENCES users(id)       ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """).strip())

    # Safe column additions for items
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'items'
    """)
    existing_item_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add_items = {
        'barcode_upc_ean':        "VARCHAR(30) NULL",
        'pack_quantity':          "INT NULL",
        'unit_of_measure':        "VARCHAR(30) NOT NULL DEFAULT 'each'",
        'typical_cost_per_unit':  "DECIMAL(8,2) NULL",
        'min_stock_level':        "INT NULL",
        'max_stock_level':        "INT NULL",
        'is_perishable':          "BOOLEAN DEFAULT FALSE",
        'shelf_life_days':        "INT NULL",
        'image_path':             "VARCHAR(255) NULL",
        'notes':                  "TEXT NULL",
        'created_at':             "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'created_by':             "INT UNSIGNED NULL",
        'sku':                    "VARCHAR(64) NULL",
        'is_active':              "TINYINT(1) NOT NULL DEFAULT 1",
        'is_kit':                 "TINYINT(1) NOT NULL DEFAULT 0",
        'description':            "TEXT NULL",
        'updated_at':             "TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP",
    }

    for col_name, col_def in columns_to_add_items.items():
        if col_name not in existing_item_columns:
            print(f"Migration: Adding missing column '{col_name}' to items table.")
            cursor.execute(f"ALTER TABLE items ADD COLUMN {col_name} {col_def}")

    # Indexes for items
    try:
        cursor.execute("CREATE UNIQUE INDEX idx_items_barcode ON items(barcode_upc_ean)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_items_category ON items(category_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_items_vendor ON items(preferred_vendor_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_items_sku ON items(sku)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_items_active ON items(is_active)")
    except: pass

    # ----- ITEM KITS / SETS (bill of materials) -----
    # A kit is a catalog item (is_kit=1) made of component items with quantities.
    # Deploying a kit consumes components via FIFO (does not stock the kit itself).
    cursor.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS item_kit_components (
            id                 INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            kit_item_id        INT UNSIGNED NOT NULL,
            component_item_id  INT UNSIGNED NOT NULL,
            quantity           INT UNSIGNED NOT NULL DEFAULT 1,
            notes              VARCHAR(255) NULL,
            sort_order         INT NOT NULL DEFAULT 0,
            UNIQUE KEY uq_kit_component (kit_item_id, component_item_id),
            FOREIGN KEY (kit_item_id)       REFERENCES items(id) ON DELETE CASCADE,
            FOREIGN KEY (component_item_id) REFERENCES items(id) ON DELETE RESTRICT
        ) ENGINE=InnoDB;
    """).strip())
    try:
        cursor.execute("CREATE INDEX idx_kit_components_kit ON item_kit_components(kit_item_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_kit_components_comp ON item_kit_components(component_item_id)")
    except: pass

    # ----- INVENTORY_BATCHES TABLE -----
    cursor.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS inventory_batches (
            id                INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            item_id           INT UNSIGNED NOT NULL,
            location_id       INT UNSIGNED NOT NULL,
            quantity_on_hand  INT NOT NULL DEFAULT 0,
            purchase_date     DATE NULL,
            expiration_date   DATE NULL,
            cost_per_unit     DECIMAL(8,2) NULL,
            total_cost        DECIMAL(10,2) NULL,
            lot_number        VARCHAR(50) NULL,
            notes             TEXT NULL,
            received_by       INT UNSIGNED NULL,
            FOREIGN KEY (item_id)     REFERENCES items(id)     ON DELETE CASCADE,
            FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE RESTRICT,
            FOREIGN KEY (received_by) REFERENCES users(id)      ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """).strip())

    # Indexes for batches
    try:
        cursor.execute("CREATE INDEX idx_batches_item ON inventory_batches(item_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_batches_location ON inventory_batches(location_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_batches_expiration ON inventory_batches(expiration_date)")
    except: pass

    # ----- INVENTORY_TRANSACTIONS TABLE -----
    cursor.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS inventory_transactions (
            id                INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            batch_id          INT UNSIGNED NOT NULL,
            transaction_type  ENUM('receive','adjust','use','discard','transfer','return') NOT NULL,
            quantity_change   INT NOT NULL,
            date              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id           INT UNSIGNED NOT NULL,
            related_event_id  INT UNSIGNED NULL,
            notes             TEXT NULL,
            FOREIGN KEY (batch_id)    REFERENCES inventory_batches(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id)     REFERENCES users(id)           ON DELETE RESTRICT
            -- related_event_id can link to events table in future if needed
        ) ENGINE=InnoDB;
    """).strip())

    # Indexes for transactions
    try:
        cursor.execute("CREATE INDEX idx_transactions_batch ON inventory_transactions(batch_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_transactions_user ON inventory_transactions(user_id)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_transactions_date ON inventory_transactions(date DESC)")
    except: pass

    # ----- BARCODE_SCANS TABLE (Optional logging for debugging / future multi-barcode support) -----
    cursor.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS barcode_scans (
            id               INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            barcode          VARCHAR(30) NOT NULL,
            scanned_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id          INT UNSIGNED NULL,
            resolved_item_id INT UNSIGNED NULL,
            status           ENUM('found','not_found','manual_entry') NOT NULL DEFAULT 'not_found',
            FOREIGN KEY (user_id)          REFERENCES users(id)       ON DELETE SET NULL,
            FOREIGN KEY (resolved_item_id) REFERENCES items(id)       ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """).strip())

    # Indexes for barcode scans
    try:
        cursor.execute("CREATE INDEX idx_scans_barcode ON barcode_scans(barcode)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_scans_item ON barcode_scans(resolved_item_id)")
    except: pass

    # Seed starter categories / locations so churches can start immediately
    cursor.execute("SELECT COUNT(*) AS c FROM categories")
    cat_count = cursor.fetchone()
    cat_n = cat_count[0] if isinstance(cat_count, (list, tuple)) else (cat_count or {}).get('c', 0)
    if not cat_n:
        defaults = [
            'Office supplies',
            'Cleaning & facilities',
            'Kitchen & hospitality',
            'Communion / worship',
            'Children & nursery',
            'Youth ministry',
            'AV / tech',
            'First aid & safety',
            'Events & outreach',
            'Curriculum & print',
            'Maintenance / tools',
            'Kits & sets',
        ]
        for name in defaults:
            try:
                cursor.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
            except Exception:
                pass
        print("Seeded default inventory categories.")

    cursor.execute("SELECT COUNT(*) AS c FROM locations")
    loc_count = cursor.fetchone()
    loc_n = loc_count[0] if isinstance(loc_count, (list, tuple)) else (loc_count or {}).get('c', 0)
    if not loc_n:
        for name, area in [
            ('Main storage', 'Building'),
            ('Kitchen pantry', 'Kitchen'),
            ('Nursery closet', 'Children'),
            ('AV booth', 'Sanctuary'),
            ('Office supply closet', 'Office'),
            ('Janitor closet', 'Facilities'),
        ]:
            try:
                cursor.execute(
                    "INSERT INTO locations (name, building_area) VALUES (%s, %s)",
                    (name, area),
                )
            except Exception:
                pass
        print("Seeded default inventory locations.")

    print("Inventory tables synchronization complete (MariaDB). Ready for barcode scanning, batch tracking, kits/sets, expiration alerts, and full audit trail.")