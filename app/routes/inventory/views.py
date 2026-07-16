# Inventory route handlers — catalog, kits/sets, stock ops, audit.

from flask import render_template, request, redirect, url_for, flash, session, jsonify

from . import inventory_bp
from .queries import (
    get_low_stock_items,
    get_expiring_items,
    get_recent_transactions,
    get_items_list,
    get_item_by_id,
    create_item,
    update_item,
    receive_stock_batch,
    use_or_discard_stock,
    adjust_stock,
    transfer_stock,
    add_category,
    add_location,
    get_categories,
    get_locations,
    get_vendors,
    get_item_by_barcode,
    get_stock_snapshot,
    log_barcode_scan,
    get_catalog_stats,
    get_item_stock_by_location,
    get_item_transactions,
    get_batches_for_item,
    get_kit_components,
    kit_assemblable_count,
    save_kit_component,
    remove_kit_component,
    deploy_kit,
    set_item_active,
    ensure_inventory_ready,
)
from .forms import (
    validate_item_form,
    validate_receive_stock_form,
    validate_category_form,
    validate_location_form,
    validate_stock_move_form,
    validate_kit_component_form,
    validate_deploy_kit_form,
)
from .utils import current_user_id, external_barcode_lookup

from app.utils.decorators import login_required, permission_required
from app.models.log import log_change
from app.utils.time_utils import format_church


def _ready():
    try:
        ensure_inventory_ready()
    except Exception as e:
        print(f"Inventory ensure ready: {e}")


@inventory_bp.route('/')
@login_required
@permission_required('manage_inventory')
def inventory_dashboard():
    _ready()
    low_stock = get_low_stock_items()
    expiring = get_expiring_items()
    recent_transactions = get_recent_transactions(25)
    stats = get_catalog_stats()

    for item in expiring:
        exp = item.get('expiration_date')
        item['formatted_expiration'] = (
            format_church(exp, '%b %d, %Y') if exp else 'N/A'
        )
    for t in recent_transactions:
        dt = t.get('date')
        t['formatted_date'] = format_church(dt, '%b %d, %Y %I:%M %p') if dt else 'N/A'

    return render_template(
        'inventory/dashboard.html',
        low_stock=low_stock,
        expiring=expiring,
        recent_transactions=recent_transactions,
        stats=stats,
    )


@inventory_bp.route('/barcode_lookup')
@login_required
@permission_required('manage_inventory')
def barcode_lookup():
    code = request.args.get('code', '').strip()
    if not code:
        return jsonify({'error': 'No barcode provided'}), 400

    local_item = get_item_by_barcode(code)
    if local_item:
        log_barcode_scan(code, current_user_id(), local_item.get('id'), 'found')
        return jsonify({'source': 'local', 'item': dict(local_item)})

    external = external_barcode_lookup(code)
    if external:
        log_barcode_scan(code, current_user_id(), None, 'not_found')
        return jsonify(external)

    log_barcode_scan(code, current_user_id(), None, 'not_found')
    return jsonify({'source': 'none', 'message': 'Not found'})


@inventory_bp.route('/items')
@login_required
@permission_required('manage_inventory')
def items_list():
    _ready()
    search = request.args.get('search', '').strip()
    category_id = request.args.get('category_id') or None
    show = (request.args.get('show') or 'active').strip().lower()
    active_only = show != 'all' and show != 'inactive'
    kits_only = show == 'kits'
    low_stock_only = show == 'low'
    if show == 'inactive':
        active_only = False

    items = get_items_list(
        search=search,
        category_id=category_id,
        active_only=active_only if show != 'inactive' else False,
        kits_only=kits_only,
        low_stock_only=low_stock_only,
    )
    if show == 'inactive':
        items = [i for i in items if not i.get('is_active', 1)]

    # Attach assemblable for kits
    for it in items:
        if it.get('is_kit'):
            try:
                it['assemblable'] = kit_assemblable_count(it['id'])
            except Exception:
                it['assemblable'] = 0

    return render_template(
        'inventory/items_list.html',
        items=items,
        search=search,
        categories=get_categories(),
        category_id=int(category_id) if category_id else None,
        show=show,
        stats=get_catalog_stats(),
    )


@inventory_bp.route('/items/<int:item_id>')
@login_required
@permission_required('manage_inventory')
def item_detail(item_id):
    _ready()
    item = get_item_by_id(item_id)
    if not item:
        flash('Item not found.', 'error')
        return redirect(url_for('inventory.items_list'))

    batches = get_batches_for_item(item_id)
    by_loc = get_item_stock_by_location(item_id)
    history = get_item_transactions(item_id, limit=50)
    for t in history:
        dt = t.get('date')
        t['formatted_date'] = format_church(dt, '%b %d, %Y %I:%M %p') if dt else 'N/A'
    for b in batches:
        exp = b.get('expiration_date')
        b['formatted_expiration'] = format_church(exp, '%b %d, %Y') if exp else '—'

    components = []
    assemblable = 0
    if item.get('is_kit'):
        components = get_kit_components(item_id)
        assemblable = kit_assemblable_count(item_id)

    return render_template(
        'inventory/item_detail.html',
        item=item,
        batches=batches,
        by_location=by_loc,
        history=history,
        components=components,
        assemblable=assemblable,
        locations=get_locations(),
        catalog_items=get_items_list(active_only=True),
    )


@inventory_bp.route('/items/add', methods=['GET', 'POST'])
@inventory_bp.route('/items/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@permission_required('manage_inventory')
def item_manage(item_id=None):
    _ready()
    categories = get_categories()
    vendors = get_vendors()

    if request.method == 'POST':
        clean_data = validate_item_form(request.form)
        if not clean_data:
            item = get_item_by_id(item_id) if item_id else None
            return render_template(
                'inventory/item_form.html',
                item=item,
                categories=categories,
                vendors=vendors,
            )

        clean_data['created_by'] = current_user_id()

        try:
            if item_id:
                update_item(item_id, clean_data)
                log_change(current_user_id(), 'update', item_id, 'item', f"Updated item {clean_data['name']}")
                flash('Item updated.', 'success')
                return redirect(url_for('inventory.item_detail', item_id=item_id))
            else:
                new_id = create_item(clean_data)
                log_change(current_user_id(), 'create', new_id, 'item', f"Created item {clean_data['name']}")
                flash('Item added to catalog.', 'success')
                if clean_data.get('is_kit'):
                    flash('Add components on the item page to build this kit/set.', 'success')
                return redirect(url_for('inventory.item_detail', item_id=new_id))
        except Exception as e:
            flash('Failed to save item.', 'error')
            print(f"Item save error: {e}")

    item = get_item_by_id(item_id) if item_id else None
    if item_id and not item:
        flash('Item not found.', 'error')
        return redirect(url_for('inventory.items_list'))

    return render_template(
        'inventory/item_form.html',
        item=item,
        categories=categories,
        vendors=vendors,
    )


@inventory_bp.route('/items/<int:item_id>/kit', methods=['POST'])
@login_required
@permission_required('manage_inventory')
def kit_component_add(item_id):
    item = get_item_by_id(item_id)
    if not item:
        flash('Item not found.', 'error')
        return redirect(url_for('inventory.items_list'))

    action = request.form.get('action') or 'add'
    if action == 'remove':
        row_id = request.form.get('component_row_id')
        try:
            remove_kit_component(item_id, int(row_id))
            flash('Component removed from set.', 'success')
        except Exception as e:
            flash('Could not remove component.', 'error')
            print(e)
        return redirect(url_for('inventory.item_detail', item_id=item_id))

    if action == 'deploy':
        clean = validate_deploy_kit_form(request.form)
        if not clean:
            return redirect(url_for('inventory.item_detail', item_id=item_id))
        try:
            result = deploy_kit(
                item_id,
                clean['quantity'],
                current_user_id(),
                location_id=clean.get('location_id'),
                notes=clean.get('notes'),
            )
            log_change(
                current_user_id(), 'update', item_id, 'kit',
                f"Deployed kit ×{result['kits_deployed']}",
            )
            flash(f"Deployed {result['kits_deployed']} kit(s) — component stock updated.", 'success')
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash('Failed to deploy kit.', 'error')
            print(e)
        return redirect(url_for('inventory.item_detail', item_id=item_id))

    clean = validate_kit_component_form(request.form)
    if not clean:
        return redirect(url_for('inventory.item_detail', item_id=item_id))
    try:
        # Mark as kit if not already
        if not item.get('is_kit'):
            data = {
                'name': item['name'],
                'description': item.get('description'),
                'category_id': item['category_id'],
                'barcode': item.get('barcode_upc_ean'),
                'sku': item.get('sku'),
                'pack_quantity': item.get('pack_quantity'),
                'unit': item.get('unit_of_measure') or 'each',
                'typical_cost': item.get('typical_cost_per_unit'),
                'min_stock_level': item.get('min_stock_level'),
                'max_stock_level': item.get('max_stock_level'),
                'is_perishable': 1 if item.get('is_perishable') else 0,
                'shelf_life_days': item.get('shelf_life_days'),
                'notes': item.get('notes'),
                'preferred_vendor_id': item.get('preferred_vendor_id'),
                'is_kit': 1,
                'is_active': 1 if item.get('is_active', 1) else 0,
            }
            update_item(item_id, data)
        save_kit_component(
            item_id,
            clean['component_item_id'],
            clean['quantity'],
            clean.get('notes'),
        )
        flash('Component added to set.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash('Could not add component.', 'error')
        print(e)
    return redirect(url_for('inventory.item_detail', item_id=item_id))


@inventory_bp.route('/items/<int:item_id>/archive', methods=['POST'])
@login_required
@permission_required('manage_inventory')
def item_archive(item_id):
    item = get_item_by_id(item_id)
    if not item:
        flash('Item not found.', 'error')
        return redirect(url_for('inventory.items_list'))
    active = request.form.get('active') == '1'
    set_item_active(item_id, active=active)
    flash('Item restored to catalog.' if active else 'Item archived (hidden from active catalog).', 'success')
    return redirect(url_for('inventory.item_detail', item_id=item_id))


@inventory_bp.route('/receive', methods=['GET', 'POST'])
@login_required
@permission_required('manage_inventory')
def receive_stock():
    items = get_items_list(active_only=True)
    locations = get_locations()
    preselect = request.args.get('item_id')

    if request.method == 'POST':
        clean_data = validate_receive_stock_form(request.form)
        if not clean_data:
            return render_template(
                'inventory/receive_form.html',
                items=items,
                locations=locations,
                preselect=preselect,
            )

        try:
            receive_stock_batch(
                item_id=clean_data['item_id'],
                location_id=clean_data['location_id'],
                quantity=clean_data['quantity'],
                purchase_date=clean_data['purchase_date'],
                expiration_date=clean_data['expiration_date'],
                cost_per_unit=clean_data['cost_per_unit'],
                notes=clean_data['notes'],
                user_id=current_user_id(),
            )
            log_change(
                current_user_id(), 'create', clean_data['item_id'], 'batch',
                f'Received {clean_data["quantity"]} units',
            )
            flash('Stock received successfully.', 'success')
            return redirect(url_for('inventory.item_detail', item_id=clean_data['item_id']))
        except Exception as e:
            flash('Failed to receive stock.', 'error')
            print(f"Receive stock error: {e}")

    return render_template(
        'inventory/receive_form.html',
        items=items,
        locations=locations,
        preselect=preselect,
    )


@inventory_bp.route('/stock-move', methods=['GET', 'POST'])
@login_required
@permission_required('manage_inventory')
def stock_move():
    items = get_items_list(active_only=True)
    locations = get_locations()
    preselect = request.args.get('item_id')

    if request.method == 'POST':
        clean_data = validate_stock_move_form(request.form)
        if not clean_data:
            return render_template(
                'inventory/stock_move.html',
                items=items,
                locations=locations,
                preselect=preselect,
            )
        try:
            t = clean_data['transaction_type']
            if t in ('use', 'discard'):
                use_or_discard_stock(
                    item_id=clean_data['item_id'],
                    quantity=clean_data['quantity'],
                    transaction_type=t,
                    notes=clean_data['notes'],
                    user_id=current_user_id(),
                    location_id=clean_data.get('location_id'),
                )
            elif t == 'adjust':
                adjust_stock(
                    item_id=clean_data['item_id'],
                    quantity_delta=clean_data['quantity_delta'],
                    notes=clean_data['notes'],
                    user_id=current_user_id(),
                    location_id=clean_data.get('location_id'),
                )
            elif t == 'transfer':
                transfer_stock(
                    item_id=clean_data['item_id'],
                    quantity=clean_data['quantity'],
                    from_location_id=clean_data['location_id'],
                    to_location_id=clean_data['to_location_id'],
                    notes=clean_data['notes'],
                    user_id=current_user_id(),
                )
            log_change(
                current_user_id(), 'update', clean_data['item_id'], 'stock',
                f"{t} {clean_data['quantity']} units",
            )
            flash(f"Recorded {t} of {clean_data['quantity']}.", 'success')
            return redirect(url_for('inventory.item_detail', item_id=clean_data['item_id']))
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash('Failed to update stock.', 'error')
            print(f"Stock move error: {e}")

    return render_template(
        'inventory/stock_move.html',
        items=items,
        locations=locations,
        preselect=preselect,
    )


@inventory_bp.route('/cat-location', methods=['GET', 'POST'])
@login_required
@permission_required('manage_inventory')
def cat_location():
    _ready()
    categories = get_categories()
    locations = get_locations()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_category':
            name = validate_category_form(request.form)
            if name:
                add_category(name)
                log_change(current_user_id(), 'create', None, 'category', f'Added category "{name}"')
                flash(f'Category "{name}" added.', 'success')

        elif action == 'add_location':
            name = validate_location_form(request.form)
            if name:
                area = (request.form.get('building_area') or '').strip() or None
                add_location(name, building_area=area)
                log_change(current_user_id(), 'create', None, 'location', f'Added location "{name}"')
                flash(f'Location "{name}" added.', 'success')

        return redirect(url_for('inventory.cat_location'))

    return render_template(
        'inventory/add_cat_location.html',
        categories=categories,
        locations=locations,
    )


@inventory_bp.route('/scan')
@login_required
@permission_required('manage_inventory')
def scan():
    return render_template(
        'inventory/scan.html',
        mode=request.args.get('mode', 'lookup'),
        categories=get_categories(),
    )


@inventory_bp.route('/audit')
@login_required
@permission_required('manage_inventory')
def audit_report():
    snapshot = get_stock_snapshot()
    report = []
    for row in snapshot:
        current = int(row['current'] or 0)
        min_lvl = row.get('min_stock_level')
        report.append({
            'id': row['id'],
            'name': row['name'],
            'sku': row.get('sku'),
            'unit': row.get('unit') or 'each',
            'counted': current,
            'current': current,
            'min_stock_level': min_lvl,
            'is_kit': row.get('is_kit'),
            'discrepancy': 0,
            'status': (
                'low' if min_lvl is not None and current < int(min_lvl)
                else ('out' if current <= 0 and not row.get('is_kit') else 'ok')
            ),
        })
    return render_template('inventory/audit_report.html', report=report)


@inventory_bp.route('/clear_audit', methods=['POST'])
@login_required
@permission_required('manage_inventory')
def clear_audit():
    flash('Audit view refreshed from live stock (system counts unchanged).', 'success')
    return redirect(url_for('inventory.audit_report'))
