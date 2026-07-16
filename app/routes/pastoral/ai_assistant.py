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
def call_ai(prompt, model=None):
    """Thin wrapper so pastoral sermon tools share Gemini model fixes."""
    return _shared_call_ai(prompt, model=model, timeout=45)

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

    if not title and not passage:
        return jsonify({'status': 'error', 'message': 'Title or primary passage required'}), 400

    prompt_text = f"Title: {title}\nPrimary Passage: {passage}"
    if contains_censored_word(prompt_text):
        return jsonify({'status': 'error', 'message': 'Prohibited content in prompt'}), 400

    prompt = f"""
    You are a biblical preaching assistant for a church pastor.
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

    if not context:
        return jsonify({'status': 'error', 'message': 'Context required'}), 400

    if contains_censored_word(context):
        return jsonify({'status': 'error', 'message': 'Prohibited content in context'}), 400

    prompt = f"""
    You are a biblical preaching assistant.
    Based on this sermon content: {context}

    Suggest 5-8 thoughtful small-group discussion/application questions.
    Return ONLY a numbered list.
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

    if not point:
        return jsonify({'status': 'error', 'message': 'Point text required'}), 400

    if contains_censored_word(point):
        return jsonify({'status': 'error', 'message': 'Prohibited content'}), 400

    prompt = f"""
    You are a biblical preaching assistant.
    Expand this sermon point into 3-5 supporting explanatory paragraphs with biblical insight:
    {point}

    Keep tone pastoral and encouraging.
    """

    output, error = call_ai(prompt)
    if error:
        return jsonify({'status': 'error', 'message': error}), 500

    if contains_censored_word(output):
        output = "[Redacted - generated content contained prohibited terms]"

    log_change(user_id, 'ai', sermon_id, None, 'AI expanded point')

    return jsonify({'status': 'success', 'expansion': output})