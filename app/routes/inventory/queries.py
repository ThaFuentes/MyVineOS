# app/routes/inventory/queries.py
# Data-access layer for inventory (MariaDB / PyMySQL).

import pymysql
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from app.models.db import get_db
from app.utils.time_utils import utc_now


def get_low_stock_items():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT i.id, i.name, i.min_stock_level,
               COALESCE(SUM(b.quantity_on_hand), 0) AS total_stock
        FROM items i
        LEFT JOIN inventory_batches b ON b.item_id = i.id
        GROUP BY i.id, i.name, i.min_stock_level
        HAVING i.min_stock_level IS NOT NULL
           AND total_stock < i.min_stock_level
        ORDER BY total_stock ASC
        LIMIT 20
    """)
    return cur.fetchall()


def get_expiring_items(days=30):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    expire_date = (datetime.utcnow() + timedelta(days=days)).strftime('%Y-%m-%d')
    cur.execute("""
        SELECT i.name, b.expiration_date, b.quantity_on_hand, l.name AS location_name
        FROM inventory_batches b
        JOIN items i ON b.item_id = i.id
        JOIN locations l ON b.location_id = l.id
        WHERE b.expiration_date IS NOT NULL
          AND b.expiration_date <= %s
          AND b.quantity_on_hand > 0
        ORDER BY b.expiration_date ASC
        LIMIT 15
    """, (expire_date,))
    return cur.fetchall()


def get_recent_transactions(limit=20):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT t.id, t.transaction_type, t.quantity_change, t.date, t.notes,
               i.name AS item_name, u.username AS user_name
        FROM inventory_transactions t
        JOIN inventory_batches b ON t.batch_id = b.id
        JOIN items i ON b.item_id = i.id
        LEFT JOIN users u ON t.user_id = u.id
        ORDER BY t.date DESC
        LIMIT %s
    """, (limit,))
    return cur.fetchall()


def get_items_list(search='', category_id=None, active_only=True, kits_only=False,
                   low_stock_only=False, include_stock=True):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT i.*, c.name AS category_name,
               COALESCE(SUM(b.quantity_on_hand), 0) AS total_stock
        FROM items i
        LEFT JOIN categories c ON i.category_id = c.id
        LEFT JOIN inventory_batches b ON b.item_id = i.id
        WHERE 1=1
    """
    params = []

    if active_only:
        sql += " AND COALESCE(i.is_active, 1) = 1"
    if kits_only:
        sql += " AND COALESCE(i.is_kit, 0) = 1"
    if category_id:
        sql += " AND i.category_id = %s"
        params.append(int(category_id))
    if search:
        like = f"%{search}%"
        sql += """ AND (
            i.name LIKE %s OR i.barcode_upc_ean = %s OR i.sku LIKE %s
            OR c.name LIKE %s OR i.description LIKE %s
        )"""
        params.extend([like, search, like, like, like])

    sql += " GROUP BY i.id"
    if low_stock_only:
        sql += " HAVING i.min_stock_level IS NOT NULL AND total_stock < i.min_stock_level"
    sql += " ORDER BY i.name"
    cur.execute(sql, params)
    return cur.fetchall()


def get_catalog_stats():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT
            COUNT(*) AS total_items,
            SUM(CASE WHEN COALESCE(is_active,1)=1 THEN 1 ELSE 0 END) AS active_items,
            SUM(CASE WHEN COALESCE(is_kit,0)=1 AND COALESCE(is_active,1)=1 THEN 1 ELSE 0 END) AS kit_items
        FROM items
    """)
    row = cur.fetchone() or {}
    cur.execute("""
        SELECT COALESCE(SUM(quantity_on_hand), 0) AS total_units
        FROM inventory_batches
    """)
    units = cur.fetchone() or {}
    low = get_low_stock_items()
    return {
        'total_items': int(row.get('total_items') or 0),
        'active_items': int(row.get('active_items') or 0),
        'kit_items': int(row.get('kit_items') or 0),
        'total_units': int(units.get('total_units') or 0),
        'low_stock_count': len(low or []),
    }


def get_item_by_id(item_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT i.*, c.name AS category_name,
               COALESCE((
                   SELECT SUM(b.quantity_on_hand) FROM inventory_batches b WHERE b.item_id = i.id
               ), 0) AS total_stock
        FROM items i
        LEFT JOIN categories c ON i.category_id = c.id
        WHERE i.id = %s
    """, (item_id,))
    return cur.fetchone()


def get_item_stock_by_location(item_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT l.id AS location_id, l.name AS location_name,
               COALESCE(SUM(b.quantity_on_hand), 0) AS qty
        FROM locations l
        LEFT JOIN inventory_batches b
          ON b.location_id = l.id AND b.item_id = %s AND b.quantity_on_hand > 0
        GROUP BY l.id, l.name
        HAVING qty > 0
        ORDER BY l.name
    """, (item_id,))
    return cur.fetchall()


def get_item_transactions(item_id, limit=40):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT t.id, t.transaction_type, t.quantity_change, t.date, t.notes,
               u.username AS user_name, l.name AS location_name
        FROM inventory_transactions t
        JOIN inventory_batches b ON t.batch_id = b.id
        LEFT JOIN locations l ON b.location_id = l.id
        LEFT JOIN users u ON t.user_id = u.id
        WHERE b.item_id = %s
        ORDER BY t.date DESC
        LIMIT %s
    """, (item_id, int(limit)))
    return cur.fetchall()


def create_item(data):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO items
            (name, description, category_id, barcode_upc_ean, sku, pack_quantity,
             unit_of_measure, typical_cost_per_unit, min_stock_level, max_stock_level,
             is_perishable, shelf_life_days, notes, preferred_vendor_id,
             is_kit, is_active, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['name'],
            data.get('description'),
            data['category_id'],
            data.get('barcode'),
            data.get('sku'),
            data.get('pack_quantity'),
            data.get('unit') or 'each',
            data.get('typical_cost'),
            data.get('min_stock_level'),
            data.get('max_stock_level'),
            data.get('is_perishable') or 0,
            data.get('shelf_life_days'),
            data.get('notes'),
            data.get('preferred_vendor_id'),
            data.get('is_kit') or 0,
            data.get('is_active', 1),
            data.get('created_by'),
        ))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def update_item(item_id, data):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE items
            SET name=%s, description=%s, category_id=%s, barcode_upc_ean=%s, sku=%s,
                pack_quantity=%s, unit_of_measure=%s, typical_cost_per_unit=%s,
                min_stock_level=%s, max_stock_level=%s, is_perishable=%s,
                shelf_life_days=%s, notes=%s, preferred_vendor_id=%s,
                is_kit=%s, is_active=%s
            WHERE id=%s
        """, (
            data['name'],
            data.get('description'),
            data['category_id'],
            data.get('barcode'),
            data.get('sku'),
            data.get('pack_quantity'),
            data.get('unit') or 'each',
            data.get('typical_cost'),
            data.get('min_stock_level'),
            data.get('max_stock_level'),
            data.get('is_perishable') or 0,
            data.get('shelf_life_days'),
            data.get('notes'),
            data.get('preferred_vendor_id'),
            data.get('is_kit') or 0,
            data.get('is_active', 1),
            item_id,
        ))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def set_item_active(item_id, active=True):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE items SET is_active = %s WHERE id = %s", (1 if active else 0, item_id))
    db.commit()


# ----- Kits / sets (bill of materials) -----

def get_kit_components(kit_item_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT kc.id, kc.kit_item_id, kc.component_item_id, kc.quantity, kc.notes, kc.sort_order,
               i.name AS component_name, i.unit_of_measure AS unit,
               i.sku AS component_sku,
               COALESCE((
                   SELECT SUM(b.quantity_on_hand) FROM inventory_batches b
                   WHERE b.item_id = kc.component_item_id
               ), 0) AS stock_on_hand
        FROM item_kit_components kc
        JOIN items i ON i.id = kc.component_item_id
        WHERE kc.kit_item_id = %s
        ORDER BY kc.sort_order, i.name
    """, (kit_item_id,))
    rows = cur.fetchall() or []
    for r in rows:
        r['quantity'] = int(r.get('quantity') or 1)
        r['stock_on_hand'] = int(r.get('stock_on_hand') or 0)
        need = r['quantity'] or 1
        r['assemblable'] = r['stock_on_hand'] // need if need else 0
    return rows


def kit_assemblable_count(kit_item_id):
    comps = get_kit_components(kit_item_id)
    if not comps:
        return 0
    return min(c['assemblable'] for c in comps)


def save_kit_component(kit_item_id, component_item_id, quantity=1, notes=None):
    if int(kit_item_id) == int(component_item_id):
        raise ValueError('A kit cannot include itself as a component.')
    qty = max(1, int(quantity or 1))
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO item_kit_components (kit_item_id, component_item_id, quantity, notes)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE quantity = VALUES(quantity), notes = VALUES(notes)
        """, (kit_item_id, component_item_id, qty, notes))
        # Ensure parent marked as kit
        cur.execute("UPDATE items SET is_kit = 1 WHERE id = %s", (kit_item_id,))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def remove_kit_component(kit_item_id, component_row_id):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "DELETE FROM item_kit_components WHERE id = %s AND kit_item_id = %s",
        (component_row_id, kit_item_id),
    )
    db.commit()
    return cur.rowcount > 0


def deploy_kit(kit_item_id, kits_count, user_id, location_id=None, notes=None):
    """
    Consume components for N kits via FIFO use transactions.
    Returns dict with kits_deployed and component lines used.
    """
    kits_count = int(kits_count)
    if kits_count <= 0:
        raise ValueError('Quantity of kits must be positive.')

    comps = get_kit_components(kit_item_id)
    if not comps:
        raise ValueError('This kit has no components. Add items to the set first.')

    can_build = kit_assemblable_count(kit_item_id)
    if location_id:
        # Recompute availability filtered by location
        can_build = None
        for c in comps:
            batches = get_batches_for_item(c['component_item_id'])
            batches = [b for b in batches if int(b['location_id']) == int(location_id)]
            avail = sum(int(b['quantity_on_hand']) for b in batches)
            n = avail // c['quantity'] if c['quantity'] else 0
            can_build = n if can_build is None else min(can_build, n)
        can_build = can_build or 0

    if can_build < kits_count:
        raise ValueError(
            f'Only enough stock to deploy {can_build} kit(s). '
            f'Receive more components or lower the quantity.'
        )

    kit = get_item_by_id(kit_item_id)
    kit_name = (kit or {}).get('name') or f'Kit #{kit_item_id}'
    note_base = notes or f'Deploy kit: {kit_name} ×{kits_count}'

    for c in comps:
        need = c['quantity'] * kits_count
        use_or_discard_stock(
            item_id=c['component_item_id'],
            quantity=need,
            transaction_type='use',
            notes=f"{note_base} · {c['component_name']}",
            user_id=user_id,
            location_id=location_id,
        )
    return {'kits_deployed': kits_count, 'components': comps}


def _to_decimal(val):
    if val is None or val == '':
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return None


def receive_stock_batch(item_id, location_id, quantity, purchase_date, expiration_date,
                        cost_per_unit, notes, user_id, transaction_type='receive'):
    """Create a batch and inbound transaction (receive / adjust / return / transfer)."""
    db = get_db()
    cur = db.cursor()
    now = utc_now()
    cost = _to_decimal(cost_per_unit)
    total = (cost * Decimal(quantity)) if cost is not None else None
    txn = transaction_type if transaction_type in (
        'receive', 'adjust', 'use', 'discard', 'transfer', 'return'
    ) else 'receive'

    try:
        cur.execute("""
            INSERT INTO inventory_batches
            (item_id, location_id, quantity_on_hand, purchase_date, expiration_date,
             cost_per_unit, total_cost, notes, received_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            item_id, location_id, quantity, purchase_date, expiration_date,
            cost, total, notes, user_id,
        ))
        batch_id = cur.lastrowid

        cur.execute("""
            INSERT INTO inventory_transactions
            (batch_id, transaction_type, quantity_change, user_id, notes, date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (batch_id, txn, quantity, user_id, notes, now))

        db.commit()
        return batch_id
    except Exception:
        db.rollback()
        raise


def get_batches_for_item(item_id):
    """Batches with remaining stock (FIFO order by purchase/expiration)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT b.*, l.name AS location_name
        FROM inventory_batches b
        JOIN locations l ON b.location_id = l.id
        WHERE b.item_id = %s AND b.quantity_on_hand > 0
        ORDER BY
            CASE WHEN b.expiration_date IS NULL THEN 1 ELSE 0 END,
            b.expiration_date ASC,
            b.id ASC
    """, (item_id,))
    return cur.fetchall()


def adjust_batch_stock(batch_id, quantity_change, transaction_type, notes, user_id):
    """
    Apply a stock change to a batch.
    quantity_change: signed int (negative for use/discard).
    transaction_type: receive|adjust|use|discard|transfer|return
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    now = utc_now()

    try:
        cur.execute(
            "SELECT id, quantity_on_hand FROM inventory_batches WHERE id = %s",
            (batch_id,),
        )
        batch = cur.fetchone()
        if not batch:
            raise ValueError('Batch not found')

        new_qty = int(batch['quantity_on_hand']) + int(quantity_change)
        if new_qty < 0:
            raise ValueError('Insufficient quantity on batch')

        cur.execute(
            "UPDATE inventory_batches SET quantity_on_hand = %s WHERE id = %s",
            (new_qty, batch_id),
        )
        cur.execute("""
            INSERT INTO inventory_transactions
            (batch_id, transaction_type, quantity_change, user_id, notes, date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (batch_id, transaction_type, quantity_change, user_id, notes, now))
        db.commit()
        return new_qty
    except Exception:
        db.rollback()
        raise


def use_or_discard_stock(item_id, quantity, transaction_type, notes, user_id, location_id=None):
    """FIFO consume from batches (use or discard)."""
    if transaction_type not in ('use', 'discard'):
        raise ValueError('Invalid transaction type')
    remaining = int(quantity)
    if remaining <= 0:
        raise ValueError('Quantity must be positive')

    batches = get_batches_for_item(item_id)
    if location_id:
        batches = [b for b in batches if int(b['location_id']) == int(location_id)]

    total_available = sum(int(b['quantity_on_hand']) for b in batches)
    if total_available < remaining:
        raise ValueError(f'Only {total_available} units available')

    for batch in batches:
        if remaining <= 0:
            break
        take = min(int(batch['quantity_on_hand']), remaining)
        adjust_batch_stock(
            batch['id'],
            -take,
            transaction_type,
            notes,
            user_id,
        )
        remaining -= take
    return True


def adjust_stock(item_id, quantity_delta, notes, user_id, location_id=None):
    """
    Positive delta: receive as a simple adjustment batch (needs location).
    Negative delta: FIFO consume with type 'adjust'.
    """
    delta = int(quantity_delta)
    if delta == 0:
        raise ValueError('Adjustment cannot be zero.')
    if delta > 0:
        if not location_id:
            raise ValueError('Location is required when adding stock via adjust.')
        return receive_stock_batch(
            item_id=item_id,
            location_id=location_id,
            quantity=delta,
            purchase_date=None,
            expiration_date=None,
            cost_per_unit=None,
            notes=notes or 'Stock adjustment (+)',
            user_id=user_id,
            transaction_type='adjust',
        )
    # consume
    remaining = abs(delta)
    batches = get_batches_for_item(item_id)
    if location_id:
        batches = [b for b in batches if int(b['location_id']) == int(location_id)]
    total_available = sum(int(b['quantity_on_hand']) for b in batches)
    if total_available < remaining:
        raise ValueError(f'Only {total_available} units available to remove')
    for batch in batches:
        if remaining <= 0:
            break
        take = min(int(batch['quantity_on_hand']), remaining)
        adjust_batch_stock(batch['id'], -take, 'adjust', notes or 'Stock adjustment (−)', user_id)
        remaining -= take
    return True


def transfer_stock(item_id, quantity, from_location_id, to_location_id, notes, user_id):
    """Move quantity from one location to another (FIFO out, receive in)."""
    qty = int(quantity)
    if qty <= 0:
        raise ValueError('Quantity must be positive.')
    if int(from_location_id) == int(to_location_id):
        raise ValueError('Source and destination locations must differ.')

    batches = [
        b for b in get_batches_for_item(item_id)
        if int(b['location_id']) == int(from_location_id)
    ]
    available = sum(int(b['quantity_on_hand']) for b in batches)
    if available < qty:
        raise ValueError(f'Only {available} units at source location.')

    remaining = qty
    note = notes or 'Transfer between locations'
    for batch in batches:
        if remaining <= 0:
            break
        take = min(int(batch['quantity_on_hand']), remaining)
        adjust_batch_stock(batch['id'], -take, 'transfer', f'{note} (out)', user_id)
        remaining -= take

    receive_stock_batch(
        item_id=item_id,
        location_id=to_location_id,
        quantity=qty,
        purchase_date=None,
        expiration_date=None,
        cost_per_unit=None,
        notes=f'{note} (in)',
        user_id=user_id,
        transaction_type='transfer',
    )
    return True


def get_stock_snapshot():
    """System stock by item for audit report."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT i.id, i.name, i.unit_of_measure AS unit, i.sku,
               i.min_stock_level, COALESCE(i.is_kit, 0) AS is_kit,
               COALESCE(SUM(b.quantity_on_hand), 0) AS current
        FROM items i
        LEFT JOIN inventory_batches b ON b.item_id = i.id
        WHERE COALESCE(i.is_active, 1) = 1
        GROUP BY i.id, i.name, i.unit_of_measure, i.sku, i.min_stock_level, i.is_kit
        ORDER BY i.name
    """)
    return cur.fetchall()


def log_barcode_scan(barcode, user_id, resolved_item_id, status):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO barcode_scans (barcode, user_id, resolved_item_id, status)
            VALUES (%s, %s, %s, %s)
        """, (barcode, user_id, resolved_item_id, status))
        db.commit()
    except Exception:
        db.rollback()


def add_category(name, description=None):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            "INSERT INTO categories (name, description) VALUES (%s, %s)",
            (name, description),
        )
    except Exception:
        cur.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
    db.commit()
    return cur.lastrowid


def add_location(name, building_area=None):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            "INSERT INTO locations (name, building_area) VALUES (%s, %s)",
            (name, building_area),
        )
    except Exception:
        cur.execute("INSERT INTO locations (name) VALUES (%s)", (name,))
    db.commit()
    return cur.lastrowid


def get_categories():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id, name, description FROM categories ORDER BY name")
    try:
        return cur.fetchall()
    except Exception:
        cur.execute("SELECT id, name FROM categories ORDER BY name")
        return cur.fetchall()


def get_locations():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id, name, building_area FROM locations ORDER BY name")
    try:
        return cur.fetchall()
    except Exception:
        cur.execute("SELECT id, name FROM locations ORDER BY name")
        return cur.fetchall()


def get_vendors():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute("SELECT id, name FROM vendors ORDER BY name")
        return cur.fetchall() or []
    except Exception:
        return []


def get_item_by_barcode(code):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT * FROM items WHERE barcode_upc_ean = %s OR sku = %s",
        (code, code),
    )
    return cur.fetchone()


def ensure_inventory_ready():
    """
    Idempotent: ensure kit table, item columns, and starter categories/locations.
    Safe to call from first page load if builddb not re-run.
    """
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS item_kit_components (
                id                 INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
                kit_item_id        INT UNSIGNED NOT NULL,
                component_item_id  INT UNSIGNED NOT NULL,
                quantity           INT UNSIGNED NOT NULL DEFAULT 1,
                notes              VARCHAR(255) NULL,
                sort_order         INT NOT NULL DEFAULT 0,
                UNIQUE KEY uq_kit_component (kit_item_id, component_item_id)
            ) ENGINE=InnoDB
        """)
        for col, ddl in [
            ('sku', "VARCHAR(64) NULL"),
            ('is_active', "TINYINT(1) NOT NULL DEFAULT 1"),
            ('is_kit', "TINYINT(1) NOT NULL DEFAULT 0"),
            ('description', "TEXT NULL"),
        ]:
            try:
                cur.execute(f"ALTER TABLE items ADD COLUMN {col} {ddl}")
            except Exception:
                pass

        cur.execute("SELECT COUNT(*) AS c FROM categories")
        row = cur.fetchone()
        n = row[0] if isinstance(row, (list, tuple)) else (row or {}).get('c', 0)
        if not n:
            for name in (
                'Office supplies', 'Cleaning & facilities', 'Kitchen & hospitality',
                'Communion / worship', 'Children & nursery', 'Youth ministry',
                'AV / tech', 'First aid & safety', 'Events & outreach',
                'Curriculum & print', 'Maintenance / tools', 'Kits & sets',
            ):
                try:
                    cur.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
                except Exception:
                    pass

        cur.execute("SELECT COUNT(*) AS c FROM locations")
        row = cur.fetchone()
        n = row[0] if isinstance(row, (list, tuple)) else (row or {}).get('c', 0)
        if not n:
            for name, area in (
                ('Main storage', 'Building'),
                ('Kitchen pantry', 'Kitchen'),
                ('Nursery closet', 'Children'),
                ('AV booth', 'Sanctuary'),
                ('Office supply closet', 'Office'),
                ('Janitor closet', 'Facilities'),
            ):
                try:
                    cur.execute(
                        "INSERT INTO locations (name, building_area) VALUES (%s, %s)",
                        (name, area),
                    )
                except Exception:
                    try:
                        cur.execute("INSERT INTO locations (name) VALUES (%s)", (name,))
                    except Exception:
                        pass

        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
