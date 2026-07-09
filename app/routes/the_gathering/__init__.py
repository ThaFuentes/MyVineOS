# MYVINECHURCH.ONLINE/app/routes/the_gathering/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Main The Gathering Place Manager blueprint initializer (parent blueprint).
# • Creates the_gathering_bp with url_prefix='/the_gathering' (exact same pattern as public parent).
# • Registers ONLY the dashboard sub-blueprint (exactly like public sub-blueprints).
# • Root '/' route redirects to the nested dashboard endpoint using the full correct name.
# • Template and static paths match your templates/the_gathering/ folder structure.
# • 100% rebuilt to match the exact public modular pattern you already have working.
# • All original behavior preserved — only registration and route attachment fixed.

from flask import Blueprint, redirect, url_for, request
import re

# ──────────────────────────────────────────────────────────────
# Main The Gathering Place Manager Blueprint (Parent)
# ──────────────────────────────────────────────────────────────
the_gathering_bp = Blueprint(
    'the_gathering',
    __name__,
    url_prefix='/the_gathering',
    template_folder='../../../templates/the_gathering',
    static_folder='../../../static'
)

# ──────────────────────────────────────────────────────────────
# Register the Dashboard Sub-Blueprint
# ──────────────────────────────────────────────────────────────
from .dashboard import dashboard_bp
the_gathering_bp.register_blueprint(dashboard_bp)

# Enable Gathering Place Manager for admin editing of posts & comments.
# Only subs that import cleanly without errors are enabled (announcements, dreams).
# Others (prayers, prophecies, sermons, events) have incomplete/mismatched forms/queries in the partial rebuild and are left disabled to keep app starting.
from .announcements import announcements_bp
the_gathering_bp.register_blueprint(announcements_bp)
from .dreams import dreams_bp
the_gathering_bp.register_blueprint(dreams_bp)
# Now enabling the remaining sections (prayers moderation, sermons content, events, prophecies) as they are completed to match the working dreams/announcements pattern.
from .prayers import prayers_bp
the_gathering_bp.register_blueprint(prayers_bp)
from .prophecies import prophecies_bp
the_gathering_bp.register_blueprint(prophecies_bp)
from .sermons import sermons_bp
the_gathering_bp.register_blueprint(sermons_bp)
from .events import events_bp
the_gathering_bp.register_blueprint(events_bp)

_SECTION_NAV = {
    'events': ('📅 Events Manager', 'the_gathering.events.events_dashboard'),
    'prayers': ('🙏 Prayers Manager', 'the_gathering.prayers.prayers_dashboard'),
    'sermons': ('📖 Sermons Manager', 'the_gathering.sermons.sermons_dashboard'),
    'dreams': ('🌟 Dreams Manager', 'the_gathering.dreams.dreams_dashboard'),
    'prophecies': ('🔮 Prophecies Manager', 'the_gathering.prophecies.prophecies_dashboard'),
    'announcements': ('📢 Announcements Manager', 'the_gathering.announcements.announcements_dashboard'),
}

_PAGE_LABELS = {
    'new': 'Create New',
    'moderation': 'Moderation Queue',
    'potluck': 'Potluck',
    'comments.html': 'Comments',
    'view': 'View',
    'edit': 'Edit',
}


@the_gathering_bp.context_processor
def inject_manager_breadcrumb():
    """Breadcrumb context for all Gathering Place Manager templates."""
    path = (request.path or '').rstrip('/')
    section_name = None
    section_url = None
    page_label = None

    match = re.match(r'^/the_gathering(?:/([^/]+)(?:/(.+))?)?$', path)
    if not match:
        return {
            'manager_section_name': section_name,
            'manager_section_url': section_url,
            'manager_page_label': page_label,
        }

    section_key = match.group(1) or ''
    remainder = (match.group(2) or '').strip('/')

    if section_key == 'dashboard':
        if remainder == 'moderation':
            page_label = _PAGE_LABELS['moderation']
    elif section_key in _SECTION_NAV:
        label, endpoint = _SECTION_NAV[section_key]
        section_name = label
        section_url = url_for(endpoint)
        if remainder:
            if remainder == 'new':
                page_label = _PAGE_LABELS['new']
            elif remainder.endswith('/potluck'):
                page_label = _PAGE_LABELS['potluck']
            elif remainder.endswith('/comments.html'):
                page_label = _PAGE_LABELS['comments.html']
            elif re.search(r'/view$', remainder):
                page_label = _PAGE_LABELS['view']
            elif re.search(r'/edit$', remainder):
                page_label = _PAGE_LABELS['edit']
            elif remainder and not remainder.isdigit():
                tail = remainder.rsplit('/', 1)[-1]
                page_label = _PAGE_LABELS.get(tail, tail.replace('_', ' ').title())

    return {
        'manager_section_name': section_name,
        'manager_section_url': section_url,
        'manager_page_label': page_label,
    }


# ──────────────────────────────────────────────────────────────
# Root Route (keeps original user experience)
# ──────────────────────────────────────────────────────────────
@the_gathering_bp.route('/')
def index():
    """Root of /the_gathering redirects to the main Gathering Place Manager dashboard.
    Uses the full nested endpoint name so Flask can always find it (matches public pattern)."""
    return redirect(url_for('the_gathering.dashboard.dashboard'))


# print("✅ the_gathering (Gathering Place Manager) fully enabled: announcements, dreams, prayers, prophecies, sermons, events subs for admin edit/moderation of posts & comments.")