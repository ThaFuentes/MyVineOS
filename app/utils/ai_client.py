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

# Current stable defaults.
# Prefer gemini-flash-latest: always tracks Google's current free/paid flash endpoint
# (fixed IDs like gemini-2.5-flash-lite are often 404 for new API keys; 3.5 can be slow/503).
DEFAULT_MODELS = {
    'grok': 'grok-2-latest',
    'openai': 'gpt-4o-mini',
    'gemini': 'gemini-flash-latest',
    'ollama': 'llama3.1',
}

# Map retired / fragile aliases → reliable Gemini model IDs.
_GEMINI_MODEL_ALIASES = {
    'gemini-1.5-flash': 'gemini-flash-latest',
    'gemini-1.5-flash-latest': 'gemini-flash-latest',
    'gemini-1.5-flash-8b': 'gemini-flash-lite-latest',
    'gemini-1.5-pro': 'gemini-2.5-pro',
    'gemini-1.5-pro-latest': 'gemini-2.5-pro',
    'gemini-pro': 'gemini-flash-latest',
    'gemini-pro-latest': 'gemini-2.5-pro',
    # flash-lite fixed IDs frequently 404 for new keys — use rolling alias
    'gemini-2.5-flash-lite': 'gemini-flash-lite-latest',
    'gemini-2.0-flash-lite': 'gemini-flash-lite-latest',
    'models/gemini-1.5-flash': 'gemini-flash-latest',
    'models/gemini-1.5-pro': 'gemini-2.5-pro',
}


def normalize_model_name(provider: str, model: str | None) -> str:
    """Return a usable model id for the provider (fix retired Gemini names)."""
    provider = (provider or '').strip().lower()
    raw = (model or '').strip()
    if not raw:
        return DEFAULT_MODELS.get(provider, '')
    # Strip optional "models/" prefix some UIs store
    if raw.startswith('models/'):
        raw = raw[len('models/') :]
    if provider == 'gemini':
        key = raw.lower()
        return _GEMINI_MODEL_ALIASES.get(key, raw)
    return raw


# Curated fallbacks when live list is unavailable (still better than a blank box).
RECOMMENDED_MODELS: dict[str, list[dict[str, str]]] = {
    'gemini': [
        {'id': 'gemini-flash-latest', 'label': 'Gemini Flash (latest) — recommended', 'note': 'Most reliable; tracks Google’s current flash model'},
        {'id': 'gemini-flash-lite-latest', 'label': 'Gemini Flash-Lite (latest)', 'note': 'Cheapest / fastest alias'},
        {'id': 'gemini-2.5-flash', 'label': 'Gemini 2.5 Flash', 'note': 'Stable fixed ID when available'},
        {'id': 'gemini-2.5-pro', 'label': 'Gemini 2.5 Pro', 'note': 'Higher quality reasoning'},
        {'id': 'gemini-3.5-flash', 'label': 'Gemini 3.5 Flash', 'note': 'Newer; can be slower or rate-limited on free tier'},
    ],
    'openai': [
        {'id': 'gpt-4o-mini', 'label': 'GPT-4o mini (recommended)', 'note': 'Good default for reports'},
        {'id': 'gpt-4o', 'label': 'GPT-4o', 'note': 'Higher quality'},
        {'id': 'gpt-4.1-mini', 'label': 'GPT-4.1 mini', 'note': 'Newer mini class'},
        {'id': 'o4-mini', 'label': 'o4-mini', 'note': 'Reasoning mini'},
    ],
    'grok': [
        {'id': 'grok-2-latest', 'label': 'Grok 2 (latest)', 'note': 'Default xAI chat model'},
        {'id': 'grok-3', 'label': 'Grok 3', 'note': 'When available on your plan'},
        {'id': 'grok-3-mini', 'label': 'Grok 3 Mini', 'note': 'Faster / cheaper'},
    ],
    'ollama': [
        {'id': 'llama3.1', 'label': 'Llama 3.1', 'note': 'Common local default'},
        {'id': 'llama3.2', 'label': 'Llama 3.2', 'note': 'If pulled locally'},
        {'id': 'mistral', 'label': 'Mistral', 'note': 'If pulled locally'},
        {'id': 'qwen2.5', 'label': 'Qwen 2.5', 'note': 'If pulled locally'},
    ],
}

# Short in-process cache for ListModels responses (per provider fingerprint).
_MODEL_LIST_CACHE: dict[str, tuple[float, dict]] = {}
_MODEL_LIST_TTL_SEC = 120


def _cache_get(key: str) -> Optional[dict]:
    row = _MODEL_LIST_CACHE.get(key)
    if not row:
        return None
    ts, payload = row
    if time.time() - ts > _MODEL_LIST_TTL_SEC:
        _MODEL_LIST_CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: dict) -> None:
    _MODEL_LIST_CACHE[key] = (time.time(), payload)


def _model_entry(model_id: str, label: str = '', note: str = '', **extra) -> dict:
    mid = (model_id or '').strip()
    if mid.startswith('models/'):
        mid = mid[len('models/') :]
    return {
        'id': mid,
        'label': label or mid,
        'note': note or '',
        **extra,
    }


def _list_gemini_models(api_key: str) -> tuple[list[dict], Optional[str]]:
    """List generateContent-capable Gemini models for this API key."""
    models: list[dict] = []
    page_token = None
    try:
        for _ in range(10):  # hard cap pages
            params = {'key': api_key, 'pageSize': 100}
            if page_token:
                params['pageToken'] = page_token
            resp = requests.get(
                'https://generativelanguage.googleapis.com/v1beta/models',
                params=params,
                timeout=20,
            )
            if resp.status_code != 200:
                body = ''
                try:
                    body = (resp.json().get('error') or {}).get('message') or resp.text
                except Exception:
                    body = resp.text
                return [], _sanitize_error(
                    f'Gemini ListModels HTTP {resp.status_code}: {body or "failed"}'
                )
            data = resp.json() or {}
            for m in data.get('models') or []:
                name = (m.get('name') or '').strip()
                if name.startswith('models/'):
                    name = name[len('models/') :]
                methods = m.get('supportedGenerationMethods') or m.get('supported_generation_methods') or []
                # Only models that can power chat / insights
                if methods and 'generateContent' not in methods:
                    continue
                if not name:
                    continue
                # Chat / text models only for Pastoral + Insights picker
                low = name.lower()
                skip_tokens = (
                    'embed', 'aqa', 'imagen', 'image', 'veo', 'tts', 'robotics',
                    'lyria', 'nano-banana', 'audio', 'live', 'computer-use',
                    'deep-research', 'antigravity', 'gemma',  # optional: keep gemma if wanted
                )
                # Keep gemma models — remove from skip
                skip_tokens = (
                    'embed', 'aqa', 'imagen', 'image', 'veo', 'tts', 'robotics',
                    'lyria', 'nano-banana', 'native-audio', 'live-preview',
                    'computer-use', 'deep-research', 'antigravity',
                )
                if any(x in low for x in skip_tokens):
                    continue
                display = (m.get('displayName') or m.get('display_name') or name).strip()
                desc = (m.get('description') or '')[:160]
                models.append(_model_entry(
                    name,
                    label=display,
                    note=desc,
                    methods=list(methods) if isinstance(methods, list) else [],
                    input_token_limit=m.get('inputTokenLimit') or m.get('input_token_limit'),
                    output_token_limit=m.get('outputTokenLimit') or m.get('output_token_limit'),
                ))
            page_token = data.get('nextPageToken') or data.get('next_page_token')
            if not page_token:
                break
    except requests.Timeout:
        return [], 'Gemini model list timed out.'
    except requests.RequestException:
        return [], 'Network error listing Gemini models.'
    except Exception:
        return [], 'Could not parse Gemini model list.'

    # Prefer flash/pro chat models first
    def sort_key(item: dict):
        i = (item.get('id') or '').lower()
        rank = 50
        if 'flash-lite' in i:
            rank = 2
        elif 'flash' in i and 'latest' not in i:
            rank = 1
        elif 'flash-latest' in i or i.endswith('flash-latest'):
            rank = 3
        elif 'pro' in i:
            rank = 4
        elif 'latest' in i:
            rank = 5
        return (rank, i)

    models.sort(key=sort_key)
    # de-dupe by id
    seen = set()
    unique = []
    for m in models:
        if m['id'] in seen:
            continue
        seen.add(m['id'])
        unique.append(m)
    return unique, None


def _list_openai_models(api_key: str) -> tuple[list[dict], Optional[str]]:
    try:
        resp = requests.get(
            'https://api.openai.com/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=20,
        )
        if resp.status_code != 200:
            return [], _sanitize_error(f'OpenAI ListModels HTTP {resp.status_code}')
        data = resp.json() or {}
        models = []
        for m in data.get('data') or []:
            mid = (m.get('id') or '').strip()
            if not mid:
                continue
            low = mid.lower()
            # Chat / completion oriented models
            if not any(k in low for k in ('gpt', 'o1', 'o3', 'o4', 'chatgpt')):
                continue
            if any(k in low for k in ('realtime', 'audio', 'transcribe', 'tts', 'image', 'embed', 'moderation', 'search')):
                continue
            models.append(_model_entry(mid, label=mid))
        models.sort(key=lambda x: (0 if 'mini' in x['id'] else 1, x['id']))
        return models, None
    except requests.Timeout:
        return [], 'OpenAI model list timed out.'
    except requests.RequestException:
        return [], 'Network error listing OpenAI models.'
    except Exception:
        return [], 'Could not parse OpenAI model list.'


def _list_grok_models(api_key: str) -> tuple[list[dict], Optional[str]]:
    try:
        resp = requests.get(
            'https://api.x.ai/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=20,
        )
        if resp.status_code != 200:
            return [], _sanitize_error(f'xAI ListModels HTTP {resp.status_code}')
        data = resp.json() or {}
        models = []
        for m in data.get('data') or []:
            mid = (m.get('id') or '').strip()
            if not mid:
                continue
            models.append(_model_entry(mid, label=mid))
        models.sort(key=lambda x: x['id'])
        return models, None
    except requests.Timeout:
        return [], 'xAI model list timed out.'
    except requests.RequestException:
        return [], 'Network error listing xAI models.'
    except Exception:
        return [], 'Could not parse xAI model list.'


def _list_ollama_models(base_url: str) -> tuple[list[dict], Optional[str]]:
    base = (base_url or 'http://127.0.0.1:11434').rstrip('/')
    try:
        resp = requests.get(f'{base}/api/tags', timeout=10)
        if resp.status_code != 200:
            return [], f'Ollama /api/tags HTTP {resp.status_code}. Is Ollama running at {base}?'
        data = resp.json() or {}
        models = []
        for m in data.get('models') or []:
            name = (m.get('name') or m.get('model') or '').strip()
            if not name:
                continue
            # Prefer short tag without :latest for display id still keep full name
            models.append(_model_entry(
                name,
                label=name,
                note=str(m.get('details', {}).get('parameter_size') or m.get('size') or ''),
            ))
        models.sort(key=lambda x: x['id'])
        return models, None
    except requests.Timeout:
        return [], f'Ollama timed out at {base}.'
    except requests.RequestException:
        return [], f'Could not reach Ollama at {base}. Start Ollama or check Base URL.'
    except Exception:
        return [], 'Could not parse Ollama model list.'


def list_available_models(
    provider: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    force_refresh: bool = False,
    include_recommended: bool = True,
) -> dict:
    """
    Discover models for a provider.
    Returns:
      {
        ok, provider, source: 'live'|'recommended'|'mixed',
        models: [{id, label, note, ...}],
        recommended: [...],
        error: optional message,
        default: suggested model id
      }
    Never includes API keys.
    """
    provider = (provider or '').strip().lower()
    if provider not in PROVIDERS:
        return {'ok': False, 'provider': provider, 'models': [], 'error': 'Unknown provider.'}

    recommended = list(RECOMMENDED_MODELS.get(provider) or [])
    default = DEFAULT_MODELS.get(provider, '')

    cache_key = f'{provider}:{(api_key or "")[:8]}:{(base_url or "")}'
    if not force_refresh:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    live: list[dict] = []
    err: Optional[str] = None

    if provider == 'gemini':
        if not api_key:
            err = 'Add a Gemini API key, then click Refresh models.'
        else:
            live, err = _list_gemini_models(api_key)
    elif provider == 'openai':
        if not api_key:
            err = 'Add an OpenAI API key, then click Refresh models.'
        else:
            live, err = _list_openai_models(api_key)
    elif provider == 'grok':
        if not api_key:
            err = 'Add an xAI/Grok API key, then click Refresh models.'
        else:
            live, err = _list_grok_models(api_key)
    elif provider == 'ollama':
        live, err = _list_ollama_models(base_url or 'http://127.0.0.1:11434')

    # Merge: live first, then recommended not already present
    by_id: dict[str, dict] = {}
    for m in live:
        by_id[m['id']] = {**m, 'source': 'live'}
    if include_recommended:
        for m in recommended:
            if m['id'] not in by_id:
                by_id[m['id']] = {**m, 'source': 'recommended'}

    models = list(by_id.values())

    # If current default is not in list, still prefer it as default when live empty
    if live:
        source = 'live' if not include_recommended else 'mixed'
        # Prefer DEFAULT if present in live list
        if default not in by_id and live:
            default = live[0]['id']
        elif default not in by_id:
            default = live[0]['id']
        ok = True
        # Soft warning if list worked but empty after filter
        if not live:
            ok = bool(models)
    else:
        source = 'recommended'
        ok = bool(models)
        if err and not models:
            ok = False

    payload = {
        'ok': ok if live or recommended else False,
        'provider': provider,
        'source': source,
        'models': models,
        'recommended': recommended,
        'live_count': len(live),
        'default': default,
        'error': err,
        'fetched_at': int(time.time()),
    }
    # Cache successful live lists (and recommended-only) briefly
    if live or not err:
        _cache_set(cache_key, payload)
    return payload


def list_models_for_configured_provider(provider: str, force_refresh: bool = False) -> dict:
    """Load stored key/url for provider and list models (settings UI helper)."""
    from app.routes.settings import load_ai_providers, decrypt

    provider = (provider or '').strip().lower()
    rows = load_ai_providers() or []
    row = next((p for p in rows if p.get('provider') == provider), None) or {}
    api_key = decrypt(row.get('api_key') or '') if row.get('api_key') else ''
    base_url = (row.get('base_url') or '').strip()
    result = list_available_models(
        provider,
        api_key=api_key or None,
        base_url=base_url or None,
        force_refresh=force_refresh,
    )
    result['current_model'] = normalize_model_name(provider, row.get('model_default') or '')
    result['has_key'] = bool(api_key) or provider == 'ollama'
    return result


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
    provider = chosen['provider']
    model = normalize_model_name(provider, chosen.get('model_default') or '')
    return {
        'provider': provider,
        'api_key': api_key or '',
        'base_url': (chosen.get('base_url') or '').strip(),
        'model': model,
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
    text = re.sub(r'AIza[0-9A-Za-z_\-]{10,}', '***', text)
    if len(text) > 280:
        text = text[:280] + '…'
    return text


def _friendly_http_error(provider: str, status: int, body: str, model: str | None) -> str:
    """Turn raw provider errors into actionable UI messages (no secrets)."""
    body_l = (body or '').lower()
    model = model or '?'

    if status == 404 and provider == 'gemini':
        return (
            f"Gemini model '{model}' was not found (HTTP 404). "
            f"Use '{DEFAULT_MODELS['gemini']}' or 'gemini-flash-lite-latest' "
            f"under Settings → AI Providers (fixed IDs like gemini-2.5-flash-lite often 404 for new keys)."
        )
    if status in (401, 403):
        return (
            f"AI provider rejected the API key (HTTP {status}). "
            f"Check the key under Settings → AI Providers for '{provider}'."
        )
    if status == 429:
        return (
            'AI provider rate limit hit (HTTP 429). '
            'Wait a minute, or switch to a lighter model like gemini-2.5-flash-lite.'
        )
    if status == 503:
        return (
            f"AI provider overloaded (HTTP 503) for model '{model}'. "
            'This is temporary on Google’s side — not caused by your report data. '
            'The app will auto-retry and try a lighter model; if it still fails, wait 30–60s and try again.'
        )
    if status >= 500:
        return (
            f'AI provider is temporarily unavailable (HTTP {status}). '
            'This is usually short-lived. Wait briefly and try again.'
        )

    # Surface a short Google error message when useful
    hint = ''
    try:
        parsed = json.loads(body or '')
        msg = (parsed.get('error') or {}).get('message') or ''
        if msg:
            hint = ' ' + _sanitize_error(msg)
    except Exception:
        if body_l and 'not found' in body_l:
            hint = ' Model may be retired or misspelled.'

    return _sanitize_error(f'AI API error HTTP {status}.{hint}')


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


# Transient failures worth automatic retry / model fallback.
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

# Fallbacks when primary is slow/503/404. Prefer rolling aliases that stay valid for new keys.
_GEMINI_FALLBACK_MODELS = (
    'gemini-flash-latest',
    'gemini-flash-lite-latest',
    'gemini-2.5-flash',
    'gemini-2.0-flash',
    'gemini-3-flash-preview',
)


def _gemini_model_candidates(primary: str) -> list[str]:
    """Primary model first, then lighter/alternate fallbacks (deduped)."""
    ordered = [primary] + [m for m in _GEMINI_FALLBACK_MODELS if m != primary]
    seen = set()
    out = []
    for m in ordered:
        m = normalize_model_name('gemini', m)
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _post_with_retries(
    url: str,
    *,
    headers: dict,
    json_body: dict,
    params: dict | None = None,
    timeout: int = 45,
    max_attempts: int = 3,
) -> tuple[Optional[requests.Response], Optional[str]]:
    """
    POST with exponential backoff on timeout / 429 / 5xx.
    Returns (response, transport_error). response may be non-200.
    """
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            # (connect timeout, read timeout) — fail faster on dead connections
            connect_t = min(12, timeout)
            read_t = max(timeout, 20)
            resp = requests.post(
                url,
                headers=headers,
                json=json_body,
                params=params,
                timeout=(connect_t, read_t),
            )
            if resp.status_code in _RETRYABLE_STATUS and attempt < max_attempts:
                # Honor Retry-After when present (cap 8s)
                delay = min(2 ** attempt, 6)
                try:
                    ra = resp.headers.get('Retry-After')
                    if ra:
                        delay = min(max(float(ra), 1.0), 8.0)
                except (TypeError, ValueError):
                    pass
                time.sleep(delay)
                last_err = f'HTTP {resp.status_code}'
                continue
            return resp, None
        except requests.Timeout:
            last_err = 'timeout'
            if attempt < max_attempts:
                time.sleep(min(2 ** attempt, 5))
                continue
            return None, 'timeout'
        except requests.RequestException as e:
            last_err = 'network'
            if attempt < max_attempts:
                time.sleep(min(2 ** attempt, 5))
                continue
            return None, 'network'
    return None, last_err or 'failed'


def _parse_provider_text(provider: str, result: dict) -> tuple[Optional[str], Optional[str]]:
    if provider == 'gemini':
        candidates = result.get('candidates') or []
        if not candidates:
            block = (result.get('promptFeedback') or {}).get('blockReason')
            if block:
                return None, f'Gemini blocked the prompt ({block}). Try a shorter question.'
            return None, 'Gemini returned no content. Try again with a simpler report.'
        parts = ((candidates[0].get('content') or {}).get('parts') or [])
        text = (parts[0].get('text') if parts else '') or ''
        return text, None
    if provider == 'ollama':
        return result.get('response') or '', None
    try:
        return result['choices'][0]['message']['content'], None
    except (KeyError, IndexError, TypeError):
        return None, 'Could not parse AI provider response.'


def call_ai(
    prompt: str,
    *,
    model: str | None = None,
    preferred_provider: str | None = None,
    system: str | None = None,
    timeout: int = 60,
    max_prompt_chars: int = 14000,
) -> tuple[Optional[str], Optional[str]]:
    """
    Call the configured provider with retries + Gemini model fallback on overload.
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

    provider = config['provider']
    primary_model = normalize_model_name(provider, model or config.get('model') or None)
    headers = {'Content-Type': 'application/json'}

    model_list = (
        _gemini_model_candidates(primary_model)
        if provider == 'gemini'
        else [primary_model]
    )

    last_http_error = None
    last_model_tried = primary_model
    saw_overload = False

    try:
        for model_idx, model in enumerate(model_list):
            last_model_tried = model
            # Build request per provider
            if provider == 'gemini':
                url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
                body_text = f'{system}\n\n{prompt}' if system else prompt
                data = {
                    'contents': [{'role': 'user', 'parts': [{'text': body_text}]}],
                    # Keep reports snappy — less time on overloaded fleets
                    'generationConfig': {
                        'temperature': 0.4,
                        'maxOutputTokens': 2048,
                    },
                }
                params = {'key': config['api_key']}
                auth_headers = headers
            elif provider == 'openai':
                url = 'https://api.openai.com/v1/chat/completions'
                messages = []
                if system:
                    messages.append({'role': 'system', 'content': system})
                messages.append({'role': 'user', 'content': prompt})
                data = {
                    'model': model,
                    'messages': messages,
                    'max_tokens': 2048,
                    'temperature': 0.4,
                }
                params = None
                auth_headers = {**headers, 'Authorization': f"Bearer {config['api_key']}"}
            elif provider == 'grok':
                url = 'https://api.x.ai/v1/chat/completions'
                messages = []
                if system:
                    messages.append({'role': 'system', 'content': system})
                messages.append({'role': 'user', 'content': prompt})
                data = {
                    'model': model,
                    'messages': messages,
                    'max_tokens': 2048,
                    'temperature': 0.4,
                }
                params = None
                auth_headers = {**headers, 'Authorization': f"Bearer {config['api_key']}"}
            elif provider == 'ollama':
                base = (config.get('base_url') or 'http://127.0.0.1:11434').rstrip('/')
                url = f'{base}/api/generate'
                full = f'{system}\n\n{prompt}' if system else prompt
                data = {'model': model, 'prompt': full, 'stream': False}
                params = None
                auth_headers = headers
            else:
                return None, 'Unsupported AI provider.'

            # Fewer attempts on later fallback models (already waited on primary)
            attempts = 3 if model_idx == 0 else 2
            response, transport_err = _post_with_retries(
                url,
                headers=auth_headers,
                json_body=data,
                params=params,
                timeout=timeout,
                max_attempts=attempts,
            )

            if transport_err == 'timeout':
                saw_overload = True
                # Try next Gemini model
                if provider == 'gemini' and model_idx < len(model_list) - 1:
                    continue
                return None, (
                    'AI provider timed out after retries. '
                    'Google may be overloaded — wait 30–60 seconds and try again, '
                    'or switch to gemini-flash-latest under Settings → AI Providers.'
                )
            if transport_err == 'network':
                if provider == 'gemini' and model_idx < len(model_list) - 1:
                    continue
                return None, 'Network error contacting AI provider. Check internet connectivity and try again.'
            if response is None:
                continue

            if response.status_code != 200:
                body = ''
                try:
                    body = response.text or ''
                except Exception:
                    body = ''
                last_http_error = _friendly_http_error(
                    provider, response.status_code, body, model
                )
                if response.status_code in _RETRYABLE_STATUS:
                    saw_overload = True
                    # Fall through to next model for Gemini
                    if provider == 'gemini' and model_idx < len(model_list) - 1:
                        continue
                # Non-retryable (401/403/404) — stop immediately
                return None, last_http_error

            try:
                result = response.json()
            except ValueError:
                if provider == 'gemini' and model_idx < len(model_list) - 1:
                    continue
                return None, 'Could not parse AI provider response.'

            text, parse_err = _parse_provider_text(provider, result)
            if parse_err:
                return None, parse_err

            text = (text or '').strip()
            if contains_censored_word(text):
                text = '[Redacted — generated content contained prohibited terms]'
            return text, None

        # Exhausted models
        if last_http_error:
            if saw_overload:
                return None, (
                    f'{last_http_error} '
                    f'Automatic retries and alternate models were tried '
                    f'(last: {last_model_tried}). Wait a minute and try again — '
                    f'this is usually temporary Google-side overload, not your data size.'
                )
            return None, last_http_error
        return None, 'AI provider failed after retries. Try again shortly.'

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

    # Insights: allow a bit more time; retries/fallback handle 503 overload
    text, error = call_ai(
        user_prompt,
        preferred_provider=preferred_provider,
        system=system,
        timeout=70,
    )
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
