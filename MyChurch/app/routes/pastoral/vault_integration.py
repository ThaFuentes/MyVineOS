# app/routes/pastoral/vault_integration.py
# Full path: WebChurchMan/app/routes/pastoral/vault_integration.py
# File name: vault_integration.py
# Brief, detailed purpose:
#   Dedicated blueprint for seamless sermon section  Vault integration endpoints.
#   Provides:
#     - POST /vault/integration/quick_save   -> Quick-save current sermon section as a new Vault item (private or shared)
#     - GET  /vault/integration/search       -> Live search across visible Vault items (My Vault / Shared / All tabs)
#   All routes require membership in the Pastoral Group (@pastoral_required).
#   Enforces censorship checks on all text fields.
#   Audit-logs quick-save actions.
#   Fully compatible with the updated pastoral_vault schema (title required, section_type, scripture_reference, source_url, visibility ENUM).
#   Designed to be called via AJAX from sermon_editor.html (Save to Vault modal and Insert from Vault modal).

from flask import Blueprint, request, jsonify, session
import json

from . import pastoral_required  # From app/routes/pastoral/__init__.py
from app.models.pastoral.vault import add_vault_item, search_vault_and_sermons
from app.models.log import log_change
from app.utils.helpers import contains_censored_word

vault_integration_bp = Blueprint(
    'vault_integration',
    __name__,
    url_prefix='/vault/integration'
)


def _collect_all_text(data: dict) -> str:
    """
    Combine every text field that could contain user input for a single censorship scan.
    """
    fields = [
        data.get('title', ''),
        data.get('content', ''),
        data.get('scripture_reference', ''),
        data.get('source_url', ''),
        data.get('reference', ''),      # legacy field
        data.get('notes', ''),
        data.get('tags', '')
    ]
    return ' '.join(fields)


@vault_integration_bp.route('/quick_save', methods=['POST'])
@pastoral_required()
def quick_save():
    """
    Quick-save the current sermon section as a new Vault item.
    Expected JSON payload:
    {
        "title": str,
        "content": str (HTML from Quill),
        "section_type": str,
        "scripture_reference": str | null,
        "source_url": str | null,
        "reference": str | null,           # legacy free-text
        "notes": str | null,
        "tags": str (comma-separated),
        "visibility": "private" | "pastoral_group"
    }
    """
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}

    if not data.get('title') or not data.get('content'):
        return jsonify({'status': 'error', 'message': 'Title and content are required'}), 400

    # Censorship check - block prohibited words/phrases
    if contains_censored_word(_collect_all_text(data)):
        return jsonify({'status': 'error', 'message': 'Prohibited content detected'}), 400

    visibility = data.get('visibility', 'private')
    if visibility not in ('private', 'pastoral_group'):
        return jsonify({'status': 'error', 'message': 'Invalid visibility'}), 400

    owner_id = user_id if visibility == 'private' else None

    tags_list = [t.strip() for t in data.get('tags', '').split(',') if t.strip()]
    tags_json = json.dumps(tags_list)

    vault_data = {
        'title': data['title'],
        'content': data['content'],
        'section_type': data.get('section_type', 'point'),
        'scripture_reference': data.get('scripture_reference'),
        'source_url': data.get('source_url'),
        'reference': data.get('reference', ''),      # preserve legacy field
        'notes': data.get('notes'),
        'tags': tags_json,
        'visibility': visibility
    }

    try:
        new_item_id = add_vault_item(vault_data, owner_id)
        log_change(
            user_id=user_id,
            action='vault_quick_save',
            item_id=new_item_id,
            details=data['title'][:50],
            description='Quick-saved sermon section to Vault'
        )
        return jsonify({'status': 'success', 'item_id': new_item_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@vault_integration_bp.route('/search')
@pastoral_required()
def search():
    """
    Live search for the Insert from Vault modal.
    Query params:
        q            -> search term (across title, content, tags, scripture_reference, source_url)
        visibility   -> 'my' | 'shared' | 'all' (defaults to 'all')
        limit        -> max results (default 50)
    Returns JSON list of matching Vault items formatted for the modal grid.
    """
    user_id = session['user_id']
    q = request.args.get('q', '').strip()
    visibility_filter = request.args.get('visibility', 'all').lower()
    limit = int(request.args.get('limit', 50))

    # Map modal tabs to visibility logic used by search_vault_and_sermons
    if visibility_filter == 'my':
        vis = 'private'
    elif visibility_filter == 'shared':
        vis = 'pastoral_group'
    else:
        vis = 'all'

    try:
        results = search_vault_and_sermons(
            user_id=user_id,
            query=q,
            visibility=vis,
            limit=limit
        )
        # Ensure tags are a list for frontend (model may already parse them)
        for item in results:
            tags = item.get('tags')
            if isinstance(tags, list):
                continue
            if not tags:
                item['tags'] = []
            elif isinstance(tags, str):
                try:
                    parsed = json.loads(tags)
                    item['tags'] = parsed if isinstance(parsed, list) else [str(parsed)]
                except json.JSONDecodeError:
                    item['tags'] = [t.strip() for t in tags.split(',') if t.strip()]
            else:
                item['tags'] = []
        return jsonify({'items': results})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500