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
    can_manage_worship, can_edit_worship_charts, can_view_worship,
    get_worship_team_members, get_worship_leaders,
)
from app.models.worship import charts as chart_model
from app.utils.emailer import send_email

from . import worship_bp, worship_required
from .utils import DEFAULT_ROLES, chords_upload_dir, save_chord_upload


def _parse_sections_form():
    """Prefer structured section cards from the song editor; fall back to JSON/lyrics."""
    ids = request.form.getlist('sec_id[]')
    types = request.form.getlist('sec_type[]')
    labels = request.form.getlist('sec_label[]')
    contents = request.form.getlist('sec_content[]')
    layers_raw = request.form.getlist('sec_layers[]')
    if ids or labels or contents:
        sections = []
        n = max(len(ids), len(types), len(labels), len(contents), len(layers_raw))
        for i in range(n):
            content = (contents[i] if i < len(contents) else '') or ''
            content = content.strip()
            layers = None
            if i < len(layers_raw) and layers_raw[i]:
                try:
                    layers = json.loads(layers_raw[i])
                except (TypeError, json.JSONDecodeError):
                    layers = None
            # Keep sections that have layers even if content empty briefly
            if not content and not layers:
                continue
            if not content and layers:
                content = (layers.get('lyrics') or '').strip()
            sid = (ids[i] if i < len(ids) else '') or ''
            stype = (types[i] if i < len(types) else '') or 'verse'
            label = (labels[i] if i < len(labels) else '') or stype.title()
            sec = {
                'id': sid.strip() or f's{i + 1}',
                'type': stype.strip().lower() or 'verse',
                'label': label.strip() or 'Section',
                'content': content,
                'sort': i + 1,
                'repeat': 1,
            }
            if layers:
                sec['layers'] = layers
            sections.append(sec)
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
    """Parse worship assignment rows: member and/or non-member guest_name."""
    roles = request.form.getlist('assign_role[]')
    users = request.form.getlist('assign_user[]')
    guests = request.form.getlist('assign_guest[]')
    while len(users) < len(roles):
        users.append('')
    while len(guests) < len(roles):
        guests.append('')
    rows = []
    for role, uid, guest in zip(roles, users, guests):
        role = (role or '').strip()
        if not role:
            continue
        guest = (guest or '').strip() or None
        if uid in ('', 'None', None):
            uid = None
        else:
            try:
                uid = int(uid)
            except (TypeError, ValueError):
                uid = None
        if uid:
            guest = None
        # Allow empty person (role shell) or member or guest
        rows.append({'role_name': role, 'user_id': uid, 'guest_name': guest})
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
        setlists=setlist_model.list_setlists(40),
        weekly_templates=template_model.list_templates(),
    )


@worship_bp.route('/songs/send-to-setlist', methods=['POST'])
@worship_required
def songs_send_to_setlist():
    """Bulk-add checked library songs to a setlist, weekly day default, or entire week."""
    if not can_manage_worship():
        flash('Only worship managers can send songs to setlists.', 'error')
        return redirect(url_for('worship.songs_list'))

    raw_ids = request.form.getlist('song_ids')
    song_ids = []
    for r in raw_ids:
        try:
            song_ids.append(int(r))
        except (TypeError, ValueError):
            continue
    # de-dupe preserve order
    seen = set()
    song_ids = [i for i in song_ids if not (i in seen or seen.add(i))]
    target = (request.form.get('target') or '').strip()

    if not song_ids:
        flash('Select at least one song.', 'error')
        return redirect(url_for('worship.songs_list'))
    if not target:
        flash('Choose a destination setlist or weekly default.', 'error')
        return redirect(url_for('worship.songs_list'))

    uid = session.get('user_id')
    added = 0
    destinations = 0

    try:
        if target == 'week_all':
            # All weekly defaults (practice week) — ensure each weekday template exists
            for weekday in range(7):
                tid = template_model.ensure_template(weekday, uid)
                destinations += 1
                for sid in song_ids:
                    template_model.add_song_to_template(tid, sid)
                    added += 1
            flash(
                f'Added {len(song_ids)} song(s) to all weekly defaults '
                f'({destinations} days × {len(song_ids)} songs).',
                'success',
            )
        elif target.startswith('setlist:'):
            setlist_id = int(target.split(':', 1)[1])
            if not setlist_model.get_setlist(setlist_id):
                flash('Setlist not found.', 'error')
                return redirect(url_for('worship.songs_list'))
            for sid in song_ids:
                setlist_model.add_song_to_setlist(setlist_id, sid)
                added += 1
            flash(f'Added {added} song(s) to the setlist.', 'success')
            return redirect(url_for('worship.setlist_edit', setlist_id=setlist_id))
        elif target.startswith('template:'):
            weekday = int(target.split(':', 1)[1])
            if weekday < 0 or weekday > 6:
                flash('Invalid weekday.', 'error')
                return redirect(url_for('worship.songs_list'))
            tid = template_model.ensure_template(weekday, uid)
            for sid in song_ids:
                template_model.add_song_to_template(tid, sid)
                added += 1
            flash(f'Added {added} song(s) to that day\'s weekly default.', 'success')
            return redirect(url_for('worship.template_edit', weekday=weekday))
        else:
            flash('Unknown destination.', 'error')
            return redirect(url_for('worship.songs_list'))
    except Exception as exc:
        flash(f'Could not send songs: {exc}', 'error')
        return redirect(url_for('worship.songs_list'))

    return redirect(url_for('worship.songs_list'))


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
                    chart_model.ensure_default_charts_for_song(
                        song_id,
                        session['user_id'],
                        initial_sections=data.get('sections') or [],
                        initial_play_order=data.get('play_order') or [],
                    )
                    flash(
                        f"Song saved ({parsed.get('parse_mode', 'rules')}"
                        + (', AI assisted' if parsed.get('ai_used') else '')
                        + f", {len(data['sections'])} sections). "
                        f"Music Studio is open — place chords/notes above lyrics, TAB, or drums.",
                        'success',
                    )
                    return redirect(url_for('worship.song_edit', song_id=song_id, chart='full_band'))
                chart_preview = parsed
                flash(
                    'Chart parsed — save to open Music Studio (chords/melody above lyrics, TAB, drums). '
                    'AI only structures what you pasted; it does not invent notes.',
                    'success',
                )
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
    """JSON API: parse pasted chart / upload text with rules or AI (team chart editors)."""
    if not can_edit_worship_charts():
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
    # Leaders/managers add library songs; team members edit role notes on existing songs
    if not can_manage_worship():
        flash('Worship leaders/managers add songs to the library. Team members open a song and edit their instrument chart with musical notes.', 'error')
        return redirect(url_for('worship.songs_list'))

    if request.method == 'POST':
        data = _song_form_data(save_chord_upload(request.files.get('chords_file'), current_app))
        if not data['title']:
            flash('Song title is required.', 'error')
        else:
            song_id = song_model.save_song(data, session['user_id'])
            # Seed every role chart with sections + musical layers (chords/melody/TAB/drums)
            chart_model.ensure_default_charts_for_song(
                song_id,
                session['user_id'],
                initial_sections=data.get('sections') or [],
                initial_play_order=data.get('play_order') or [],
            )
            # Persist primary chart with layers explicitly
            charts = chart_model.list_charts(song_id)
            primary = next((c for c in charts if c.get('chart_key') == 'full_band'), None)
            if primary and data.get('sections'):
                chart_model.save_chart(
                    song_id,
                    'full_band',
                    {
                        'display_name': primary.get('display_name') or 'Full band (default)',
                        'instrument_family': 'full',
                        'notation': 'chordpro',
                        'show_chords': True,
                        'show_lyrics': True,
                        'is_primary': True,
                        'sections': data.get('sections') or [],
                        'play_order': data.get('play_order') or [],
                        'notes': data.get('notes_permanent') or '',
                    },
                    session['user_id'],
                    chart_id=int(primary['id']),
                )
            flash(
                'Song created with Music Studio. Add chords/melody above lyrics, guitar/bass TAB, or drums — '
                'then switch role tabs so each person can customize their part.',
                'success',
            )
            return redirect(url_for('worship.song_edit', song_id=song_id, chart='full_band'))

    return render_template(
        'worship/song_edit.html',
        song=None,
        can_manage=True,
        can_edit_charts=True,
        charts=[],
        active_chart=None,
        chart_key='full_band',
        ccli_settings=chart_model.get_ccli_settings(),
        songselect_url=chart_model.songselect_search_url(),
    )


@worship_bp.route('/songs/<int:song_id>/edit', methods=['GET', 'POST'])
@worship_required
def song_edit(song_id):
    song = song_model.get_song(song_id)
    if not song:
        abort(404)

    can_manage = can_manage_worship()
    can_charts = can_edit_worship_charts()
    chart_key = (request.args.get('chart') or request.form.get('chart_key') or 'full_band').strip()
    charts = song.get('charts') or chart_model.list_charts(song_id)
    if not charts:
        charts = chart_model.ensure_default_charts_for_song(song_id, session.get('user_id'))
    active = next((c for c in charts if c.get('chart_key') == chart_key), None)
    if not active and charts:
        active = charts[0]
        chart_key = active.get('chart_key') or 'full_band'

    if request.method == 'POST':
        action = (request.form.get('action') or 'save').strip()
        if action == 'save_personal_note' and can_view_worship() and active:
            chart_model.save_user_chart_note(
                int(active['id']),
                session['user_id'],
                request.form.get('personal_note') or '',
            )
            flash('Your personal chart note saved (does not change the master chart).', 'success')
            return redirect(url_for('worship.song_edit', song_id=song_id, chart=chart_key))

        if action == 'save_ccli_settings' and can_manage:
            chart_model.save_ccli_settings({
                'ccli_license_number': request.form.get('ccli_license_number'),
                'organization_name': request.form.get('organization_name'),
                'notes': request.form.get('ccli_org_notes'),
            }, session['user_id'])
            flash('Church CCLI license settings saved (for your records only).', 'success')
            return redirect(url_for('worship.song_edit', song_id=song_id, chart=chart_key))

        if action in ('save', 'save_chart', 'save_metadata'):
            if action == 'save_metadata' and not can_manage:
                flash('Only managers can change song title/CCLI metadata.', 'error')
                return redirect(url_for('worship.song_edit', song_id=song_id, chart=chart_key))
            if action in ('save', 'save_chart') and not can_charts:
                flash('You do not have permission to edit charts.', 'error')
                return redirect(url_for('worship.song_edit', song_id=song_id, chart=chart_key))

            # Metadata (managers)
            if can_manage and action in ('save', 'save_metadata'):
                chords = song.get('chords_filename')
                uploaded = save_chord_upload(request.files.get('chords_file'), current_app)
                if uploaded:
                    chords = uploaded
                data = _song_form_data(chords)
                if not data['title']:
                    flash('Song title is required.', 'error')
                    return redirect(url_for('worship.song_edit', song_id=song_id, chart=chart_key))
                song_model.save_song(data, session['user_id'], song_id=song_id)

            # Role chart content (team + managers)
            if can_charts and action in ('save', 'save_chart') and active:
                chart_payload = {
                    'display_name': request.form.get('chart_display_name') or active.get('display_name'),
                    'instrument_family': active.get('instrument_family') or 'full',
                    'notation': request.form.get('chart_notation') or active.get('notation') or 'chordpro',
                    'notes': request.form.get('chart_notes') or '',
                    'capo': request.form.get('chart_capo'),
                    'show_chords': request.form.get('chart_show_chords') == '1',
                    'show_lyrics': request.form.get('chart_show_lyrics') == '1',
                    'is_primary': request.form.get('chart_is_primary') == '1' or chart_key == 'full_band',
                    'sections': _parse_sections_form(),
                    'play_order': _parse_play_order_form(),
                }
                # Prefer structured form sections when present
                if not chart_payload['sections']:
                    chart_payload['lyrics_raw'] = request.form.get('lyrics_raw') or ''
                chart_model.save_chart(
                    song_id,
                    chart_key,
                    chart_payload,
                    session['user_id'],
                    chart_id=int(active['id']),
                )
            flash('Saved.', 'success')
            return redirect(url_for('worship.song_edit', song_id=song_id, chart=chart_key))

        flash('Unknown action.', 'error')
        return redirect(url_for('worship.song_edit', song_id=song_id, chart=chart_key))

    # GET — show active chart sections in the editor
    if active:
        song = dict(song)
        song['sections'] = active.get('sections') or song.get('sections') or []
        song['play_order'] = active.get('play_order') or song.get('play_order') or []

    personal_note = ''
    if active and session.get('user_id'):
        personal_note = chart_model.get_user_chart_note(int(active['id']), session['user_id'])

    ccli_settings = chart_model.get_ccli_settings()
    songselect_url = chart_model.songselect_search_url(
        title=song.get('title') or '',
        artist=song.get('artist') or '',
        ccli=song.get('ccli_song_number') or '',
    )

    return render_template(
        'worship/song_edit.html',
        song=song,
        can_manage=can_manage,
        can_edit_charts=can_charts,
        charts=charts,
        active_chart=active,
        chart_key=chart_key,
        personal_note=personal_note,
        ccli_settings=ccli_settings,
        songselect_url=songselect_url,
    )


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


@worship_bp.route('/ccli-report', methods=['GET', 'POST'])
@worship_required
def ccli_report():
    """
    List CCLI song numbers used (played services) for day/week/month/year.
    Download CSV and/or email the list via Settings → Email SMTP.
    """
    from flask import Response
    from datetime import date as date_cls

    period = (request.values.get('period') or 'week').strip().lower()
    on_date = (request.values.get('on_date') or '').strip()
    start = (request.values.get('start') or '').strip()
    end = (request.values.get('end') or '').strip()
    include_planned = request.values.get('include_planned') == '1'
    if not on_date:
        on_date = date_cls.today().isoformat()

    start_d, end_d, period_label = plays_model.resolve_ccli_report_range(
        period, start=start, end=end, on_date=on_date
    )
    report = plays_model.get_ccli_usage_report(
        start_d, end_d, include_planned=include_planned
    )
    text_body = plays_model.format_ccli_report_text(report, period_label=period_label)

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip().lower()
        if action == 'download':
            csv_data = plays_model.format_ccli_report_csv(report)
            fname = f"ccli-usage-{start_d.isoformat()}-to-{end_d.isoformat()}.csv"
            return Response(
                csv_data,
                mimetype='text/csv; charset=utf-8',
                headers={
                    'Content-Disposition': f'attachment; filename="{fname}"',
                },
            )
        if action == 'email':
            if not can_manage_worship():
                flash('Only worship managers can email CCLI reports.', 'error')
                return redirect(url_for('worship.ccli_report', period=period, on_date=on_date))
            to_email = (request.form.get('to_email') or '').strip()
            if not to_email or '@' not in to_email:
                flash('Enter an email address to send the CCLI list.', 'error')
                return redirect(url_for(
                    'worship.ccli_report',
                    period=period, on_date=on_date, start=start, end=end,
                    include_planned='1' if include_planned else None,
                ))
            try:
                from app.utils.emailer import send_email
                subject = f'CCLI song usage — {period_label}'
                send_email(to_email, subject, text_body)
                flash(f'CCLI usage list emailed to {to_email}.', 'success')
            except Exception as e:
                flash(f'Could not send email: {e}', 'error')
            return redirect(url_for(
                'worship.ccli_report',
                period=period, on_date=on_date, start=start, end=end,
                include_planned='1' if include_planned else None,
            ))
        if action == 'download_and_email':
            # Email first, then return CSV download
            to_email = (request.form.get('to_email') or '').strip()
            email_ok = False
            if can_manage_worship() and to_email and '@' in to_email:
                try:
                    from app.utils.emailer import send_email
                    send_email(to_email, f'CCLI song usage — {period_label}', text_body)
                    email_ok = True
                except Exception as e:
                    flash(f'Email failed ({e}); download still provided.', 'warning')
            elif not to_email:
                flash('No email address — download only.', 'info')
            csv_data = plays_model.format_ccli_report_csv(report)
            fname = f"ccli-usage-{start_d.isoformat()}-to-{end_d.isoformat()}.csv"
            if email_ok:
                # Can't flash after Response easily — include note in filename path via cookie is overkill
                pass
            return Response(
                csv_data,
                mimetype='text/csv; charset=utf-8',
                headers={
                    'Content-Disposition': f'attachment; filename="{fname}"',
                    'X-CCLI-Email-Sent': '1' if email_ok else '0',
                },
            )

    return render_template(
        'worship/ccli_report.html',
        report=report,
        period=period,
        period_label=period_label,
        on_date=on_date,
        start=start_d.isoformat(),
        end=end_d.isoformat(),
        include_planned=include_planned,
        text_preview=text_body,
        can_manage=can_manage_worship(),
    )


@worship_bp.route('/defaults', methods=['GET', 'POST'])
@worship_required
def defaults():
    if not can_manage_worship():
        flash('Only worship managers can edit default assignments.', 'error')
        return redirect(url_for('worship.dashboard'))

    if request.method == 'POST':
        setlist_model.save_default_assignments(_assignment_rows_from_form())
        flash('Default role assignments saved (members and guests).', 'success')
        return redirect(url_for('worship.defaults'))

    # Always show standard roles; fill people/guests when saved; keep any custom extras
    stored = setlist_model.get_default_assignments() or []
    by_role = {}
    for d in stored:
        rn = (d.get('role_name') or '').strip()
        if rn:
            by_role[rn] = d
    defaults = []
    for role in DEFAULT_ROLES:
        if role in by_role:
            defaults.append(by_role.pop(role))
        else:
            defaults.append({
                'role_name': role,
                'user_id': None,
                'guest_name': None,
                'user_full_name': None,
            })
    for extra in by_role.values():
        defaults.append(extra)

    return render_template(
        'worship/defaults.html',
        defaults=defaults,
        members=get_worship_team_members(),
        default_roles=DEFAULT_ROLES,
    )


def _prompter_chart_options():
    """Instrument / role charts available for per-musician prompter."""
    from app.models.worship.charts import DEFAULT_CHART_DEFS
    return [
        {'chart_key': d['chart_key'], 'display_name': d['display_name']}
        for d in DEFAULT_CHART_DEFS
    ]


def _prompter_context(plan, *, public_mode: bool, chart_key: str, public_token=None):
    """Build podium template context: chart overlay, slide timings, user prefs."""
    from app.models.worship import prefs as prefs_model

    plan = setlist_model.apply_chart_to_plan(plan, chart_key)
    timings = {}
    for item in (plan.get('songs') or []):
        sid = item.get('song_id') or item.get('id')
        if not sid:
            continue
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            continue
        if sid not in timings:
            timings[str(sid)] = prefs_model.get_song_slide_timings(sid)

    user_id = session.get('user_id') if not public_mode else None
    user_prefs = prefs_model.get_user_prefs(user_id)
    return {
        'setlist': plan,
        'public_mode': public_mode,
        'chart_key': chart_key,
        'chart_options': _prompter_chart_options(),
        'public_token': public_token,
        'song_timings': timings,
        'user_prefs': user_prefs,
        'can_save_timings': (not public_mode) and bool(user_id),
        'can_save_prefs': (not public_mode) and bool(user_id),
    }


@worship_bp.route('/podium/<int:setlist_id>')
@worship_required
def podium(setlist_id):
    """Logged-in prompter; ?chart=bass (etc.) shows that musician's chart."""
    setlist = setlist_model.get_setlist(setlist_id)
    if not setlist:
        abort(404)
    chart_key = (request.args.get('chart') or request.args.get('role') or 'full_band').strip()
    return render_template(
        'worship/podium.html',
        **_prompter_context(
            setlist,
            public_mode=False,
            chart_key=chart_key,
            public_token=setlist.get('public_token'),
        ),
    )


@worship_bp.route('/screen/<token>')
def public_screen(token):
    """Public auditorium display - song titles only, no login."""
    plan = template_model.get_by_public_token(token)
    if not plan:
        abort(404)
    return render_template('worship/public_screen.html', plan=plan)


@worship_bp.route('/prompter/<token>')
def public_prompter(token):
    """Secret-link prompter — full lyrics, optional per-musician chart via ?chart=."""
    plan = template_model.get_by_public_token(token)
    if not plan:
        abort(404)
    chart_key = (request.args.get('chart') or request.args.get('role') or 'full_band').strip()
    return render_template(
        'worship/podium.html',
        **_prompter_context(
            plan,
            public_mode=True,
            chart_key=chart_key,
            public_token=token,
        ),
    )


@worship_bp.route('/api/prompter-prefs', methods=['POST'])
@worship_required
def prompter_prefs_save():
    """Save logged-in user's prompter display/advance prefs (JSON)."""
    from app.models.worship import prefs as prefs_model

    data = request.get_json(silent=True) or {}
    prefs = prefs_model.save_user_prefs(session.get('user_id'), data)
    return jsonify({'ok': True, 'prefs': prefs})


@worship_bp.route('/api/song-timings/<int:song_id>', methods=['POST'])
@worship_required
def song_timings_save(song_id):
    """
    Save continuous slide timing recording for a song.
    Body: { "offsets_ms": [0, 15200, 30400, ...] } absolute ms from song start.
    """
    from app.models.worship import prefs as prefs_model

    if not can_view_worship():
        return jsonify({'ok': False, 'error': 'denied'}), 403
    try:
        exists = song_model.get_song(song_id)
    except TypeError:
        exists = song_model.get_song(song_id)
    if not exists:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    data = request.get_json(silent=True) or {}
    offsets = data.get('offsets_ms') or data.get('timings') or []
    if not isinstance(offsets, list):
        return jsonify({'ok': False, 'error': 'bad_payload'}), 400
    saved = prefs_model.save_song_slide_timings(song_id, offsets)
    return jsonify({'ok': True, 'offsets_ms': saved})