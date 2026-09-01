# AI provider configuration - per-provider keys, enable toggles, live model discovery.

from flask import render_template, request, redirect, url_for, flash, session, jsonify

from app.models.db import get_db
from app.models.log import log_change
from app.utils.ai_client import (
    DEFAULT_MODELS,
    RECOMMENDED_MODELS,
    list_available_models,
    list_models_for_configured_provider,
    normalize_model_name,
)
from . import settings_bp, encrypt, decrypt, has_section_permission, load_ai_providers

PROVIDERS = ['grok', 'openai', 'gemini', 'ollama']


def _provider_display_name(prov: str) -> str:
    return {
        'openai': 'OpenAI (ChatGPT)',
        'grok': 'Grok (xAI)',
        'gemini': 'Gemini (Google)',
        'ollama': 'Ollama (local)',
    }.get(prov, prov.title())


@settings_bp.route('/ai', methods=['GET', 'POST'])
def ai():
    if request.method == 'POST' and not has_section_permission('ai'):
        flash('Insufficient permission to edit AI settings.', 'error')
        return redirect(url_for('settings.ai'))

    db = get_db()
    user_id = session['user_id']
    providers = {p['provider']: p for p in load_ai_providers()}

    if request.method == 'POST':
        default_provider = request.form.get('default_provider', 'grok')
        cur = db.cursor()

        for prov in PROVIDERS:
            enabled = 1 if request.form.get(f'enabled_{prov}') == '1' else 0
            new_key = request.form.get(f'api_key_{prov}', '').strip()
            base_url = request.form.get(f'base_url_{prov}', '').strip() or None
            # Prefer picker value; allow custom override when "custom" selected
            model_pick = (request.form.get(f'model_pick_{prov}') or '').strip()
            model_custom = (request.form.get(f'model_custom_{prov}') or '').strip()
            if model_pick == '__custom__':
                model_default = model_custom or None
            elif model_pick:
                model_default = model_pick
            else:
                model_default = (request.form.get(f'model_{prov}') or '').strip() or None
            if model_default:
                model_default = normalize_model_name(prov, model_default)

            existing = providers.get(prov, {})
            api_key = encrypt(new_key) if new_key else existing.get('api_key')
            is_default = 1 if prov == default_provider else 0

            cur.execute("SELECT id FROM ai_providers WHERE provider = %s", (prov,))
            if cur.fetchone():
                if new_key:
                    cur.execute("""
                        UPDATE ai_providers
                        SET enabled = %s, is_default = %s, api_key = %s, base_url = %s, model_default = %s
                        WHERE provider = %s
                    """, (enabled, is_default, api_key, base_url, model_default, prov))
                else:
                    cur.execute("""
                        UPDATE ai_providers
                        SET enabled = %s, is_default = %s, base_url = %s, model_default = %s
                        WHERE provider = %s
                    """, (enabled, is_default, base_url, model_default, prov))
            else:
                cur.execute("""
                    INSERT INTO ai_providers (provider, enabled, is_default, api_key, base_url, model_default)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (prov, enabled, is_default, api_key, base_url, model_default))

        db.commit()
        log_change(user_id, 'update', None, None, 'Updated AI provider configuration')
        flash('AI settings saved.', 'success')
        providers = {p['provider']: p for p in load_ai_providers()}

    provider_list = []
    for prov in PROVIDERS:
        row = providers.get(prov, {})
        raw_model = row.get('model_default') or ''
        model_default = normalize_model_name(prov, raw_model) if raw_model else (DEFAULT_MODELS.get(prov) or '')
        # Prefetch recommended list for first paint; live list via AJAX
        recommended = list(RECOMMENDED_MODELS.get(prov) or [])
        provider_list.append({
            'provider': prov,
            'display_name': _provider_display_name(prov),
            'enabled': row.get('enabled', 0),
            'is_default': row.get('is_default', 0),
            'has_key': bool(row.get('api_key')),
            'base_url': row.get('base_url') or ('http://127.0.0.1:11434' if prov == 'ollama' else ''),
            'model_default': model_default,
            'recommended_models': recommended,
            'default_model': DEFAULT_MODELS.get(prov) or '',
        })

    return render_template(
        'settings/ai.html',
        providers=provider_list,
        can_edit=has_section_permission('ai'),
    )


@settings_bp.route('/ai/models/<provider>', methods=['GET'])
def ai_list_models(provider):
    """
    Live model discovery for Settings UI.
    Uses saved key (or optional draft key/base_url query for unsaved testing).
    Never returns API keys.
    """
    # before_request already requires settings access; listing models is read-only discovery.
    provider = (provider or '').strip().lower()
    if provider not in PROVIDERS:
        return jsonify({'ok': False, 'error': 'Unknown provider'}), 400

    force = request.args.get('refresh') in ('1', 'true', 'yes')
    draft_key = (request.args.get('api_key') or '').strip()
    draft_base = (request.args.get('base_url') or '').strip()

    if draft_key or draft_base:
        # Unsaved form values (user typed key but hasn't saved yet)
        from app.routes.settings import load_ai_providers, decrypt
        rows = load_ai_providers() or []
        row = next((p for p in rows if p.get('provider') == provider), None) or {}
        api_key = draft_key or (decrypt(row.get('api_key') or '') if row.get('api_key') else '')
        base_url = draft_base or (row.get('base_url') or '')
        result = list_available_models(
            provider,
            api_key=api_key or None,
            base_url=base_url or None,
            force_refresh=force,
        )
        result['current_model'] = normalize_model_name(provider, row.get('model_default') or '')
        result['has_key'] = bool(api_key) or provider == 'ollama'
    else:
        result = list_models_for_configured_provider(provider, force_refresh=force)

    status = 200 if result.get('ok') or result.get('models') else 502
    if result.get('source') == 'recommended' and result.get('error'):
        # Still return 200 with recommended fallback so UI can populate
        status = 200
    return jsonify(result), status
