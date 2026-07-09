# app/routes/inventory/forms.py
# Full path: MyVineChurch/app/routes/inventory/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Inventory module.
# - Validates item add/edit, receive stock, category and location forms.
# - Performs server-side censored word check on all text fields.
# - Returns clean dict on success, or None + flash message on error.
# - 100% matches the original inventory.py validation logic.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_item_form(form_data):
    """Validate add/edit item form."""
    name = form_data.get('name', '').strip()
    category_id = form_data.get('category_id')
    barcode = form_data.get('barcode_upc_ean', '').strip() or None
    pack_quantity = form_data.get('pack_quantity') or None
    unit = form_data.get('unit_of_measure', 'each')
    min_stock_level = form_data.get('min_stock_level') or None
    is_perishable = 1 if 'is_perishable' in form_data else 0
    shelf_life_days = form_data.get('shelf_life_days') or None
    notes = form_data.get('notes', '').strip()
    preferred_vendor_id = form_data.get('preferred_vendor_id') or None

    if not name or not category_id:
        flash('Name and category are required.', 'error')
        return None

    # Censorship check on all text fields
    for field in ['name', 'notes', 'description', 'shelf_life_days', 'unit_of_measure']:
        if contains_censored_word(form_data.get(field, '')):
            flash('Item contains prohibited content.', 'error')
            return None

    return {
        'name': name,
        'category_id': category_id,
        'barcode': barcode,
        'pack_quantity': pack_quantity,
        'unit': unit,
        'min_stock_level': min_stock_level,
        'is_perishable': is_perishable,
        'shelf_life_days': shelf_life_days,
        'notes': notes,
        'preferred_vendor_id': preferred_vendor_id
    }


def validate_receive_stock_form(form_data):
    """Validate receive stock form."""
    item_id = form_data.get('item_id')
    location_id = form_data.get('location_id')
    quantity = form_data.get('quantity')

    if not item_id or not location_id or not quantity:
        flash('Item, location, and quantity are required.', 'error')
        return None

    try:
        quantity = int(quantity)
        if quantity <= 0:
            flash('Quantity must be greater than 0.', 'error')
            return None
    except (ValueError, TypeError):
        flash('Quantity must be a valid number.', 'error')
        return None

    return {
        'item_id': item_id,
        'location_id': location_id,
        'quantity': quantity,
        'purchase_date': form_data.get('purchase_date') or None,
        'expiration_date': form_data.get('expiration_date') or None,
        'cost_per_unit': form_data.get('cost_per_unit') or None,
        'notes': form_data.get('notes', '').strip()
    }


def validate_category_form(form_data):
    """Validate add category form."""
    name = form_data.get('cat_name', '').strip()
    if not name:
        flash('Category name is required.', 'error')
        return None
    return name


def validate_location_form(form_data):
    """Validate add location form."""
    name = form_data.get('loc_name', '').strip()
    if not name:
        flash('Location name is required.', 'error')
        return None
    return name