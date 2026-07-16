import json
from datetime import datetime

from flask import (
    abort, current_app, flash, jsonify, redirect, render_template, request,
    send_from_directory, session, url_for,
)

from app.models.worship import setlists as setlist_model
from app.models.worship import songs as song_model
from app.models.worship import templates as template_model
from app.models.worship import notes as notes_model
from app.models.worship import plays as plays_model
from app.models.worship.sections import parse_lyrics_to_sections
from app.models.worship.shared import (
    can_manage_worship, get_worship_team_members, get_worship_leaders,
)
from app.utils.emailer import send_email

from . import worship_bp, worship_required
from .utils import DEFAULT_ROLES, chords_upload_dir, save_chord_upload


def _parse_sections_form():
    """Prefer structured section cards from the song editor; fall back to JSON/lyrics."""
    ids = request.form.getlist('sec_id[]')
    types = request.form.getlist('sec_type[]')
    labels = request.form.getlist('sec_label[]')
    contents = request.form.getlist('sec_content[]')
    if ids or labels or contents:
        sections = []
        n = max(len(ids), len(types), len(labels), len(contents))
        for i in range(n):
            content = (contents[i] if i < len(contents) else '') or ''
            content = content.strip()
            if not content:
                continue
            sid = (ids[i] if i < len(ids) else '') or ''
            stype = (types[i] if i < len(types) else '') or 'verse'
            label = (labels[i] if i < len(labels) else '') or stype.title()
            sections.append({
                'id': sid.strip() or f's{i + 1}',
                'type': stype.strip().lower() or 'verse',
                'label': label.strip() or 'Section',
                'content': content,
                'sort': i + 1,
                'repeat': 1,
            })
        if sections:
            return sections

    raw = (request.form.get('sections_json') or '').strip()
    if raw:
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            pass
    lyrics = (request.form.get('lyrics_raw') or '').strip()
    if lyrics:
        return parse_lyrics_to_sections(lyrics) or [
            {'id': 'v1', 'type': 'verse', 'label': 'Lyrics', 'content': lyrics, 'sort': 1, 'repeat': 1},
        ]
    return []


def _parse_play_order_form():
    order = request.form.getlist('play_order[]')
    if order:
        return [x.strip() for x in order if x and x.strip()]
    raw = (request.form.get('play_order_json') or '').strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x) for x in data if x]
        except json.JSONDecodeError:
            pass
    return []


def _song_form_data(chords_filename=None):
    year = request.form.get('copyright_year')
    return {
        'title': (request.form.get('title') or '').strip(),
        'artist': (request.form.get('artist') or '').strip() or None,
        'ccli_song_number': (request.form.get('ccli_song_number') or '').strip() or None,
        'copyright_line': (request.form.get('copyright_line') or '').strip() or None,
        'publisher': (request.form.get('publisher') or '').strip() or None,
        'copyright_year': int(year) if year and year.isdigit() else None,
        'lyrics_raw': (request.form.get('lyrics_raw') or '').strip() or None,
        'notes_permanent': (request.form.get('notes_permanent') or '').strip() or None,
        'sections': _parse_sections_form(),
        'play_order': _parse_play_order_form(),
        'chords_filename': chords_filename,
    }


def _setlist_form_data():
    return {
        'title': (request.form.get('title') or '').strip(),
        'service_date': (request.form.get('service_date') or '').strip() or None,
        'service_time': (request.form.get('service_time') or '').strip() or None,
        'rehearsal_time': (request.form.get('rehearsal_time') or '').strip() or None,
        'rehearsal_location': (request.form.get('rehearsal_location') or '').strip() or None,
        'notes': (request.form.get('notes') or '').strip() or None,
        'is_published': request.form.get('is_published') == '1',
    }


def _assignment_rows_from_form():
    roles = request.form.getlist('assign_role[]')
    users = request.form.getlist('assign_user[]')
    rows = []
    for role, uid in zip(roles, users):
        if role.strip() and uid:
            rows.append({'role_name': role.strip(), 'user_id': int(uid)})
    return rows


def _save_member_notes_from_form(setlist_id=None, template_id=None):
    if not can_manage_worship():
        return
    uids = request.form.getlist('note_user_id[]')
    texts = request.form.getlist('note_text[]')
    for uid, text in zip(uids, texts):
        if uid:
            notes_model.save_member_note(
                int(uid), text, session['user_id'],
                setlist_id=setlist_id, template_id=template_id,
            )


def _plan_context(plan):
    """Normalize plan dict for edit templates."""
    if not plan:
        return None
    ctx = dict(plan)
    if plan.get('source') == 'template':
        ctx['template_id'] = plan.get('template_id') or plan.get('id')
        ctx['is_template_plan'] = True
    return ctx


@worship_bp.route('/')
@worship_required
def dashboard():
    upcoming = setlist_model.get_upcoming_setlist()
    public_token = None
    if upcoming:
        if upcoming.get('source') == 'override' and upcoming.get('id'):
            public_token = setlist_model.ensure_public_token(upcoming['id'])
        elif upcoming.get('template_id'):
            public_token = template_model.ensure_public_token_template(upcoming['template_id'])
    return render_template(
        'worship/dashboard.html',
        upcoming=upcoming,
        setlists=setlist_model.list_setlists(8),
        songs=song_model.list_songs()[:8],
        can_manage=can_manage_worship(),
        leaders=get_worship_leaders(),
        play_stats=plays_model.get_song_play_counts()[:5],
        public_token=public_token,
    )


@worship_bp.route('/songs')
@worship_required
def songs_list():
    return render_template(
        'worship/songs_list.html',
        songs=song_model.list_songs(),
        can_manage=can_manage_worship(),
        play_stats=plays_model.get_song_play_counts(),
    )


@worship_bp.route('/songs/import', methods=['GET', 'POST'])
@worship_required
def songs_import():
    if not can_manage_worship():
        flash('Only worship managers can import songs.', 'error')
        return redirect(url_for('worship.songs_list'))

    result = None
    chart_preview = None
    if request.method == 'POST':
        action = (request.form.get('action') or 'json').strip()
        if action == 'chart':
            from app.models.worship.song_parse import extract_text_from_upload, parse_song_text
            parse_mode = (request.form.get('parse_mode') or 'auto').strip().lower()
            if parse_mode not in ('rules', 'auto', 'ai'):
                parse_mode = 'auto'
            raw = (request.form.get('chart_text') or '').strip()
            f = request.files.get('chart_file')
            if not raw and f and f.filename:
                try:
                    raw = extract_text_from_upload(f.filename, f.read())
                except ValueError as e:
                    flash(str(e), 'error')
                    return redirect(url_for('worship.songs_import'))
            if not raw:
                flash('Paste a chord chart or upload a .txt / ChordPro / .docx file.', 'error')
            else:
                parsed = parse_song_text(
                    raw,
                    title_hint=request.form.get('title') or '',
                    artist_hint=request.form.get('artist') or '',
                    use_ai=parse_mode,
                )
                if request.form.get('save_now') == '1':
                    ccli = (
                        parsed.get('ccli_song_number')
                        or (request.form.get('ccli_hint') or '').strip()
                        or None
                    )
                    copyright_line = (
                        parsed.get('copyright_line')
                        or (request.form.get('copyright_hint') or '').strip()
                        or None
                    )
                    data = {
                        'title': parsed.get('title') or 'Untitled Song',
                        'artist': parsed.get('artist') or None,
                        'ccli_song_number': ccli,
                        'copyright_line': copyright_line,
                        'publisher': None,
                        'copyright_year': None,
                        'lyrics_raw': parsed.get('lyrics_raw'),
                        'notes_permanent': parsed.get('notes') or None,
                        'sections': parsed.get('sections') or [],
                        'play_order': parsed.get('play_order') or [],
                        'chords_filename': None,
                    }
                    song_id = song_model.save_song(data, session['user_id'])
                    flash(
                        f"Song saved ({parsed.get('parse_mode', 'rules')}"
                        + (', AI assisted' if parsed.get('ai_used') else '')
                        + f", {len(data['sections'])} sections).",
                        'success',
                    )
                    return redirect(url_for('worship.song_edit', song_id=song_id))
                chart_preview = parsed
                flash('Chart parsed — review below, then save to library or open the editor.', 'success')
        else:
            raw = (request.form.get('json_data') or '').strip()
            if not raw and request.files.get('json_file'):
                raw = request.files['json_file'].read().decode('utf-8', errors='replace')
            try:
                payload = json.loads(raw)
                items = payload.get('songs', payload) if isinstance(payload, dict) else payload
                if not isinstance(items, list):
                    raise ValueError('Expected a JSON array or {"songs": [...]}')
                result = song_model.bulk_import_songs(items, session['user_id'])
                flash(
                    f"Import done: {result['created']} created, {result['updated']} updated, "
                    f"{result['skipped']} skipped.",
                    'success',
                )
            except (json.JSONDecodeError, ValueError) as e:
                flash(f'Invalid JSON: {e}', 'error')

    return render_template(
        'worship/songs_import.html',
        result=result,
        chart_preview=chart_preview,
        can_manage=True,
    )


@worship_bp.route('/songs/parse-chart', methods=['POST'])
@worship_required
def songs_parse_chart():
    """JSON API: parse pasted chart / upload text with rules or AI (managers only)."""
    if not can_manage_worship():
        return jsonify({'ok': False, 'error': 'Permission denied'}), 403
    from app.models.worship.song_parse import extract_text_from_upload, parse_song_text

    if request.is_json:
        data = request.get_json(silent=True) or {}
        raw = (data.get('chart_text') or data.get('text') or '').strip()
        title_hint = data.get('title') or ''
        artist_hint = data.get('artist') or ''
        parse_mode = (data.get('parse_mode') or 'auto').strip().lower()
    else:
        raw = (request.form.get('chart_text') or '').strip()
        title_hint = request.form.get('title') or ''
        artist_hint = request.form.get('artist') or ''
        parse_mode = (request.form.get('parse_mode') or 'auto').strip().lower()
        f = request.files.get('chart_file')
        if not raw and f and f.filename:
            try:
                raw = extract_text_from_upload(f.filename, f.read())
            except ValueError as e:
                return jsonify({'ok': False, 'error': str(e)}), 400
    if parse_mode not in ('rules', 'auto', 'ai'):
        parse_mode = 'auto'
    if not raw:
        return jsonify({'ok': False, 'error': 'No chart text provided'}), 400
    parsed = parse_song_text(raw, title_hint=title_hint, artist_hint=artist_hint, use_ai=parse_mode)
    return jsonify({'ok': True, 'song': parsed})


@worship_bp.route('/songs/public-domain', methods=['GET', 'POST'])
@worship_required
def songs_public_domain():
    """Browse public-domain starter pack; add selected songs to the library."""
    from app.models.worship.public_domain import (
        get_public_domain_song,
        get_public_domain_songs,
        list_public_domain_pack,
    )
    from app.models.worship.song_parse import parse_chart_to_sections, sections_to_lyrics_raw
    from app.models.worship.sections import default_play_order_from_sections, normalize_sections

    if request.method == 'POST':
        if not can_manage_worship():
            flash('Only worship managers can add pack songs.', 'error')
            return redirect(url_for('worship.songs_public_domain'))
        ids = request.form.getlist('pack_id')
        if not ids:
            flash('Select at least one song to add.', 'error')
            return redirect(url_for('worship.songs_public_domain'))
        items = []
        for pack_id in ids:
            song = get_public_domain_song(pack_id)
            if not song:
                continue
            sections = normalize_sections(None, song.get('lyrics_raw'))
            if not sections:
                sections = parse_chart_to_sections(song.get('lyrics_raw') or '')
            items.append({
                'title': song['title'],
                'artist': song.get('artist'),
                'ccli_song_number': song.get('ccli_song_number') or None,
                'copyright_line': song.get('copyright_line') or 'Public Domain',
                'lyrics_raw': song.get('lyrics_raw'),
                'sections': sections,
                'notes_permanent': 'From MyVine public-domain starter pack. Simple chords for church use.',
            })
        if not items:
            flash('No valid songs selected.', 'error')
            return redirect(url_for('worship.songs_public_domain'))
        # Prefer play_order on save via sections
        for it in items:
            if it.get('sections') and not it.get('play_order'):
                it['play_order'] = default_play_order_from_sections(it['sections'])
        result = song_model.bulk_import_songs(items, session['user_id'])
        # bulk_import may not save play_order — update after
        flash(
            f"Added pack songs: {result['created']} new, {result['updated']} updated, "
            f"{result['skipped']} skipped.",
            'success',
        )
        return redirect(url_for('worship.songs_list'))

    pack = list_public_domain_pack()
    # Mark already in library (by title match)
    existing_titles = {
        (s.get('title') or '').strip().lower()
        for s in (song_model.list_songs() or [])
    }
    for p in pack:
        p['in_library'] = p['title'].strip().lower() in existing_titles

    preview = None
    pid = request.args.get('preview')
    if pid:
        preview = get_public_domain_song(pid)

    return render_template(
        'worship/songs_public_domain.html',
        pack=pack,
        preview=preview,
        can_manage=can_manage_worship(),
    )


@worship_bp.route('/songs/new', methods=['GET', 'POST'])
@worship_required
def song_new():
    if not can_manage_worship():
        flash('Only worship managers can edit the song library.', 'error')
        return redirect(url_for('worship.songs_list'))

    if request.method == 'POST':
        data = _song_form_data(save_chord_upload(request.files.get('chords_file'), current_app))
        if not data['title']:
            flash('Song title is required.', 'error')
        else:
            song_id = song_model.save_song(data, session['user_id'])
            flash('Song saved.', 'success')
            return redirect(url_for('worship.song_edit', song_id=song_id))

    return render_template('worship/song_edit.html', song=None, can_manage=True)


@worship_bp.route('/songs/<int:song_id>/edit', methods=['GET', 'POST'])
@worship_required
def song_edit(song_id):
    song = song_model.get_song(song_id)
    if not song:
        abort(404)
    if not can_manage_worship():
        return render_template('worship/song_edit.html', song=song, can_manage=False)

    if request.method == 'POST':
        chords = song.get('chords_filename')
        uploaded = save_chord_upload(request.files.get('chords_file'), current_app)
        if uploaded:
            chords = uploaded
        data = _song_form_data(chords)
        if not data['title']:
            flash('Song title is required.', 'error')
        else:
            song_model.save_song(data, session['user_id'], song_id=song_id)
            flash('Song updated.', 'success')
            return redirect(url_for('worship.song_edit', song_id=song_id))
        song = song_model.get_song(song_id)

    return render_template('worship/song_edit.html', song=song, can_manage=True)


@worship_bp.route('/songs/<int:song_id>/delete', methods=['POST'])
@worship_required
def song_delete(song_id):
    if not can_manage_worship():
        flash('Only worship managers can delete songs.', 'error')
        return redirect(url_for('worship.songs_list'))
    song_model.delete_song(song_id)
    flash('Song deleted.', 'success')
    return redirect(url_for('worship.songs_list'))


@worship_bp.route('/chords/<filename>')
@worship_required
def chord_file(filename):
    return send_from_directory(chords_upload_dir(current_app), filename)


@worship_bp.route('/templates')
@worship_required
def templates_list():
    templates = template_model.list_templates()
    existing_days = {t['weekday'] for t in templates}
    return render_template(
        'worship/templates_list.html',
        templates=templates,
        weekday_names=template_model.WEEKDAY_NAMES,
        existing_days=existing_days,
        can_manage=can_manage_worship(),
    )


@worship_bp.route('/templates/<int:weekday>/edit', methods=['GET', 'POST'])
@worship_required
def template_edit(weekday):
    if weekday < 0 or weekday > 6:
        abort(404)
    if not can_manage_worship():
        flash('Only worship managers can edit weekly templates.', 'error')
        return redirect(url_for('worship.templates_list'))

    template_id = template_model.ensure_template(
        weekday, session['user_id'],
        f"{template_model.WEEKDAY_NAMES[weekday]} Worship",
    )
    template = template_model.get_template(template_id)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_song':
            song_id = request.form.get('song_id')
            if song_id:
                template_model.add_song_to_template(template_id, int(song_id))
                flash('Song added to weekly template.', 'success')
        elif action == 'remove_song':
            item_id = request.form.get('item_id')
            if item_id:
                template_model.remove_template_song(int(item_id), template_id)
                flash('Song removed.', 'success')
        elif action == 'save':
            data = _setlist_form_data()
            if not data['title']:
                flash('Title is required.', 'error')
            else:
                template_model.update_template(template_id, data, session['user_id'])
                template_model.save_template_assignments(template_id, _assignment_rows_from_form())
                _save_member_notes_from_form(template_id=template_id)
                flash('Weekly template saved.', 'success')
        return redirect(url_for('worship.template_edit', weekday=weekday))

    member_notes = {n['user_id']: n for n in notes_model.get_notes_for_setlist(template_id=template_id)}
    public_token = template_model.ensure_public_token_template(template_id)
    return render_template(
        'worship/template_edit.html',
        template=template,
        weekday=weekday,
        songs=template.get('songs') or [],
        all_songs=song_model.list_songs(),
        members=get_worship_team_members(),
        default_roles=DEFAULT_ROLES,
        member_notes=member_notes,
        public_token=public_token,
        can_manage=True,
    )


@worship_bp.route('/plan/<date_str>', methods=['GET', 'POST'])
@worship_required
def plan_for_date(date_str):
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        abort(404)

    if request.method == 'POST' and request.form.get('action') == 'customize':
        if not can_manage_worship():
            flash('Only managers can customize a date.', 'error')
            return redirect(url_for('worship.plan_for_date', date_str=date_str))
        setlist_id = template_model.create_override_from_template(date_str, session['user_id'])
        if setlist_id:
            flash('Created a custom plan for this date.', 'success')
            return redirect(url_for('worship.setlist_edit', setlist_id=setlist_id))
        flash('No weekly template exists for this weekday yet.', 'warning')
        return redirect(url_for('worship.templates_list'))

    plan = template_model.get_setlist_for_date(date_str)
    public_token = None
    if plan:
        if plan.get('source') == 'override' and plan.get('id'):
            public_token = setlist_model.ensure_public_token(plan['id'])
            if request.method == 'GET':
                return redirect(url_for('worship.setlist_edit', setlist_id=plan['id']))
        elif plan.get('template_id'):
            public_token = template_model.ensure_public_token_template(plan['template_id'])

    member_notes = {}
    if plan and plan.get('template_id'):
        member_notes = {n['user_id']: n for n in notes_model.get_notes_for_setlist(template_id=plan['template_id'])}

    return render_template(
        'worship/plan_view.html',
        plan=plan,
        date_str=date_str,
        public_token=public_token,
        member_notes=member_notes,
        can_manage=can_manage_worship(),
    )


@worship_bp.route('/setlists')
@worship_required
def setlists_list():
    return render_template(
        'worship/setlists_list.html',
        setlists=setlist_model.list_setlists(),
        templates=template_model.list_templates(),
        can_manage=can_manage_worship(),
    )


@worship_bp.route('/setlists/new', methods=['GET', 'POST'])
@worship_required
def setlist_new():
    if not can_manage_worship():
        flash('Only worship managers can create setlists.', 'error')
        return redirect(url_for('worship.setlists_list'))

    if request.method == 'POST':
        data = _setlist_form_data()
        if not data['title']:
            flash('Setlist title is required.', 'error')
        else:
            setlist_id = setlist_model.create_setlist(data, session['user_id'])
            setlist_model.ensure_public_token(setlist_id)
            setlist_model.apply_defaults_to_setlist(setlist_id)
            rows = _assignment_rows_from_form()
            if rows:
                setlist_model.save_assignments(setlist_id, rows)
            flash('Setlist created.', 'success')
            return redirect(url_for('worship.setlist_edit', setlist_id=setlist_id))

    members = get_worship_team_members()
    defaults = setlist_model.get_default_assignments()
    return render_template(
        'worship/setlist_edit.html',
        setlist=None,
        songs=[],
        all_songs=song_model.list_songs(),
        members=members,
        default_roles=DEFAULT_ROLES,
        defaults=defaults,
        member_notes={},
        public_token=None,
        can_manage=True,
    )


@worship_bp.route('/setlists/<int:setlist_id>/edit', methods=['GET', 'POST'])
@worship_required
def setlist_edit(setlist_id):
    setlist = setlist_model.get_setlist(setlist_id)
    if not setlist:
        abort(404)

    if request.method == 'POST':
        if not can_manage_worship():
            flash('Only worship managers can edit setlists.', 'error')
            return redirect(url_for('worship.setlist_edit', setlist_id=setlist_id))

        action = request.form.get('action')
        if action == 'add_song':
            song_id = request.form.get('song_id')
            if song_id:
                setlist_model.add_song_to_setlist(setlist_id, int(song_id))
                flash('Song added to setlist.', 'success')
        elif action == 'remove_song':
            item_id = request.form.get('item_id')
            if item_id:
                setlist_model.remove_setlist_song(int(item_id), setlist_id)
                flash('Song removed.', 'success')
        elif action == 'confirm_service':
            if setlist.get('service_date'):
                song_ids = [s['song_id'] for s in (setlist_model.get_setlist(setlist_id).get('songs') or [])]
                n = plays_model.log_service_plays(
                    setlist_id,
                    str(setlist['service_date']),
                    song_ids,
                    session['user_id'],
                )
                flash(f'Logged {n} song(s) as played in service (not rehearsal).', 'success')
        elif action == 'save':
            data = _setlist_form_data()
            if not data['title']:
                flash('Setlist title is required.', 'error')
            else:
                setlist_model.update_setlist(setlist_id, data, session['user_id'])
                setlist_model.save_assignments(setlist_id, _assignment_rows_from_form())
                _save_member_notes_from_form(setlist_id=setlist_id)
                setlist_model.ensure_public_token(setlist_id)
                flash('Setlist saved.', 'success')
        return redirect(url_for('worship.setlist_edit', setlist_id=setlist_id))

    members = get_worship_team_members()
    member_notes = {n['user_id']: n for n in notes_model.get_notes_for_setlist(setlist_id=setlist_id)}
    public_token = setlist_model.ensure_public_token(setlist_id)
    return render_template(
        'worship/setlist_edit.html',
        setlist=setlist,
        songs=setlist.get('songs') or [],
        all_songs=song_model.list_songs(),
        members=members,
        default_roles=DEFAULT_ROLES,
        defaults=setlist_model.get_default_assignments(),
        member_notes=member_notes,
        public_token=public_token,
        can_manage=can_manage_worship(),
    )


@worship_bp.route('/setlists/<int:setlist_id>/delete', methods=['POST'])
@worship_required
def setlist_delete(setlist_id):
    if not can_manage_worship():
        flash('Only worship managers can delete setlists.', 'error')
        return redirect(url_for('worship.setlists_list'))
    setlist_model.delete_setlist(setlist_id)
    flash('Setlist deleted.', 'success')
    return redirect(url_for('worship.setlists_list'))


@worship_bp.route('/setlists/<int:setlist_id>/email', methods=['POST'])
@worship_required
def setlist_email(setlist_id):
    if not can_manage_worship():
        flash('Only worship managers can email the team.', 'error')
        return redirect(url_for('worship.setlist_edit', setlist_id=setlist_id))

    setlist = setlist_model.get_setlist(setlist_id)
    if not setlist:
        abort(404)

    sent = skipped = 0
    lines_base = [f"Worship Team - {setlist['title']}", '']
    if setlist.get('service_date'):
        lines_base.append(f"Service date: {setlist['service_date']}")
    if setlist.get('service_time'):
        lines_base.append(f"Service time: {setlist['service_time']}")
    if setlist.get('rehearsal_time'):
        lines_base.append(f"Rehearsal: {setlist['rehearsal_time']}")
    if setlist.get('rehearsal_location'):
        lines_base.append(f"Location: {setlist['rehearsal_location']}")
    lines_base.append('')
    lines_base.append('Setlist:')
    for i, s in enumerate(setlist.get('songs') or [], 1):
        artist = f" - {s['artist']}" if s.get('artist') else ''
        lines_base.append(f"  {i}. {s['title']}{artist}")

    for a in setlist.get('assignments') or []:
        uid = a.get('user_id')
        email = a.get('email')
        if not email or not uid:
            continue
        if not plays_model.user_accepts_worship_email(uid):
            skipped += 1
            continue
        personal = notes_model.get_note_for_user(uid, setlist_id=setlist_id)
        lines = list(lines_base)
        lines.insert(2, f"Your role: {a['role_name']}")
        if personal:
            lines.append('')
            lines.append('Note for you:')
            lines.append(personal)
        if setlist.get('notes'):
            lines.append('')
            lines.append('Team notes:')
            lines.append(setlist['notes'])
        try:
            send_email(email, f"Worship setlist: {setlist['title']}", '\n'.join(lines))
            sent += 1
        except Exception:
            pass

    msg = f'Email sent to {sent} member{"s" if sent != 1 else ""}.'
    if skipped:
        msg += f' {skipped} skipped (opted out of worship emails).'
    flash(msg, 'success' if sent else 'warning')
    return redirect(url_for('worship.setlist_edit', setlist_id=setlist_id))


@worship_bp.route('/history')
@worship_required
def history():
    return render_template(
        'worship/history.html',
        history=plays_model.get_play_history(),
        stats=plays_model.get_song_play_counts(),
    )


@worship_bp.route('/defaults', methods=['GET', 'POST'])
@worship_required
def defaults():
    if not can_manage_worship():
        flash('Only worship managers can edit default assignments.', 'error')
        return redirect(url_for('worship.dashboard'))

    if request.method == 'POST':
        setlist_model.save_default_assignments(_assignment_rows_from_form())
        flash('Default role assignments saved.', 'success')
        return redirect(url_for('worship.defaults'))

    return render_template(
        'worship/defaults.html',
        defaults=setlist_model.get_default_assignments(),
        members=get_worship_team_members(),
        default_roles=DEFAULT_ROLES,
    )


@worship_bp.route('/podium/<int:setlist_id>')
@worship_required
def podium(setlist_id):
    setlist = setlist_model.get_setlist(setlist_id)
    if not setlist:
        abort(404)
    return render_template('worship/podium.html', setlist=setlist, public_mode=False)


@worship_bp.route('/screen/<token>')
def public_screen(token):
    """Public auditorium display - song titles only, no login."""
    plan = template_model.get_by_public_token(token)
    if not plan:
        abort(404)
    return render_template('worship/public_screen.html', plan=plan)


@worship_bp.route('/prompter/<token>')
def public_prompter(token):
    """Secret-link prompter with full lyrics - for sanctuary PC without login."""
    plan = template_model.get_by_public_token(token)
    if not plan:
        abort(404)
    return render_template('worship/podium.html', setlist=plan, public_mode=True)