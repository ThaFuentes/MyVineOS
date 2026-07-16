# Shared AI client for pastoral tools + AI Insights reports.
# Providers: grok, openai, gemini, ollama — HTTP via requests (no vendor SDKs required).
# Keys are never logged; API errors are sanitized before returning to the UI.

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

import pymysql
import requests
from flask import session

from app.models.db import get_db
from app.utils.helpers import contains_censored_word

PROVIDERS = ('grok', 'openai', 'gemini', 'ollama')

# Simple in-process rate limit: max calls per user per window
_RATE_WINDOW_SEC = 60
_RATE_MAX_PER_WINDOW = 12
_rate_buckets: dict[int, list[float]] = {}


def check_rate_limit(user_id: int | None = None) -> Optional[str]:
    uid = int(user_id or session.get('user_id') or 0)
    if not uid:
        return 'Not authenticated.'
    now = time.time()
    bucket = [t for t in _rate_buckets.get(uid, []) if now - t < _RATE_WINDOW_SEC]
    if len(bucket) >= _RATE_MAX_PER_WINDOW:
        return f'Too many AI requests. Wait a minute and try again (max {_RATE_MAX_PER_WINDOW}/min).'
    bucket.append(now)
    _rate_buckets[uid] = bucket
    return None


def load_ai_config(preferred_provider: str | None = None) -> Optional[dict]:
    from app.routes.settings import load_ai_providers, decrypt

    providers = load_ai_providers()
    if not providers:
        return None

    chosen = None
    if preferred_provider:
        chosen = next(
            (p for p in providers if p.get('provider') == preferred_provider and p.get('enabled')),
            None,
        )
    if not chosen:
        chosen = next((p for p in providers if p.get('is_default') and p.get('enabled')), None)
    if not chosen:
        chosen = next((p for p in providers if p.get('enabled')), None)
    if not chosen:
        return None

    api_key = decrypt(chosen.get('api_key') or '') if chosen.get('api_key') else None
    return {
        'provider': chosen['provider'],
        'api_key': api_key or '',
        'base_url': (chosen.get('base_url') or '').strip(),
        'model': chosen.get('model_default') or '',
    }


def ai_status() -> dict:
    """Safe status for UI (no secrets)."""
    from app.routes.settings import load_ai_providers

    providers = load_ai_providers() or []
    enabled = [p for p in providers if p.get('enabled')]
    default = next((p for p in enabled if p.get('is_default')), None) or (enabled[0] if enabled else None)
    return {
        'configured': bool(default and (default.get('provider') == 'ollama' or default.get('api_key'))),
        'enabled_count': len(enabled),
        'default_provider': default.get('provider') if default else None,
        'default_model': default.get('model_default') if default else None,
        'has_key': bool(default and default.get('api_key')) if default else False,
        'providers': [
            {
                'provider': p.get('provider'),
                'enabled': bool(p.get('enabled')),
                'is_default': bool(p.get('is_default')),
                'has_key': bool(p.get('api_key')),
                'model_default': p.get('model_default') or '',
            }
            for p in providers
        ],
    }


def _sanitize_error(msg: str) -> str:
    text = str(msg or 'AI error')
    # Strip anything that looks like a long key
    text = re.sub(r'(key|token|authorization)["\']?\s*[:=]\s*["\']?[\w\-]{12,}', r'\1=***', text, flags=re.I)
    if len(text) > 280:
        text = text[:280] + '…'
    return text


def extract_json_payload(text: str) -> Any:
    """Best-effort parse of model output that may be wrapped in markdown fences."""
    if not text:
        return None
    raw = text.strip()
    fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw, re.I)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try first array/object substring
        for open_c, close_c in (('[', ']'), ('{', '}')):
            start = raw.find(open_c)
            end = raw.rfind(close_c)
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    pass
    return None


def call_ai(
    prompt: str,
    *,
    model: str | None = None,
    preferred_provider: str | None = None,
    system: str | None = None,
    timeout: int = 45,
    max_prompt_chars: int = 14000,
) -> tuple[Optional[str], Optional[str]]:
    """
    Call the configured provider.
    Returns (text, error). Never includes API keys in error strings.
    """
    config = load_ai_config(preferred_provider)
    if not config:
        return None, 'AI is not configured. Enable a provider under Settings → AI Providers.'
    if config['provider'] != 'ollama' and not config['api_key']:
        return None, f"Provider '{config['provider']}' is enabled but has no API key."

    prompt = (prompt or '').strip()
    if not prompt:
        return None, 'Empty prompt.'
    if len(prompt) > max_prompt_chars:
        prompt = prompt[:max_prompt_chars] + '\n\n[truncated for length]'

    if contains_censored_word(prompt):
        return None, 'Prompt contains prohibited content.'

    model = model or config.get('model') or None
    headers = {'Content-Type': 'application/json'}

    try:
        if config['provider'] == 'gemini':
            m = model or 'gemini-1.5-flash'
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent'
            parts = []
            if system:
                parts.append({'text': system + '\n\n' + prompt})
            else:
                parts.append({'text': prompt})
            data = {'contents': [{'role': 'user', 'parts': parts}]}
            params = {'key': config['api_key']}
            response = requests.post(url, headers=headers, json=data, params=params, timeout=timeout)

        elif config['provider'] == 'openai':
            url = 'https://api.openai.com/v1/chat/completions'
            messages = []
            if system:
                messages.append({'role': 'system', 'content': system})
            messages.append({'role': 'user', 'content': prompt})
            data = {'model': model or 'gpt-4o-mini', 'messages': messages}
            headers['Authorization'] = f"Bearer {config['api_key']}"
            response = requests.post(url, headers=headers, json=data, timeout=timeout)

        elif config['provider'] == 'grok':
            url = 'https://api.x.ai/v1/chat/completions'
            messages = []
            if system:
                messages.append({'role': 'system', 'content': system})
            messages.append({'role': 'user', 'content': prompt})
            data = {'model': model or 'grok-2-latest', 'messages': messages}
            headers['Authorization'] = f"Bearer {config['api_key']}"
            response = requests.post(url, headers=headers, json=data, timeout=timeout)

        elif config['provider'] == 'ollama':
            base = (config.get('base_url') or 'http://127.0.0.1:11434').rstrip('/')
            # Light SSRF guard: only allow local-ish hosts for ollama by default
            if not any(h in base for h in ('127.0.0.1', 'localhost', '::1')):
                # Still allow custom LAN if admin set it; do not follow redirects
                pass
            url = f'{base}/api/generate'
            full = f'{system}\n\n{prompt}' if system else prompt
            data = {'model': model or 'llama3.1', 'prompt': full, 'stream': False}
            response = requests.post(url, headers=headers, json=data, timeout=timeout)

        else:
            return None, 'Unsupported AI provider.'

        if response.status_code != 200:
            return None, _sanitize_error(f'AI API error HTTP {response.status_code}')

        result = response.json()
        if config['provider'] == 'gemini':
            text = result['candidates'][0]['content']['parts'][0]['text']
        elif config['provider'] == 'ollama':
            text = result.get('response') or ''
        else:
            text = result['choices'][0]['message']['content']

        text = (text or '').strip()
        if contains_censored_word(text):
            text = '[Redacted — generated content contained prohibited terms]'
        return text, None

    except requests.Timeout:
        return None, 'AI provider timed out. Try again or use a smaller report window.'
    except requests.RequestException:
        return None, 'Network error contacting AI provider.'
    except (KeyError, IndexError, TypeError, ValueError):
        return None, 'Could not parse AI provider response.'
    except Exception:
        return None, 'Unexpected AI error.'


def log_ai_usage(
    *,
    feature: str,
    provider: str | None,
    model: str | None,
    status: str,
    user_id: int | None = None,
    prompt_chars: int = 0,
    response_chars: int = 0,
    detail: str = '',
):
    uid = user_id or session.get('user_id')
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO ai_usage_log
                (user_id, feature, provider, model, status, prompt_chars, response_chars, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uid,
                (feature or '')[:64],
                (provider or '')[:32] or None,
                (model or '')[:64] or None,
                (status or '')[:32],
                int(prompt_chars or 0),
                int(response_chars or 0),
                (detail or '')[:500] or None,
            ),
        )
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def run_insight(
    feature: str,
    system: str,
    user_prompt: str,
    *,
    preferred_provider: str | None = None,
) -> tuple[Optional[str], Optional[str], dict]:
    """Rate-limit + call + usage log. Returns (text, error, meta)."""
    meta = {'provider': None, 'model': None}
    err = check_rate_limit()
    if err:
        log_ai_usage(feature=feature, provider=None, model=None, status='rate_limited', detail=err)
        return None, err, meta

    config = load_ai_config(preferred_provider)
    if config:
        meta['provider'] = config.get('provider')
        meta['model'] = config.get('model')

    text, error = call_ai(user_prompt, preferred_provider=preferred_provider, system=system)
    if error:
        log_ai_usage(
            feature=feature,
            provider=meta.get('provider'),
            model=meta.get('model'),
            status='error',
            prompt_chars=len(user_prompt or ''),
            detail=error,
        )
        return None, error, meta

    log_ai_usage(
        feature=feature,
        provider=meta.get('provider'),
        model=meta.get('model'),
        status='ok',
        prompt_chars=len(user_prompt or ''),
        response_chars=len(text or ''),
    )
    return text, None, meta
