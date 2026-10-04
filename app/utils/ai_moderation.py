# Hook for a future background AI check on new posts and comments.
#
# Nothing here calls an outside service yet. When it is wired up:
#   - run after the row is committed, in a daemon thread with its own DB
#     connection (Passenger has no worker queue), or drain a jobs table on cron
#   - classify(text) with app/utils/ai_client.py using a strict JSON prompt
#   - on a hit, call app.models.flags.raise_flag(source='ai', ...) so it lands
#     in /church/moderation/flags for a person to decide
#   - never hide or block anything on its own; crisis gets severity 5
# The settings column ai_content_monitor_enabled (church_community builddb)
# is the switch to honor.

from __future__ import annotations

AI_CHECK_ENABLED = False  # flip only when classify() is implemented and the owner opts in


def classify(text: str, kind: str = 'post') -> dict | None:
    """Return {'category', 'severity', 'score', 'reason'} or None. Not implemented."""
    return None


def queue_check(kind: str, content_id: int | None, text: str, author_id: int | None = None,
                table: str | None = None) -> None:
    """Called after a post/comment is saved. No-op until AI moderation is enabled."""
    if not AI_CHECK_ENABLED or not content_id or not (text or '').strip():
        return None
    # Future: start a background job here. Must never raise into the request.
    return None
