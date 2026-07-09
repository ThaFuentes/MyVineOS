# app/routes/inventory/queries.py
# Full path: MyVineChurch/app/routes/inventory/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Inventory module.
# - Pure data-access layer - no Flask routes, no templates, no flash messages.
# - 100% MariaDB/pymysql compatible (%s placeholders, DictCursor).
# - Every query from the original inventory.py is here with exact same logic.

import pymysql
from datetime import datetime, timedelta
from app.models.db import get_db


# ----------------------------------------------------------------------
# Dashboard Queries
# ----------------------------------------------------------------------
def get_low_stock_items():
    """Return low stock alerts."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT i.id, i.name, i.min_stock_level, COALESCE(SUM(b.quantity_on_hand), 0) AS total_stock
        FROM items i
        LEFT JOIN inventory_batches b ON b.item_id = i.id
        GROUP BY i.id
        HAVING total_stock < i.min_stock_level OR (i.min_stock_level IS NOT NULL AND total_stock = 0)
        ORDER BY total_stock ASC
        LIMIT 20
    """)
    return cur.fetchall()


def get_expiring_items(days=30):
    """Return items expiring soon."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    expire_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
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
    """Return recent inventory transactions."""
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


# ----------------------------------------------------------------------
# Items Catalog
# ----------------------------------------------------------------------
def get_items_list(search=''):
    """Return items list with optional search."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT i.*, c.name AS category_name,
               COALESCE(SUM(b.quantity_on_hand), 0) AS total_stock
        FROM items i
        LEFT JOIN categories c ON i.category_id = c.id
        LEFT JOIN inventory_batches b ON b.item_id = i.id
    """
    params = []

    if search:
        like = f"%{search}%"
        sql += " WHERE i.name LIKE %s OR i.barcode_upc_ean = %s OR c.name LIKE %s"
        params = [like, search, like]

    sql += " GROUP BY i.id ORDER BY i.name"
    cur.execute(sql, params)
    return cur.fetchall()


# ----------------------------------------------------------------------
# Add/Edit Item
# ----------------------------------------------------------------------
def create_item(data):
    """Insert new item."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO items
            (name, category_id, barcode_upc_ean, pack_quantity, unit_of_measure,
             min_stock_level, is_perishable, shelf_life_days, notes,
             preferred_vendor_id, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['name'], data['category_id'], data['barcode'], data['pack_quantity'],
            data['unit'], data['min_stock_level'], data['is_perishable'],
            data['shelf_life_days'], data['notes'], data['preferred_vendor_id'],
            data['created_by']
        ))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def update_item(item_id, data):
    """Update existing item."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE items
            SET name=%s, category_id=%s, barcode_upc_ean=%s, pack_quantity=%s,
                unit_of_measure=%s, min_stock_level=%s, is_perishable=%s,
                shelf_life_days=%s, notes=%s, preferred_vendor_id=%s
            WHERE id=%s
        """, (
            data['name'], data['category_id'], data['barcode'], data['pack_quantity'],
            data['unit'], data['min_stock_level'], data['is_perishable'],
            data['shelf_life_days'], data['notes'], data['preferred_vendor_id'],
            item_id
        ))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------------
# Receive Stock
# ----------------------------------------------------------------------
def receive_stock(item_id, location_id, quantity, purchase_date, expiration_date, cost_per_unit, notes, user_id):
    """Receive stock batch and log transaction."""
    db = get_db()
    cur = db.cursor()
    received_at = datetime.now().isoformat()

    try:
        cur.execute("""
            INSERT INTO inventory_batches
            (item_id, location_id, quantity_on_hand, purchase_date, expiration_date,
             cost_per_unit, total_cost, notes, received_by, received_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s * %s, %s, %s, %s)
        """, (item_id, location_id, quantity, purchase_date, expiration_date,
              cost_per_unit, quantity, notes, user_id, received_at))
        batch_id = cur.lastrowid

        cur.execute("""
            INSERT INTO inventory_transactions
            (batch_id, transaction_type, quantity_change, user_id, notes, date)
            VALUES (%s, 'receive', %s, %s, %s, %s)
        """, (batch_id, quantity, user_id, notes, received_at))

        db.commit()
        return batch_id
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------------
# Categories & Locations
# ----------------------------------------------------------------------
def add_category(name):
    """Add new category."""
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
    db.commit()
    return cur.lastrowid


def add_location(name):
    """Add new location."""
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO locations (name) VALUES (%s)", (name,))
    db.commit()
    return cur.lastrowid


def get_categories():
    """Return all categories."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id, name FROM categories ORDER BY name")
    return cur.fetchall()


def get_locations():
    """Return all locations."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id, name FROM locations ORDER BY name")
    return cur.fetchall()


# ----------------------------------------------------------------------
# Barcode Lookup
# ----------------------------------------------------------------------
def get_item_by_barcode(code):
    """Return item from local database by barcode."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM items WHERE barcode_upc_ean = %s", (code,))
    return cur.fetchone()