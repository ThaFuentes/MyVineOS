# app/routes/sermons/utils.py
# Full path: WebChurchMan/app/routes/sermons/utils.py
# File name: utils.py
# Brief, detailed purpose: Constants + small helper functions for the sermons blueprint.
# • Allowed file extensions
# • Upload folder path resolution
# • File extension validation
# • Staff role constant (used in decorators & permission checks)
# 100% identical behavior to original — only extracted and centralized.

import os


ALLOWED_EXTENSIONS = {'pdf', 'mp3', 'mp4', 'jpg', 'jpeg', 'png', 'docx', 'txt'}


STAFF_ROLES = ['Staff', 'Admin', 'Owner']


# Persistent upload folder for sermons (absolute path)
UPLOAD_FOLDER = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'uploads', 'sermons')
)


def allowed_file(filename: str) -> bool:
    """
    Check if uploaded file has an allowed extension.
    Exact original logic preserved.
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS