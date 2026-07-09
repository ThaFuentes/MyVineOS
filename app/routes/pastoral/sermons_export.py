# app/routes/pastoral/sermons_export.py
# Full path: WebChurchMan/app/routes/pastoral/sermons_export.py
# File name: sermons_export.py
# Brief, detailed purpose:
#   Blueprint for sermon export functionality (single & bulk DOCX).
#   - Export list view with selectable sermons
#   - Single sermon DOCX download
#   - Bulk export -> ZIP of multiple DOCX files
#   - Clean formatting with python-docx
#   - Respects visibility enforcement
#   - Audit-logged exports
#   - Blueprint variable named export_bp to match existing import in pastoral/__init__.py

from flask import Blueprint, render_template, send_file, session, request, abort, flash, redirect, url_for
from io import BytesIO
import zipfile
from datetime import datetime

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from . import pastoral_required
from app.models.pastoral.sermons import get_visible_sermons, get_sermon_by_id, get_sermon_sections
from app.models.log import log_change

export_bp = Blueprint('sermons_export', __name__, url_prefix='/sermons/export')


# ----------------------------------------------------------------------
# Helper: Generate formatted DOCX for a single sermon
# ----------------------------------------------------------------------
def _generate_sermon_docx(sermon: dict, sections: list) -> Document:
    doc = Document()

    # Title (use heading - built-in 'Title' style is character-only in some templates)
    title_para = doc.add_heading(sermon['title'], level=0)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if title_para.runs:
        title_para.runs[0].font.size = Pt(24)
        title_para.runs[0].font.color.rgb = RGBColor(0, 255, 255)

    # Primary passage
    if sermon.get('primary_passage'):
        passage_para = doc.add_paragraph(sermon['primary_passage'])
        passage_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        passage_para.runs[0].italic = True

    # Meta info
    meta_parts = []
    if sermon.get('service_date'):
        meta_parts.append(f"Date: {sermon['service_date']}")
    meta_parts.append(f"Prepared by: {sermon.get('creator_name', 'Unknown')}")
    if meta_parts:
        meta_para = doc.add_paragraph(' | '.join(meta_parts))
        if meta_para.runs:
            meta_para.runs[0].italic = True

    # Sections
    for sec in sections:
        if sec.get('title'):
            heading = doc.add_heading(sec['title'], level=2)
            heading.runs[0].font.color.rgb = RGBColor(0, 255, 255)

        if sec.get('scripture_reference'):
            ref_para = doc.add_paragraph(sec['scripture_reference'])
            if ref_para.runs:
                ref_para.runs[0].italic = True

        if sec.get('content'):
            for line in sec['content'].split('\n'):
                if line.strip():
                    doc.add_paragraph(line.strip())

        if sec.get('notes'):
            notes_para = doc.add_paragraph('Preacher Notes: ')
            notes_para.runs[0].italic = True
            notes_para.add_run(sec['notes'])

    # Additional notes
    if sermon.get('notes'):
        doc.add_page_break()
        doc.add_heading('Additional Notes', level=1)
        doc.add_paragraph(sermon['notes'])

    return doc


# ----------------------------------------------------------------------
# Export Selection List
# ----------------------------------------------------------------------
@export_bp.route('/')
@pastoral_required()
def list():
    user_id = session['user_id']
    sermons = get_visible_sermons(user_id, limit=200)
    return render_template(
        'pastoral/sermons_export.html',
        sermons=sermons,
        title="Export Sermons to DOCX"
    )


# ----------------------------------------------------------------------
# Single Sermon Export
# ----------------------------------------------------------------------
@export_bp.route('/single/<int:sermon_id>')
@pastoral_required()
def single(sermon_id: int):
    user_id = session['user_id']
    sermon = get_sermon_by_id(sermon_id, user_id)
    if not sermon:
        abort(404)

    sections = get_sermon_sections(sermon_id)
    doc = _generate_sermon_docx(sermon, sections)

    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)

    safe_title = sermon['title'].replace(' ', '_').replace('/', '-')
    filename = f"{safe_title}_{sermon.get('service_date', 'NoDate')}.docx"

    log_change(user_id, 'export_single', sermon_id, sermon['title'], 'Exported single sermon to DOCX')

    return send_file(
        bio,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


# ----------------------------------------------------------------------
# Bulk Export (ZIP)
# ----------------------------------------------------------------------
@export_bp.route('/bulk', methods=['POST'])
@pastoral_required()
def bulk():
    user_id = session['user_id']
    sermon_ids = request.form.getlist('sermon_ids')

    if not sermon_ids:
        flash('No sermons selected.', 'error')
        return redirect(url_for('pastoral.sermons_export.list'))

    valid_sermons = []
    for sid_str in sermon_ids:
        sid = int(sid_str)
        sermon = get_sermon_by_id(sid, user_id)
        if sermon:
            valid_sermons.append((sid, sermon))

    if not valid_sermons:
        flash('No accessible sermons selected.', 'error')
        return redirect(url_for('pastoral.sermons_export.list'))

    bio = BytesIO()
    with zipfile.ZipFile(bio, 'w', zipfile.ZIP_DEFLATED) as zf:
        for sermon_id, sermon in valid_sermons:
            sections = get_sermon_sections(sermon_id)
            doc = _generate_sermon_docx(sermon, sections)

            doc_bio = BytesIO()
            doc.save(doc_bio)
            doc_bio.seek(0)

            safe_title = sermon['title'].replace(' ', '_').replace('/', '-')
            filename = f"{safe_title}_{sermon.get('service_date', 'NoDate')}.docx"
            zf.writestr(filename, doc_bio.read())

    bio.seek(0)

    log_change(user_id, 'export_bulk', None, None, f'Bulk exported {len(valid_sermons)} sermons')
    flash(f'{len(valid_sermons)} sermons exported.', 'success')

    return send_file(
        bio,
        as_attachment=True,
        download_name=f"MyVineChurch_Sermons_{datetime.now().strftime('%Y%m%d')}.zip",
        mimetype='application/zip'
    )