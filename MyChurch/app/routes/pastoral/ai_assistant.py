# app/routes/pastoral/ai_assistant.py
# Full path: WebChurchMan/app/routes/pastoral/ai_assistant.py
# File name: ai_assistant.py
# Brief, detailed purpose: AI-powered sermon assistance endpoints for the Pastoral Sermon Builder.
#   - Generate outline from title/primary passage
#   - Suggest discussion/application questions
#   - Expand a selected point/section
#   - Uses the globally configured AI provider from settings table (grok, openai, gemini, ollama)
#   - API key loaded and decrypted on each call (from settings.ai_api_key)
#   - Falls back to disabled if no valid config
#   - Site-wide censored word check on user prompt text
#   - Generated output checked and redacted if contains censored words (rare but safe)
#   - Audit-logged AI usage
#   - Returns JSON for editor JS integration

from flask import request, jsonify, session
from . import pastoral_bp, pastoral_required  # Package-relative import within pastoral
from app.models.db import get_db
from app.models.log import log_change
from app.utils.helpers import contains_censored_word
from app.utils.ai_client import call_ai as _shared_call_ai
import json
import pymysql


# ----------------------------------------------------------------------
# Helper: Call the configured AI provider (shared client)
# ----------------------------------------------------------------------
def call_ai(prompt, model=None, *, max_prompt_chars=400000):
    """Thin wrapper so pastoral sermon tools share Gemini model fixes."""
    return _shared_call_ai(
        prompt,
        model=model,
        timeout=180,
        max_prompt_chars=max_prompt_chars,
        shrink_on_reject=True,
    )


def _sermon_body_for_ai(sermon_id, user_id) -> str:
    """Full sermon text from the database — not just title/passage."""
    from app.models.pastoral.sermons import get_sermon_by_id, get_sermon_sections
    from app.models.pastoral.sermon_search import sermon_blob_for_ai
    sermon = get_sermon_by_id(sermon_id, user_id)
    if not sermon:
        return ''
    return sermon_blob_for_ai(sermon, get_sermon_sections(sermon_id) or [])

# ----------------------------------------------------------------------
# Generate Outline
# ----------------------------------------------------------------------
@pastoral_bp.route('/sermons/ai/generate_outline/<int:sermon_id>', methods=['POST'])
@pastoral_required()
def ai_generate_outline(sermon_id):
    user_id = session['user_id']
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    passage = data.get('primary_passage', '').strip()
    sermon_text = _sermon_body_for_ai(sermon_id, user_id)

    if not title and not passage and not sermon_text:
        return jsonify({'status': 'error', 'message': 'Title or primary passage required'}), 400

    prompt_text = f"Title: {title}\nPrimary Passage: {passage}"
    if sermon_text:
        prompt_text += f"\n\nFULL SERMON TEXT:\n{sermon_text}"
    if contains_censored_word(prompt_text):
        return jsonify({'status': 'error', 'message': 'Prohibited content in prompt'}), 400

    prompt = f"""
    You are a practical preaching teammate helping a modern pastor prepare.
    Use clear everyday English (not King James style). Keep content warm and usable.
    You have the pastor's full sermon below (every section). Do not say you received little data.
    Generate a clear, structured sermon outline based on the following:
    {prompt_text}

    Return ONLY a JSON array of sections with:
    - "title": section heading
    - "type": one of "introduction", "point", "application", "conclusion"
    - "content": brief description or key points (2-4 sentences)
    - "scripture_reference": optional related verses

    Example format:
    [
      {{"title": "Introduction", "type": "introduction", "content": "...", "scripture_reference": ""}},
      {{"title": "Point 1: Grace", "type": "point", "content": "...", "scripture_reference": "Eph 2:8-9"}}
    ]
    """

    output, error = call_ai(prompt)
    if error:
        return jsonify({'status': 'error', 'message': error}), 500

    if contains_censored_word(output):
        output = "[Redacted - generated content contained prohibited terms]"

    log_change(user_id, 'ai', sermon_id, title or passage, 'AI generated outline')

    try:
        outline = json.loads(output)
    except json.JSONDecodeError:
        outline = output  # Fallback to raw text if not JSON

    return jsonify({'status': 'success', 'outline': outline})

# ----------------------------------------------------------------------
# Suggest Questions
# ----------------------------------------------------------------------
@pastoral_bp.route('/sermons/ai/suggest_questions/<int:sermon_id>', methods=['POST'])
@pastoral_required()
def ai_suggest_questions(sermon_id):
    user_id = session['user_id']
    data = request.get_json() or {}
    context = data.get('context', '').strip()
    sermon_text = _sermon_body_for_ai(sermon_id, user_id)
    material = sermon_text or context

    if not material:
        return jsonify({'status': 'error', 'message': 'Context required'}), 400

    if contains_censored_word(material):
        return jsonify({'status': 'error', 'message': 'Prohibited content in context'}), 400

    prompt = f"""
    You are a practical preaching teammate helping a modern pastor.
    Use clear everyday English (not formal or King James style).
    You have the pastor's full sermon below. Do not say you received little data.
    Based on this sermon content:\n{material}

    Suggest 5-8 thoughtful small-group discussion/application questions.
    Return ONLY a numbered list. No markdown headings.
    """

    output, error = call_ai(prompt)
    if error:
        return jsonify({'status': 'error', 'message': error}), 500

    if contains_censored_word(output):
        output = "[Redacted - generated content contained prohibited terms]"

    log_change(user_id, 'ai', sermon_id, None, 'AI suggested discussion questions')

    return jsonify({'status': 'success', 'questions': output})

# ----------------------------------------------------------------------
# Expand Point
# ----------------------------------------------------------------------
@pastoral_bp.route('/sermons/ai/expand_point/<int:sermon_id>', methods=['POST'])
@pastoral_required()
def ai_expand_point(sermon_id):
    user_id = session['user_id']
    data = request.get_json() or {}
    point = data.get('point', '').strip()
    sermon_text = _sermon_body_for_ai(sermon_id, user_id)

    if not point:
        return jsonify({'status': 'error', 'message': 'Point text required'}), 400

    if contains_censored_word(point) or contains_censored_word(sermon_text):
        return jsonify({'status': 'error', 'message': 'Prohibited content'}), 400

    extra = f"\n\nFULL SERMON for context:\n{sermon_text}" if sermon_text else ''
    prompt = f"""
    You are a practical preaching teammate helping a modern pastor.
    Expand this sermon point into 3-5 short paragraphs a pastor could adapt:
    {point}
    {extra}

    Everyday English, warm and clear — not King James, not academic. No markdown headings.
    Use the full sermon if it is present. Do not say you received little data.
    """

    output, error = call_ai(prompt)
    if error:
        return jsonify({'status': 'error', 'message': error}), 500

    if contains_censored_word(output):
        output = "[Redacted - generated content contained prohibited terms]"

    log_change(user_id, 'ai', sermon_id, None, 'AI expanded point')

    return jsonify({'status': 'success', 'expansion': output})