# AI provider configuration - per-provider keys and enable toggles.

from flask import render_template, request, redirect, url_for, flash, session
from app.models.db import get_db
from app.models.log import log_change
from . import settings_bp, encrypt, decrypt, has_section_permission, load_ai_providers

PROVIDERS = ['grok', 'openai', 'gemini', 'ollama']


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
            model_default = request.form.get(f'model_{prov}', '').strip() or None
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
        provider_list.append({
            'provider': prov,
            'enabled': row.get('enabled', 0),
            'is_default': row.get('is_default', 0),
            'has_key': bool(row.get('api_key')),
            'base_url': row.get('base_url') or ('http://localhost:11434' if prov == 'ollama' else ''),
            'model_default': row.get('model_default') or '',
        })

    return render_template('settings/ai.html', providers=provider_list)