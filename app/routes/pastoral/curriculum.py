# Pastoral Curriculum Studio — create & manage study courses with interactive lessons.

from __future__ import annotations

import json

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
    abort,
)

from . import pastoral_required
from app.models.log import log_change
from app.models.pastoral import curriculum as cur_model
from app.models.pastoral.content_export import (
    format_curriculum_series_markdown,
    format_curriculum_lesson_markdown,
    safe_filename,
    send_markdown_download,
)

# Nested under pastoral → endpoints: pastoral.curriculum_studio.*
curriculum_bp = Blueprint('curriculum_studio', __name__, url_prefix='/curriculum')


def _uid():
    return session.get('user_id')


# ── Library ─────────────────────────────────────────────────────────────────

@curriculum_bp.route('/')
@pastoral_required()
def library():
    status = request.args.get('status') or ''
    audience = request.args.get('audience') or ''
    q = (request.args.get('q') or '').strip()
    series = cur_model.list_series(
        status=status or None,
        audience=audience or None,
        search=q or None,
    )
    stats_map = {s['id']: cur_model.series_stats(s['id']) for s in series[:40]}
    log_change(_uid(), 'view', change_details='Opened Curriculum Studio')
    return render_template(
        'pastoral/curriculum/library.html',
        series_list=series,
        stats_map=stats_map,
        filter_status=status,
        filter_audience=audience,
        search_q=q,
        audiences=cur_model.AUDIENCES,
    )


@curriculum_bp.route('/new', methods=['GET', 'POST'])
@pastoral_required()
def series_new():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        if not title:
            flash('Give your course a title so learners know what to expect.', 'error')
            return redirect(url_for('pastoral.curriculum_studio.series_new'))
        sid = cur_model.create_series(
            {
                'title': title,
                'subtitle': request.form.get('subtitle'),
                'description': request.form.get('description'),
                'audience': request.form.get('audience') or 'everyone',
                'visibility': request.form.get('visibility') or 'members',
                'tags': request.form.get('tags'),
                'estimated_minutes': request.form.get('estimated_minutes') or None,
                'status': 'draft',
            },
            _uid(),
        )
        # Seed a first lesson so the builder never feels empty
        cur_model.create_lesson(sid, {'title': 'Lesson 1 — Getting Started', 'status': 'draft'})
        flash('Course created. Build your first lesson — make it something people finish.', 'success')
        log_change(_uid(), 'create', sid, change_details=f'Created curriculum series: {title}')
        return redirect(url_for('pastoral.curriculum_studio.series_edit', series_id=sid))
    return render_template(
        'pastoral/curriculum/series_form.html',
        series=None,
        audiences=cur_model.AUDIENCES,
    )


@curriculum_bp.route('/<int:series_id>/edit', methods=['GET', 'POST'])
@pastoral_required()
def series_edit(series_id):
    series = cur_model.get_series(series_id)
    if not series:
        flash('Course not found.', 'error')
        return redirect(url_for('pastoral.curriculum_studio.library'))

    if request.method == 'POST':
        action = request.form.get('action') or 'save'
        if action == 'delete':
            cur_model.delete_series(series_id)
            flash('Course deleted.', 'success')
            log_change(_uid(), 'delete', series_id, change_details='Deleted curriculum series')
            return redirect(url_for('pastoral.curriculum_studio.library'))
        if action == 'duplicate':
            new_id = cur_model.duplicate_series(series_id, _uid())
            flash('Course duplicated as a draft.', 'success')
            return redirect(url_for('pastoral.curriculum_studio.series_edit', series_id=new_id))
        if action == 'publish':
            cur_model.update_series(series_id, {
                'status': 'published',
                'title': request.form.get('title') or series['title'],
                'subtitle': request.form.get('subtitle'),
                'description': request.form.get('description'),
                'audience': request.form.get('audience'),
                'visibility': request.form.get('visibility') or 'members',
                'tags': request.form.get('tags'),
                'estimated_minutes': request.form.get('estimated_minutes') or None,
            })
            # Publish all draft lessons with content
            for les in cur_model.list_lessons(series_id):
                if les.get('status') != 'published':
                    cur_model.update_lesson(les['id'], {'status': 'published'})
            flash('Published! Members can study this course now.', 'success')
            log_change(_uid(), 'update', series_id, change_details='Published curriculum series')
            return redirect(url_for('pastoral.curriculum_studio.series_edit', series_id=series_id))
        if action == 'unpublish':
            cur_model.update_series(series_id, {'status': 'draft'})
            flash('Course moved back to draft.', 'info')
            return redirect(url_for('pastoral.curriculum_studio.series_edit', series_id=series_id))

        cur_model.update_series(series_id, {
            'title': request.form.get('title') or series['title'],
            'subtitle': request.form.get('subtitle'),
            'description': request.form.get('description'),
            'audience': request.form.get('audience'),
            'visibility': request.form.get('visibility') or 'members',
            'tags': request.form.get('tags'),
            'estimated_minutes': request.form.get('estimated_minutes') or None,
        })
        flash('Course details saved.', 'success')
        return redirect(url_for('pastoral.curriculum_studio.series_edit', series_id=series_id))

    lessons = cur_model.list_lessons(series_id)
    stats = cur_model.series_stats(series_id)
    return render_template(
        'pastoral/curriculum/series_edit.html',
        series=series,
        lessons=lessons,
        stats=stats,
        audiences=cur_model.AUDIENCES,
    )


@curriculum_bp.route('/<int:series_id>/download')
@pastoral_required()
def series_download(series_id):
    """Download full course (all lessons + blocks) as Markdown — creator keeps their content."""
    series = cur_model.get_series(series_id)
    if not series:
        abort(404)
    lessons = cur_model.list_lessons(series_id)
    packed = []
    for les in lessons:
        row = dict(les)
        row['blocks'] = cur_model.list_blocks(les['id'])
        packed.append(row)
    body = format_curriculum_series_markdown(series, packed)
    base = safe_filename(series.get('title') or f'course_{series_id}')
    log_change(_uid(), 'export', series_id, series.get('title'), 'Downloaded curriculum series as Markdown')
    return send_markdown_download(body, f'{base}.md')


@curriculum_bp.route('/lessons/<int:lesson_id>/download')
@pastoral_required()
def lesson_download(lesson_id):
    """Download one lesson with all blocks as Markdown."""
    lesson = cur_model.get_lesson(lesson_id)
    if not lesson:
        abort(404)
    series = cur_model.get_series(lesson['series_id']) or {'title': 'Course'}
    blocks = cur_model.list_blocks(lesson_id)
    body = format_curriculum_lesson_markdown(series, lesson, blocks)
    base = safe_filename(lesson.get('title') or f'lesson_{lesson_id}')
    log_change(_uid(), 'export', lesson_id, lesson.get('title'), 'Downloaded curriculum lesson as Markdown')
    return send_markdown_download(body, f'{base}.md')


@curriculum_bp.route('/<int:series_id>/lessons/new', methods=['POST'])
@pastoral_required()
def lesson_new(series_id):
    series = cur_model.get_series(series_id)
    if not series:
        flash('Course not found.', 'error')
        return redirect(url_for('pastoral.curriculum_studio.library'))
    title = (request.form.get('title') or '').strip() or f"Lesson {(len(cur_model.list_lessons(series_id)) + 1)}"
    lid = cur_model.create_lesson(series_id, {
        'title': title,
        'summary': request.form.get('summary'),
        'estimated_minutes': request.form.get('estimated_minutes') or None,
        'status': 'draft',
    })
    # Welcome block so the lesson isn't a blank canvas
    cur_model.create_block(lid, {
        'block_type': 'text',
        'title': 'Welcome',
        'body': 'Write your teaching notes, scripture context, or discussion prompts here.\n\nAdd images, videos, quiz questions, and fill-in-the-blank challenges from the toolbar.',
    })
    flash('Lesson created. Build it out with material and questions.', 'success')
    return redirect(url_for('pastoral.curriculum_studio.lesson_edit', lesson_id=lid))


@curriculum_bp.route('/lessons/<int:lesson_id>', methods=['GET', 'POST'])
@pastoral_required()
def lesson_edit(lesson_id):
    lesson = cur_model.get_lesson(lesson_id)
    if not lesson:
        flash('Lesson not found.', 'error')
        return redirect(url_for('pastoral.curriculum_studio.library'))
    series = cur_model.get_series(lesson['series_id'])

    if request.method == 'POST':
        action = request.form.get('action') or 'save_meta'
        if action == 'delete':
            sid = lesson['series_id']
            cur_model.delete_lesson(lesson_id)
            flash('Lesson deleted.', 'success')
            return redirect(url_for('pastoral.curriculum_studio.series_edit', series_id=sid))
        if action == 'save_meta':
            cur_model.update_lesson(lesson_id, {
                'title': request.form.get('title') or lesson['title'],
                'summary': request.form.get('summary'),
                'estimated_minutes': request.form.get('estimated_minutes') or None,
                'status': request.form.get('status') or lesson.get('status') or 'draft',
            })
            flash('Lesson saved.', 'success')
            return redirect(url_for('pastoral.curriculum_studio.lesson_edit', lesson_id=lesson_id))
        if action == 'add_block':
            btype = request.form.get('block_type') or 'text'
            data = _block_from_form(request, btype)
            # Handle file upload
            f = request.files.get('media_file')
            if f and f.filename:
                try:
                    kind = 'image' if btype == 'image' else 'video'
                    path = cur_model.save_curriculum_upload(f, current_app, kind=kind if btype in ('image', 'video') else 'image')
                    data['media_path'] = path
                except ValueError as e:
                    flash(str(e), 'error')
                    return redirect(url_for('pastoral.curriculum_studio.lesson_edit', lesson_id=lesson_id))
            if btype == 'video' and data.get('media_url'):
                data['media_url'] = cur_model.youtube_embed_url(data['media_url'])
            bid = cur_model.create_block(lesson_id, data)
            flash(f'Added {btype.replace("_", " ")} block.', 'success')
            log_change(_uid(), 'create', bid, change_details=f'Curriculum block {btype} on lesson {lesson_id}')
            return redirect(url_for('pastoral.curriculum_studio.lesson_edit', lesson_id=lesson_id) + f'#block-{bid}')
        if action == 'update_block':
            bid = int(request.form.get('block_id') or 0)
            block = cur_model.get_block(bid)
            if not block or block['lesson_id'] != lesson_id:
                flash('Block not found.', 'error')
                return redirect(url_for('pastoral.curriculum_studio.lesson_edit', lesson_id=lesson_id))
            btype = request.form.get('block_type') or block['block_type']
            data = _block_from_form(request, btype)
            f = request.files.get('media_file')
            if f and f.filename:
                try:
                    path = cur_model.save_curriculum_upload(
                        f, current_app,
                        kind='video' if btype == 'video' else 'image',
                    )
                    data['media_path'] = path
                except ValueError as e:
                    flash(str(e), 'error')
                    return redirect(url_for('pastoral.curriculum_studio.lesson_edit', lesson_id=lesson_id))
            if btype == 'video' and data.get('media_url'):
                data['media_url'] = cur_model.youtube_embed_url(data['media_url'])
            cur_model.update_block(bid, data)
            flash('Block updated.', 'success')
            return redirect(url_for('pastoral.curriculum_studio.lesson_edit', lesson_id=lesson_id) + f'#block-{bid}')
        if action == 'delete_block':
            bid = int(request.form.get('block_id') or 0)
            cur_model.delete_block(bid)
            flash('Block removed.', 'success')
            return redirect(url_for('pastoral.curriculum_studio.lesson_edit', lesson_id=lesson_id))
        if action == 'reorder_blocks':
            raw = request.form.get('order') or request.get_json(silent=True) or {}
            if isinstance(raw, dict):
                order = raw.get('order') or []
            else:
                try:
                    order = json.loads(raw)
                except json.JSONDecodeError:
                    order = [int(x) for x in str(raw).split(',') if x.strip().isdigit()]
            order = [int(x) for x in order]
            cur_model.reorder_blocks(lesson_id, order)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'ok': True})
            flash('Order updated.', 'success')
            return redirect(url_for('pastoral.curriculum_studio.lesson_edit', lesson_id=lesson_id))

    blocks = cur_model.list_blocks(lesson_id)
    siblings = cur_model.list_lessons(lesson['series_id'])
    return render_template(
        'pastoral/curriculum/lesson_edit.html',
        series=series,
        lesson=lesson,
        blocks=blocks,
        siblings=siblings,
        block_types=cur_model.BLOCK_TYPES,
        fill_blank_parts=cur_model.fill_blank_parts,
    )


@curriculum_bp.route('/lessons/<int:lesson_id>/preview')
@pastoral_required()
def lesson_preview(lesson_id):
    lesson = cur_model.get_lesson(lesson_id)
    if not lesson:
        flash('Lesson not found.', 'error')
        return redirect(url_for('pastoral.curriculum_studio.library'))
    series = cur_model.get_series(lesson['series_id'])
    blocks = cur_model.list_blocks(lesson_id)
    return render_template(
        'pastoral/curriculum/lesson_study.html',
        series=series,
        lesson=lesson,
        blocks=blocks,
        progress={'enrollment': {}, 'by_block': {}},
        is_preview=True,
        fill_blank_parts=cur_model.fill_blank_parts,
        youtube_embed_url=cur_model.youtube_embed_url,
    )


@curriculum_bp.route('/media/<path:filename>')
@pastoral_required()
def media_file(filename):
    return send_from_directory(cur_model.curriculum_upload_dir(current_app), filename)


@curriculum_bp.route('/<int:series_id>/reorder-lessons', methods=['POST'])
@pastoral_required()
def reorder_lessons(series_id):
    data = request.get_json(silent=True) or {}
    order = data.get('order') or []
    cur_model.reorder_lessons(series_id, [int(x) for x in order])
    return jsonify({'ok': True})


def _block_from_form(req, btype: str) -> dict:
    data = {
        'block_type': btype,
        'title': req.form.get('title'),
        'body': req.form.get('body'),
        'media_url': req.form.get('media_url'),
        'media_alt': req.form.get('media_alt'),
        'question_prompt': req.form.get('question_prompt'),
        'explanation': req.form.get('explanation'),
        'points': req.form.get('points') or 1,
        'is_required': req.form.get('is_required') == '1',
    }
    # Fill-blank answers: pipe or newline separated alternatives
    answers_raw = req.form.get('correct_answers') or ''
    if btype == 'fill_blank':
        parts = []
        for line in answers_raw.replace('|', '\n').split('\n'):
            line = line.strip()
            if line:
                parts.append(line)
        data['correct_answers'] = parts
    # Multiple choice choices
    if btype in ('multiple_choice', 'true_false'):
        labels = req.form.getlist('choice_label')
        corrects = set(req.form.getlist('choice_correct'))
        choices = []
        for i, label in enumerate(labels):
            label = (label or '').strip()
            if not label:
                continue
            choices.append({
                'label': label,
                'is_correct': str(i) in corrects or label in corrects,
            })
        if btype == 'true_false' and not choices:
            correct_tf = (req.form.get('tf_correct') or 'true').lower()
            choices = [
                {'label': 'True', 'is_correct': correct_tf == 'true'},
                {'label': 'False', 'is_correct': correct_tf == 'false'},
            ]
        data['choices'] = choices
    return data
