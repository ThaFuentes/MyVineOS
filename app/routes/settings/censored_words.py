# myvinechurchonline/app/routes/settings/censored_words.py
# Full path: myvinechurchonline/app/routes/settings/censored_words.py
# File name: censored_words.py
# Brief, detailed purpose: Censored words list management (quick single-add + bulk editor).
# No censorship check on this section (admins must be able to add any word).
# Case-insensitive duplicate prevention on single add.
# All actions audit-logged with full 5-argument log_change.
# Uses DictCursor for safe row access.
# CONFIRMED CORRECT: Package-relative imports + pymysql.

from flask import render_template, request, redirect, url_for, flash, session
from app.models.db import get_db
from app.models.log import log_change
from . import settings_bp, has_section_permission
import pymysql  # Required for DictCursor

@settings_bp.route('/censored-words', methods=['GET', 'POST'])
def censored_words():
    if request.method == 'POST' and not has_section_permission('censored_words'):
        flash('Insufficient permission to edit Censored Words.', 'error')
        return redirect(url_for('settings.censored_words'))

    db = get_db()
    user_id = session['user_id']
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("SELECT censored_words FROM settings WHERE id = 1")
    row = cur.fetchone()
    censored_words_text = row['censored_words'] if row and row['censored_words'] else ''

    current_words = [line.strip() for line in censored_words_text.splitlines() if line.strip()]

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_single_censored':
            new_word = request.form.get('new_word', '').strip()
            if not new_word:
                flash('Please enter a word or phrase.', 'error')
            elif new_word.lower() in [w.lower() for w in current_words]:
                flash(f'"{new_word}" is already censored.', 'info')
            else:
                current_words.append(new_word)
                new_text = '\n'.join(current_words)
                cur.execute("UPDATE settings SET censored_words = %s WHERE id = 1", (new_text,))
                db.commit()
                log_change(user_id, 'update', None, new_word, f'Added censored word: {new_word}')
                flash(f'"{new_word}" added to censored list.', 'success')
                censored_words_text = new_text
                current_words = [line.strip() for line in new_text.splitlines() if line.strip()]

        elif action == 'update_censored_words':
            new_text = request.form.get('censored_words', '').rstrip('\n')
            cur.execute("UPDATE settings SET censored_words = %s WHERE id = 1", (new_text or None,))
            db.commit()
            log_change(user_id, 'update', None, 'Full List', 'Updated full censored words list')
            flash('Full censored words list saved.', 'success')
            censored_words_text = new_text
            current_words = [line.strip() for line in new_text.splitlines() if line.strip()]

    return render_template('settings/censored_words.html', censored_words_text=censored_words_text)