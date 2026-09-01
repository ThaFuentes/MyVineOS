# Form validation for Inventory module.

from flask import flash
from app.utils.helpers import contains_censored_word


def _int_or_none(val):
    if val is None or val == '':
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _float_or_none(val):
    if val is None or val == '':
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def validate_item_form(form_data):
    """Validate add/edit item form."""
    name = form_data.get('name', '').strip()
    category_id = form_data.get('category_id')
    barcode = form_data.get('barcode_upc_ean', '').strip() or None
    sku = form_data.get('sku', '').strip() or None
    pack_quantity = _int_or_none(form_data.get('pack_quantity'))
    unit = (form_data.get('unit_of_measure') or 'each').strip() or 'each'
    min_stock_level = _int_or_none(form_data.get('min_stock_level'))
    max_stock_level = _int_or_none(form_data.get('max_stock_level'))
    is_perishable = 1 if form_data.get('is_perishable') in ('1', 'on', True, 1) else 0
    is_kit = 1 if form_data.get('is_kit') in ('1', 'on', True, 1) else 0
    is_active = 0 if form_data.get('is_active') in ('0', 'off', False, 0) else 1
    # checkbox present means active when editing with name is_active value=1
    if 'is_active' in form_data:
        is_active = 1 if form_data.get('is_active') in ('1', 'on', True, 1) else 0
    shelf_life_days = _int_or_none(form_data.get('shelf_life_days'))
    notes = form_data.get('notes', '').strip() or None
    description = form_data.get('description', '').strip() or None
    preferred_vendor_id = _int_or_none(form_data.get('preferred_vendor_id'))
    typical_cost = _float_or_none(form_data.get('typical_cost_per_unit'))

    if not name or not category_id:
        flash('Name and category are required.', 'error')
        return None

    for field in (name, notes or '', description or '', unit):
        if field and contains_censored_word(field):
            flash('Item contains prohibited content.', 'error')
            return None

    try:
        category_id = int(category_id)
    except (TypeError, ValueError):
        flash('Invalid category.', 'error')
        return None

    return {
        'name': name,
        'description': description,
        'category_id': category_id,
        'barcode': barcode,
        'sku': sku,
        'pack_quantity': pack_quantity,
        'unit': unit,
        'min_stock_level': min_stock_level,
        'max_stock_level': max_stock_level,
        'is_perishable': is_perishable,
        'is_kit': is_kit,
        'is_active': is_active,
        'shelf_life_days': shelf_life_days,
        'notes': notes,
        'preferred_vendor_id': preferred_vendor_id,
        'typical_cost': typical_cost,
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
        item_id = int(item_id)
        location_id = int(location_id)
    except (ValueError, TypeError):
        flash('Quantity must be a valid number.', 'error')
        return None

    notes = form_data.get('notes', '').strip()
    if notes and contains_censored_word(notes):
        flash('Notes contain prohibited content.', 'error')
        return None

    return {
        'item_id': item_id,
        'location_id': location_id,
        'quantity': quantity,
        'purchase_date': form_data.get('purchase_date') or None,
        'expiration_date': form_data.get('expiration_date') or None,
        'cost_per_unit': form_data.get('cost_per_unit') or None,
        'notes': notes,
    }


def validate_category_form(form_data):
    name = form_data.get('cat_name', '').strip()
    if not name:
        flash('Category name is required.', 'error')
        return None
    if contains_censored_word(name):
        flash('Category name contains prohibited content.', 'error')
        return None
    return name


def validate_location_form(form_data):
    name = form_data.get('loc_name', '').strip()
    if not name:
        flash('Location name is required.', 'error')
        return None
    if contains_censored_word(name):
        flash('Location name contains prohibited content.', 'error')
        return None
    return name


def validate_stock_move_form(form_data):
    """Validate use / discard / adjust / transfer form."""
    item_id = form_data.get('item_id')
    quantity = form_data.get('quantity')
    transaction_type = (form_data.get('transaction_type') or '').strip().lower()
    location_id = form_data.get('location_id') or None
    to_location_id = form_data.get('to_location_id') or None
    notes = (form_data.get('notes') or '').strip()
    # signed quantity for adjust: use adjust_sign
    adjust_sign = (form_data.get('adjust_sign') or 'remove').strip().lower()

    if transaction_type not in ('use', 'discard', 'adjust', 'transfer'):
        flash('Choose a stock action (use, discard, adjust, or transfer).', 'error')
        return None
    if not item_id or not quantity:
        flash('Item and quantity are required.', 'error')
        return None
    try:
        quantity = int(quantity)
        if quantity <= 0:
            flash('Quantity must be greater than 0.', 'error')
            return None
        item_id = int(item_id)
        if location_id:
            location_id = int(location_id)
        if to_location_id:
            to_location_id = int(to_location_id)
    except (ValueError, TypeError):
        flash('Invalid item or quantity.', 'error')
        return None

    if transaction_type == 'transfer':
        if not location_id or not to_location_id:
            flash('Transfer requires both from and to locations.', 'error')
            return None
    if transaction_type == 'adjust' and adjust_sign == 'add' and not location_id:
        flash('Choose a location when adding stock via adjust.', 'error')
        return None

    if notes and contains_censored_word(notes):
        flash('Notes contain prohibited content.', 'error')
        return None

    quantity_delta = quantity
    if transaction_type == 'adjust' and adjust_sign != 'add':
        quantity_delta = -quantity

    return {
        'item_id': item_id,
        'quantity': quantity,
        'quantity_delta': quantity_delta,
        'transaction_type': transaction_type,
        'location_id': location_id,
        'to_location_id': to_location_id,
        'notes': notes,
    }


def validate_kit_component_form(form_data):
    component_item_id = form_data.get('component_item_id')
    quantity = form_data.get('quantity') or 1
    notes = (form_data.get('notes') or '').strip() or None
    try:
        component_item_id = int(component_item_id)
        quantity = max(1, int(quantity))
    except (TypeError, ValueError):
        flash('Pick a component item and quantity.', 'error')
        return None
    return {
        'component_item_id': component_item_id,
        'quantity': quantity,
        'notes': notes,
    }


def validate_deploy_kit_form(form_data):
    quantity = form_data.get('quantity') or 1
    location_id = form_data.get('location_id') or None
    notes = (form_data.get('notes') or '').strip() or None
    try:
        quantity = int(quantity)
        if quantity <= 0:
            raise ValueError()
        if location_id:
            location_id = int(location_id)
    except (TypeError, ValueError):
        flash('Enter how many kits to deploy.', 'error')
        return None
    return {'quantity': quantity, 'location_id': location_id, 'notes': notes}
