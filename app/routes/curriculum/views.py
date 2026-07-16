# Learner study experience for published curriculum courses.

from flask import (
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

from app.utils.decorators import login_required
from app.models.log import log_change
from app.models.pastoral import curriculum as cur_model
from . import curriculum_bp


@curriculum_bp.route('/')
@login_required
def catalog():
    q = (request.args.get('q') or '').strip()
    audience = request.args.get('audience') or ''
    series = cur_model.list_series(
        for_learners=True,
        audience=audience or None,
        search=q or None,
    )
    # Attach personal enrollment if any
    uid = session['user_id']
    progress_map = {}
    for s in series:
        progress_map[s['id']] = cur_model.get_user_progress(uid, s['id']).get('enrollment') or {}
    return render_template(
        'curriculum/catalog.html',
        series_list=series,
        progress_map=progress_map,
        search_q=q,
        filter_audience=audience,
        audiences=cur_model.AUDIENCES,
    )


@curriculum_bp.route('/course/<int:series_id>')
@login_required
def course(series_id):
    series = cur_model.get_series(series_id)
    if not series or series.get('status') != 'published':
        flash('This course is not available.', 'error')
        return redirect(url_for('curriculum.catalog'))
    if series.get('visibility') not in ('public', 'members'):
        flash('This course is pastoral-only.', 'error')
        return redirect(url_for('curriculum.catalog'))

    lessons = cur_model.list_lessons(series_id, published_only=True)
    progress = cur_model.get_user_progress(session['user_id'], series_id)
    cur_model.ensure_enrollment(session['user_id'], series_id)
    log_change(session['user_id'], 'view', series_id, change_details=f'Opened study course: {series.get("title")}')
    return render_template(
        'curriculum/course.html',
        series=series,
        lessons=lessons,
        progress=progress,
    )


@curriculum_bp.route('/lesson/<int:lesson_id>', methods=['GET', 'POST'])
@login_required
def lesson(lesson_id):
    lesson = cur_model.get_lesson(lesson_id)
    if not lesson:
        flash('Lesson not found.', 'error')
        return redirect(url_for('curriculum.catalog'))
    series = cur_model.get_series(lesson['series_id'])
    if not series or series.get('status') != 'published' or lesson.get('status') != 'published':
        flash('This lesson is not published yet.', 'error')
        return redirect(url_for('curriculum.catalog'))

    uid = session['user_id']
    cur_model.mark_lesson_viewed(uid, series['id'], lesson_id)
    blocks = cur_model.list_blocks(lesson_id)
    progress = cur_model.get_user_progress(uid, series['id'])

    if request.method == 'POST':
        block_id = int(request.form.get('block_id') or 0)
        block = cur_model.get_block(block_id)
        if not block or block['lesson_id'] != lesson_id:
            return jsonify({'ok': False, 'error': 'Invalid block'}), 400

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
        cur_model.record_block_answer(uid, series['id'], lesson_id, block_id, submitted, result)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json':
            return jsonify({'ok': True, **result})
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
        fill_blank_parts=cur_model.fill_blank_parts,
        youtube_embed_url=cur_model.youtube_embed_url,
    )


@curriculum_bp.route('/media/<path:filename>')
@login_required
def media_file(filename):
    return send_from_directory(cur_model.curriculum_upload_dir(current_app), filename)
