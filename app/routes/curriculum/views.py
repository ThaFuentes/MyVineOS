# Learner study experience for published curriculum courses.

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from app.models.log import log_change
from app.models.pastoral import curriculum as cur_model
from . import curriculum_bp


def _viewer():
    return cur_model.viewer_from_session(session)


def _guard_series(series, viewer, *, next_url=None):
    if not series or series.get('status') != 'published':
        flash('This course is not available.', 'error')
        return redirect(url_for('curriculum.catalog'))
    if cur_model.can_view_course(series, viewer):
        return None
    reason = cur_model.deny_reason(series, viewer)
    if viewer.get('is_guest'):
        flash(reason or 'Log in to take this course.', 'error')
        return redirect(url_for('auth.login', next=next_url or request.url))
    flash(reason or 'This course is limited to a different group.', 'error')
    return redirect(url_for('curriculum.catalog'))


@curriculum_bp.route('/')
def catalog():
    q = (request.args.get('q') or '').strip()
    audience = request.args.get('audience') or ''
    viewer = _viewer()
    series = cur_model.list_series(
        for_learners=True,
        viewer=viewer,
        audience=audience or None,
        search=q or None,
    )
    progress_map = {}
    uid = viewer.get('user_id')
    if uid:
        for s in series:
            if cur_model.can_record_progress(s, viewer):
                progress_map[s['id']] = cur_model.get_user_progress(uid, s['id']).get('enrollment') or {}
    return render_template(
        'curriculum/catalog.html',
        series_list=series,
        progress_map=progress_map,
        search_q=q,
        filter_audience=audience,
        audiences=cur_model.AUDIENCES,
        viewer=viewer,
        is_guest=viewer.get('is_guest'),
    )


@curriculum_bp.route('/course/<int:series_id>')
def course(series_id):
    series = cur_model.get_series(series_id)
    viewer = _viewer()
    bounced = _guard_series(series, viewer)
    if bounced:
        return bounced

    lessons = cur_model.list_lessons(series_id, published_only=True)
    saves = cur_model.can_record_progress(series, viewer)
    progress = {'enrollment': {}, 'by_block': {}}
    if saves:
        cur_model.ensure_enrollment(viewer['user_id'], series_id)
        progress = cur_model.get_user_progress(viewer['user_id'], series_id)
        log_change(
            viewer['user_id'],
            'view',
            series_id,
            change_details=f'Opened study course: {series.get("title")}',
        )
    return render_template(
        'curriculum/course.html',
        series=series,
        lessons=lessons,
        progress=progress,
        viewer=viewer,
        is_guest=viewer.get('is_guest'),
        saves_progress=saves,
    )


@curriculum_bp.route('/lesson/<int:lesson_id>', methods=['GET', 'POST'])
def lesson(lesson_id):
    lesson = cur_model.get_lesson(lesson_id)
    if not lesson:
        flash('Lesson not found.', 'error')
        return redirect(url_for('curriculum.catalog'))
    series = cur_model.get_series(lesson['series_id'])
    viewer = _viewer()
    bounced = _guard_series(series, viewer)
    if bounced:
        return bounced
    if lesson.get('status') != 'published':
        flash('This lesson is not published yet.', 'error')
        return redirect(url_for('curriculum.course', series_id=series['id']))

    saves = cur_model.can_record_progress(series, viewer)
    uid = viewer.get('user_id') if saves else None
    if saves and uid:
        cur_model.mark_lesson_viewed(uid, series['id'], lesson_id)
    blocks = cur_model.list_blocks(lesson_id)
    progress = cur_model.get_user_progress(uid, series['id']) if uid else {'enrollment': {}, 'by_block': {}}

    if request.method == 'POST':
        try:
            block_id = int(request.form.get('block_id') or 0)
        except (TypeError, ValueError):
            block_id = 0
        block = cur_model.get_block(block_id)
        if not block or block['lesson_id'] != lesson_id:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'ok': False, 'error': 'Invalid block'}), 400
            flash('That question is not on this lesson.', 'error')
            return redirect(url_for('curriculum.lesson', lesson_id=lesson_id))

        btype = block['block_type']
        if btype == 'multiple_choice':
            submitted = request.form.get('answer')
        elif btype == 'true_false':
            submitted = request.form.get('answer')
        elif btype == 'fill_blank':
            multi = request.form.getlist('answer')
            submitted = multi if len(multi) > 1 else (request.form.get('answer') or (multi[0] if multi else ''))
        else:
            submitted = None

        result = cur_model.check_answer(block, submitted)
        if saves and uid:
            cur_model.record_block_answer(uid, series['id'], lesson_id, block_id, submitted, result)

        wants_json = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.accept_mimetypes.best == 'application/json'
        )
        if wants_json:
            return jsonify({'ok': True, 'saved': bool(saves), **result})
        flash(
            'Correct! ' + (result.get('feedback') or '') if result.get('correct')
            else 'Not quite. ' + (result.get('feedback') or 'Review and try again.'),
            'success' if result.get('correct') else 'error',
        )
        return redirect(url_for('curriculum.lesson', lesson_id=lesson_id) + f'#block-{block_id}')

    siblings = cur_model.list_lessons(series['id'], published_only=True)
    return render_template(
        'curriculum/lesson_study.html',
        series=series,
        lesson=lesson,
        blocks=blocks,
        progress=progress,
        siblings=siblings,
        is_preview=False,
        saves_progress=saves,
        is_guest=viewer.get('is_guest'),
        viewer=viewer,
        fill_blank_parts=cur_model.fill_blank_parts,
        youtube_embed_url=cur_model.youtube_embed_url,
    )


@curriculum_bp.route('/media/<path:filename>')
def media_file(filename):
    viewer = _viewer()
    if not cur_model.media_allowed_for_viewer(filename, viewer):
        abort(404)
    return send_from_directory(cur_model.curriculum_upload_dir(current_app), filename)
