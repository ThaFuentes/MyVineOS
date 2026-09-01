import os
import uuid

ALLOWED_CHORD_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'png', 'jpg', 'jpeg'}
DEFAULT_ROLES = [
    'Worship Leader', 'Vocals', 'Guitar', 'Bass', 'Keys', 'Drums', 'Sound', 'Slides',
]


def chords_upload_dir(app):
    path = os.path.join(app.config['UPLOAD_FOLDER'], 'worship', 'chords')
    os.makedirs(path, exist_ok=True)
    return path


def allowed_chord_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_CHORD_EXTENSIONS


def save_chord_upload(file_storage, app):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_chord_file(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    dest = os.path.join(chords_upload_dir(app), safe_name)
    file_storage.save(dest)
    return safe_name