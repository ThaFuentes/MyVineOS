# app/routes/sermons/forms.py
# Full path: WebChurchMan/app/routes/sermons/forms.py
# File name: forms.py
# Brief, detailed purpose: All form validation + censored word checks + repopulation logic for the sermons blueprint.
# Updated to accept the new "Full Sermon Manuscript" (sermon_text) field.

from app.utils.helpers import contains_censored_word


def validate_sermon_upload_or_edit(form_data, files, is_edit=False, existing_notes_text=''):
    """
    Validate sermon upload/edit form data (title, details, visibility, files).
    Handles censorship on title + details + extractable notes text.
    Returns tuple: (is_valid: bool, errors: list of str, cleaned_data: dict)
    """
    errors = []
    cleaned = {
        'title': '',
        'details': '',
        'external_link': '',
        'visibility': 'private',
        'notes_text': '',      # extracted from notes file for censorship
        'sermon_text': ''      # NEW: Full Sermon Manuscript
    }

    title = form_data.get('title', '').strip()
    details = form_data.get('details', '').strip()
    external_link = form_data.get('external_link', '').strip()
    visibility = form_data.get('visibility', 'private' if not is_edit else None)
    sermon_text = form_data.get('sermon_text', '').strip()   # NEW

    cleaned['title'] = title
    cleaned['details'] = details
    cleaned['external_link'] = external_link
    cleaned['sermon_text'] = sermon_text
    if visibility in ['public', 'private', 'personal']:
        cleaned['visibility'] = visibility

    if not title:
        errors.append('Title is required.')

    # Combine text for censorship check
    combined_text = f"{title} {details} {sermon_text}"

    # Handle notes file if uploaded
    notes_file = files.get('sermon_notes')
    if notes_file and notes_file.filename:
        ext = notes_file.filename.rsplit('.', 1)[-1].lower() if '.' in notes_file.filename else ''
        if ext in {'txt', 'docx', 'pdf'}:
            cleaned['notes_text'] = '(notes file provided - content checked in view)'
        else:
            errors.append('Notes file must be .txt, .docx, or .pdf')

    # For edit: if no new notes file, use existing extracted text
    if is_edit and not notes_file:
        combined_text += f" {existing_notes_text}"

    if contains_censored_word(combined_text):
        errors.append('Sermon contains a prohibited word or phrase.')

    # UPDATED REQUIREMENT: sermon_text now counts as valid content
    if not is_edit:
        has_notes = bool(notes_file and notes_file.filename)
        has_sermon_file = bool(files.get('sermon_file') and files.get('sermon_file').filename)
        has_external = bool(external_link.strip())
        has_text = bool(sermon_text)

        if not (has_notes or has_sermon_file or has_external or has_text):
            errors.append('You must provide either the Full Sermon Manuscript, notes, a media file, or an external link.')

    is_valid = len(errors) == 0
    return is_valid, errors, cleaned


def validate_sermon_comment(form_data):
    """
    Validate comment submission on sermon.
    Returns tuple: (is_valid: bool, errors: list of str, cleaned_data: dict)
    """
    errors = []
    cleaned = {'comment': ''}

    comment = form_data.get('comment', '').strip()
    cleaned['comment'] = comment

    if not comment:
        errors.append('Comment cannot be empty.')
    elif contains_censored_word(comment):
        errors.append('Comment contains a prohibited word or phrase.')

    is_valid = len(errors) == 0
    return is_valid, errors, cleaned