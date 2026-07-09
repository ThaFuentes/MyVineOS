import pymysql
from datetime import datetime
from app.models.db import get_db


def log_service_plays(setlist_id: int, service_date: str, song_ids: list, user_id: int):
    if not song_ids or not service_date:
        return 0
    db = get_db()
    cur = db.cursor()
    count = 0
    for sid in song_ids:
        cur.execute("""
            INSERT INTO worship_song_plays (song_id, setlist_id, service_date, recorded_by)
            VALUES (%s, %s, %s, %s)
        """, (sid, setlist_id, service_date, user_id))
        count += 1
    cur.execute(
        "UPDATE worship_setlists SET service_confirmed_at = NOW() WHERE id = %s",
        (setlist_id,),
    )
    db.commit()
    return count


def get_play_history(limit=100):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT p.*, s.title, s.artist
        FROM worship_song_plays p
        JOIN worship_songs s ON s.id = p.song_id
        ORDER BY p.service_date DESC, p.played_at DESC
        LIMIT %s
    """, (limit,))
    return cur.fetchall()


def get_song_play_counts():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT s.id, s.title, s.artist, COUNT(p.id) AS play_count,
               MAX(p.service_date) AS last_played
        FROM worship_songs s
        LEFT JOIN worship_song_plays p ON p.song_id = s.id
        GROUP BY s.id
        ORDER BY play_count DESC, s.title
    """)
    return cur.fetchall()


def user_accepts_worship_email(user_id: int) -> bool:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT accepts_emails, accepts_worship_emails FROM users WHERE id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        return False
    return bool(row.get('accepts_emails', 1)) and bool(row.get('accepts_worship_emails', 1))