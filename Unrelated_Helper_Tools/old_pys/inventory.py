# app/routes/inventory.py
# Full path: WebChurchMan/app/routes/inventory.py
# File name: inventory.py
# Brief, detailed purpose: Clean, fully rebuilt blueprint for inventory management.
# Restricted to Staff/Admin/Owner.
# Features (preserved + enhanced):
#   • Dashboard: low-stock alerts, expiring items, recent transactions
#   • Items catalog with search by name, barcode, OR category name
#   • Add/Edit items with category/vendor dropdowns
#   • Receive stock batches
#   • Barcode lookup (local → external fallback)
#   • NEW: Dedicated page to add Categories & Locations (Kitchen, Sanctuary, etc.)
#   • All queries use ? placeholders (SQLite compatibility)
#   • Consistent use of sqlite3.Row for dict-like access
#   • Full audit logging and flash feedback
#   • Timezone-aware UTC storage with local church time display

import sqlite3
import requests
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify

from app.utils.decorators import login_required, role_required
from app.models.db import get_db
from app.models.log import log_change
from app.utils.time_utils import utc_now, format_church

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')

REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']

UPCITEMDB_TRIAL_URL = "https://api.upcitemdb.com/prod/trial/lookup"


# ----------------------------------------------------------------------
# Helper: Current user ID for logging
# ----------------------------------------------------------------------
def current_user_id():
    return session.get('user_id')


# ----------------------------------------------------------------------
# Dashboard – /inventory/
# ----------------------------------------------------------------------
@inventory_bp.route('/')
@login_required
@role_required(REQUIRED_ROLES)
def inventory_dashboard():
    db = get_db()
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # Low stock alerts
    cur.execute("""
        SELECT i.id, i.name, i.min_stock_level, COALESCE(SUM(b.quantity_on_hand), 0) AS total_stock
        FROM items i
        LEFT JOIN inventory_batches b ON b.item_id = i.id
        GROUP BY i.id
        HAVING total_stock < i.min_stock_level OR (i.min_stock_level IS NOT NULL AND total_stock = 0)
        ORDER BY total_stock ASC
        LIMIT 20
    """)
    low_stock = cur.fetchall()

    # Expiring soon (next 30 days)
    expiring = []
    try:
        expire_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        cur.execute("""
            SELECT i.name, b.expiration_date, b.quantity_on_hand, l.name AS location_name
            FROM inventory_batches b
            JOIN items i ON b.item_id = i.id
            JOIN locations l ON b.location_id = l.id
            WHERE b.expiration_date IS NOT NULL
              AND b.expiration_date <= ?
              AND b.quantity_on_hand > 0
            ORDER BY b.expiration_date ASC
            LIMIT 15
        """, (expire_date,))
        expiring = cur.fetchall()

        for row in expiring:
            if row['expiration_date']:
                exp_date = datetime.strptime(row['expiration_date'], '%Y-%m-%d')
                row['formatted_expiration'] = exp_date.strftime('%A, %B %d, %Y')
            else:
                row['formatted_expiration'] = 'No expiration'
    except Exception as e:
        print(f"Expiring items load failed: {e}")

    # Recent transactions (church local time formatting)
    recent_transactions = []
    try:
        cur.execute("""
            SELECT t.id, t.transaction_type, t.quantity_change, t.date, t.notes,
                   i.name AS item_name, u.username AS user_name
            FROM inventory_transactions t
            JOIN inventory_batches b ON t.batch_id = b.id
            JOIN items i ON b.item_id = i.id
            LEFT JOIN users u ON t.user_id = u.id
            ORDER BY t.date DESC
            LIMIT 20
        """)
        recent_transactions = cur.fetchall()

        for row in recent_transactions:
            if row['date']:
                row['formatted_date'] = format_church(row['date'], '%B %d, %Y at %I:%M %p')
            else:
                row['formatted_date'] = 'Unknown date'
    except Exception as e:
        print(f"Recent transactions load failed: {e}")

    return render_template(
        'inventory/gathering_dashboard.html',
        low_stock=low_stock,
        expiring=expiring,
        recent_transactions=recent_transactions
    )


# ----------------------------------------------------------------------
# AJAX Barcode Lookup – /inventory/barcode_lookup?code=XXXX
# ----------------------------------------------------------------------
@inventory_bp.route('/barcode_lookup')
@login_required
@role_required(REQUIRED_ROLES)
def barcode_lookup():
    code = request.args.get('code', '').strip()
    if not code:
        return jsonify({'error': 'No barcode provided'}), 400

    db = get_db()
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # Local DB first
    cur.execute("SELECT * FROM items WHERE barcode_upc_ean = ?", (code,))
    local_item = cur.fetchone()
    if local_item:
        return jsonify({'source': 'local', 'item': dict(local_item)})

    # External fallback
    try:
        resp = requests.get(f"{UPCITEMDB_TRIAL_URL}?upc={code}", timeout=5)
        data = resp.json()
        if data.get('code') == 'OK' and data.get('items'):
            prod = data['items'][0]
            return jsonify({
                'source': 'external',
                'title': prod.get('title', ''),
                'brand': prod.get('brand', ''),
                'description': prod.get('description', ''),
                'images': prod.get('images', []),
                'category': prod.get('category', ''),
                'upc': code
            })
    except Exception as e:
        print(f"External UPC lookup error: {e}")

    return jsonify({'source': 'none', 'message': 'Not found'})


# ----------------------------------------------------------------------
# Items Catalog – /inventory/items (search by name, barcode, or category)
# ----------------------------------------------------------------------
@inventory_bp.route('/items')
@login_required
@role_required(REQUIRED_ROLES)
def items_list():
    search = request.args.get('search', '').strip()
    db = get_db()
    db.row_factory = sqlite3.Row
    cur = db.cursor()

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
        sql += " WHERE i.name LIKE ? OR i.barcode_upc_ean = ? OR c.name LIKE ?"
        params = [like, search, like]

    sql += " GROUP BY i.id ORDER BY i.name"
    cur.execute(sql, params)
    items = cur.fetchall()

    return render_template('inventory/items_list.html', items=items, search=search)


# ----------------------------------------------------------------------
# Add / Edit Item – /inventory/items/add and /inventory/items/edit/<int:item_id>
# ----------------------------------------------------------------------
@inventory_bp.route('/items/add', methods=['GET', 'POST'])
@inventory_bp.route('/items/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@role_required(REQUIRED_ROLES)
def item_manage(item_id=None):
    db = get_db()
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # Dropdown data
    cur.execute("SELECT id, name FROM categories ORDER BY name")
    categories = cur.fetchall()
    cur.execute("SELECT id, name FROM vendors ORDER BY name")
    vendors = cur.fetchall()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category_id = request.form.get('category_id')
        barcode = request.form.get('barcode_upc_ean', '').strip() or None
        pack_qty = request.form.get('pack_quantity') or None
        unit = request.form.get('unit_of_measure', 'each')
        min_stock = request.form.get('min_stock_level') or None
        is_perishable = 1 if 'is_perishable' in request.form else 0

        if not name or not category_id:
            flash('Name and category are required.', 'error')
        else:
            common_fields = (
                name, category_id, barcode, pack_qty, unit, min_stock, is_perishable,
                request.form.get('shelf_life_days') or None,
                request.form.get('notes') or None,
                request.form.get('preferred_vendor_id') or None
            )

            if item_id:  # Edit
                cur.execute("""
                    UPDATE items
                    SET name=?, category_id=?, barcode_upc_ean=?, pack_quantity=?,
                        unit_of_measure=?, min_stock_level=?, is_perishable=?,
                        shelf_life_days=?, notes=?, preferred_vendor_id=?
                    WHERE id=?
                """, (*common_fields, item_id))
                log_change(current_user_id(), 'update', item_id, 'item', 'Updated inventory item')
                flash('Item updated.', 'success')
            else:  # Add
                cur.execute("""
                    INSERT INTO items
                    (name, category_id, barcode_upc_ean, pack_quantity, unit_of_measure,
                     min_stock_level, is_perishable, shelf_life_days, notes,
                     preferred_vendor_id, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (*common_fields, current_user_id()))
                new_id = cur.lastrowid
                log_change(current_user_id(), 'create', new_id, 'item', 'Created new inventory item')
                flash('Item added.', 'success')

            db.commit()
            return redirect(url_for('inventory.items_list'))

    # GET – load item for editing
    item = None
    if item_id:
        cur.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        item = cur.fetchone()
        if not item:
            flash('Item not found.', 'error')
            return redirect(url_for('inventory.items_list'))

    return render_template('inventory/item_form.html', item=item, categories=categories, vendors=vendors)


# ----------------------------------------------------------------------
# Receive Stock – /inventory/receive
# ----------------------------------------------------------------------
@inventory_bp.route('/receive', methods=['GET', 'POST'])
@login_required
@role_required(REQUIRED_ROLES)
def receive_stock():
    db = get_db()
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    cur.execute("SELECT id, name FROM items ORDER BY name")
    items = cur.fetchall()
    cur.execute("SELECT id, name FROM locations ORDER BY name")
    locations = cur.fetchall()

    if request.method == 'POST':
        item_id = request.form.get('item_id')
        location_id = request.form.get('location_id')
        quantity = int(request.form.get('quantity', 0))
        purchase_date = request.form.get('purchase_date') or None
        expiration_date = request.form.get('expiration_date') or None
        cost_per_unit = request.form.get('cost_per_unit') or None
        notes = request.form.get('notes', '').strip()

        if not all([item_id, location_id, quantity > 0]):
            flash('Valid item, location, and quantity required.', 'error')
        else:
            received_at_utc = utc_now()

            cur.execute("""
                INSERT INTO inventory_batches
                (item_id, location_id, quantity_on_hand, purchase_date, expiration_date,
                 cost_per_unit, total_cost, notes, received_by, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ? * ?, ?, ?, ?)
            """, (item_id, location_id, quantity, purchase_date, expiration_date,
                  cost_per_unit, quantity, notes, current_user_id(), received_at_utc))
            batch_id = cur.lastrowid

            cur.execute("""
                INSERT INTO inventory_transactions
                (batch_id, transaction_type, quantity_change, user_id, notes, date)
                VALUES (?, 'receive', ?, ?, ?, ?)
            """, (batch_id, quantity, current_user_id(), notes, received_at_utc))

            log_change(current_user_id(), 'create', batch_id, 'batch', f'Received {quantity} units')
            db.commit()
            flash('Stock received successfully.', 'success')
            return redirect(url_for('inventory.inventory_dashboard'))

    return render_template('inventory/receive_form.html', items=items, locations=locations)


# ----------------------------------------------------------------------
# Add Categories & Locations – /inventory/cat-location
# ----------------------------------------------------------------------
@inventory_bp.route('/cat-location', methods=['GET', 'POST'])
@login_required
@role_required(REQUIRED_ROLES)
def cat_location():
    db = get_db()
    cur = db.cursor()
    user_id = current_user_id()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_category':
            name = request.form.get('cat_name', '').strip()
            if not name:
                flash('Category name is required.', 'error')
            else:
                cur.execute("SELECT COUNT(*) FROM categories WHERE LOWER(name) = LOWER(?)", (name,))
                if cur.fetchone()[0] > 0:
                    flash(f'Category "{name}" already exists.', 'error')
                else:
                    cur.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                    db.commit()
                    log_change(user_id, 'create', cur.lastrowid, 'category', f'Added category "{name}"')
                    flash(f'Category "{name}" added.', 'success')

        elif action == 'add_location':
            name = request.form.get('loc_name', '').strip()
            if not name:
                flash('Location name is required.', 'error')
            else:
                cur.execute("SELECT COUNT(*) FROM locations WHERE LOWER(name) = LOWER(?)", (name,))
                if cur.fetchone()[0] > 0:
                    flash(f'Location "{name}" already exists.', 'error')
                else:
                    cur.execute("INSERT INTO locations (name) VALUES (?)", (name,))
                    db.commit()
                    log_change(user_id, 'create', cur.lastrowid, 'location', f'Added location "{name}"')
                    flash(f'Location "{name}" added.', 'success')

        return redirect(url_for('inventory.cat_location'))

    # Load existing for display
    cur.execute("SELECT id, name FROM categories ORDER BY name")
    categories = cur.fetchall()

    cur.execute("SELECT id, name FROM locations ORDER BY name")
    locations = cur.fetchall()

    return render_template('inventory/add_cat_location.html',
                           categories=categories,
                           locations=locations)


print("Inventory blueprint fully rebuilt and loaded.")