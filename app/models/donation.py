# app/models/donation.py
# Donation data layer — CRUD, search, reports, exports (MariaDB).

from app.models.db import get_db
from app.utils.time_utils import now_church
import pymysql
import traceback

DONOR_TYPES = ('member', 'guest', 'business')
# pymysql: %% only when execute() has bind params; single % when no params
_DATE_FMT = '%Y-%m-%d'
_DATE_FMT_BIND = '%%Y-%%m-%%d'


def _donor_key_sql():
    """Stable grouping key: linked member id or normalized free-text name."""
    return """
        CASE
            WHEN d.user_id IS NOT NULL THEN CONCAT('u:', d.user_id)
            ELSE CONCAT('n:', LOWER(TRIM(d.name)))
        END
    """


def _display_name_sql():
    return """
        COALESCE(
            NULLIF(TRIM(CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, ''))), ''),
            d.name
        )
    """


def _search_clause(search_term):
    if not search_term or not str(search_term).strip():
        return '1=1', []
    like = f"%{str(search_term).strip()}%"
    clause = """(
        d.name LIKE %s
        OR COALESCE(d.donor_email, '') LIKE %s
        OR COALESCE(d.donor_phone, '') LIKE %s
        OR COALESCE(d.notes, '') LIKE %s
        OR COALESCE(d.confirmation_number, '') LIKE %s
        OR COALESCE(u.username, '') LIKE %s
        OR COALESCE(u.email, '') LIKE %s
        OR COALESCE(u.phone, '') LIKE %s
        OR COALESCE(u.first_name, '') LIKE %s
        OR COALESCE(u.last_name, '') LIKE %s
        OR CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')) LIKE %s
    )"""
    return clause, [like] * 11


def get_donation_years():
    """Years with donation activity; always includes current church year."""
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(f"""
            SELECT DISTINCT YEAR(STR_TO_DATE(date, '{_DATE_FMT}')) AS year
            FROM donations
            WHERE date IS NOT NULL AND date != ''
              AND STR_TO_DATE(date, '{_DATE_FMT}') IS NOT NULL
            ORDER BY year DESC
        """)
        years = [int(row['year']) for row in cur.fetchall() if row.get('year')]
        cur.close()
        current = now_church().year
        if current not in years:
            years.insert(0, current)
        return years
    except Exception as e:
        print(f"get_donation_years error: {e}")
        return [now_church().year]


def get_members_for_selector():
    """Member list for add-donation autocomplete (id, username, contact fields)."""
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT id, username, first_name, last_name, email, phone, address
            FROM users
            WHERE first_name IS NOT NULL AND last_name IS NOT NULL
            ORDER BY last_name, first_name
        """)
        rows = cur.fetchall()
        cur.close()

        members = []
        for row in rows:
            full_name = f"{(row['first_name'] or '').strip()} {(row['last_name'] or '').strip()}".strip()
            email = (row['email'] or '').strip()
            phone = (row['phone'] or '').strip()
            address = (row['address'] or '').strip()
            username = (row['username'] or '').strip()

            display = full_name
            extras = [p for p in [username, email, phone] if p]
            if extras:
                display += ' — ' + ' • '.join(extras)

            search = f"{full_name} {username} {email} {phone} {address}".lower()
            members.append({
                'id': row['id'],
                'value': full_name,
                'display': display,
                'search': search,
                'email': email,
                'phone': phone,
                'username': username,
                'address': address,
            })
        return members
    except Exception as e:
        print(f"get_members_for_selector error: {e}\n{traceback.format_exc()}")
        return []


def get_member_for_export(member_id):
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT id, username, first_name, last_name, email, phone, address
            FROM users WHERE id = %s
        """, (member_id,))
        row = cur.fetchone()
        cur.close()
        return row
    except Exception as e:
        print(f"get_member_for_export error: {e}")
        return None


def get_dashboard_data():
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        current_year = now_church().year

        cur.execute(f"""
            SELECT COALESCE(SUM(amount), 0.0) AS total_this_year
            FROM donations
            WHERE YEAR(STR_TO_DATE(date, '{_DATE_FMT_BIND}')) = %s
        """, (current_year,))
        total_this_year = float(cur.fetchone()['total_this_year'])

        cur.execute(f"""
            SELECT d.id, d.name, d.amount, d.date, d.method, d.notes,
                   d.confirmation_number, d.goods_services_provided,
                   d.user_id, d.donor_email, d.donor_phone,
                   COALESCE(d.donor_type, 'guest') AS donor_type,
                   u.username
            FROM donations d
            LEFT JOIN users u ON d.user_id = u.id
            ORDER BY STR_TO_DATE(d.date, '{_DATE_FMT}') DESC
            LIMIT 10
        """)
        recent = cur.fetchall()
        cur.close()
        return total_this_year, recent
    except Exception as e:
        print(f"get_dashboard_data error: {e}\n{traceback.format_exc()}")
        return 0.0, []


def add_donation(name, amount, date, method, notes='', confirmation_number='',
                 goods_services_provided=0, user_id=None, donor_email='',
                 donor_phone='', donor_type='guest'):
    try:
        db = get_db()
        cur = db.cursor()
        if donor_type not in DONOR_TYPES:
            donor_type = 'guest'
        if user_id:
            donor_type = 'member'
        cur.execute("""
            INSERT INTO donations
            (name, amount, date, method, notes, confirmation_number,
             goods_services_provided, user_id, donor_email, donor_phone, donor_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            name, amount, date, method, notes or None, confirmation_number or None,
            goods_services_provided, user_id, donor_email or None,
            donor_phone or None, donor_type,
        ))
        donation_id = cur.lastrowid
        db.commit()
        cur.close()
        return donation_id
    except Exception as e:
        print(f"add_donation error: {e}\n{traceback.format_exc()}")
        raise


def get_donation_by_id(donation_id):
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT d.*, u.username, u.email AS member_email, u.phone AS member_phone
            FROM donations d
            LEFT JOIN users u ON d.user_id = u.id
            WHERE d.id = %s
        """, (donation_id,))
        row = cur.fetchone()
        cur.close()
        return row
    except Exception as e:
        print(f"get_donation_by_id error: {e}")
        return None


def update_donation(donation_id, name, amount, date, method, notes='',
                    confirmation_number='', goods_services_provided=0,
                    user_id=None, donor_email='', donor_phone='', donor_type='guest'):
    try:
        db = get_db()
        cur = db.cursor()
        if donor_type not in DONOR_TYPES:
            donor_type = 'guest'
        if user_id:
            donor_type = 'member'
        cur.execute("""
            UPDATE donations
            SET name = %s, amount = %s, date = %s, method = %s, notes = %s,
                confirmation_number = %s, goods_services_provided = %s,
                user_id = %s, donor_email = %s, donor_phone = %s, donor_type = %s
            WHERE id = %s
        """, (
            name, amount, date, method, notes or None,
            confirmation_number or None, goods_services_provided,
            user_id, donor_email or None, donor_phone or None, donor_type,
            donation_id,
        ))
        db.commit()
        cur.close()
    except Exception as e:
        print(f"update_donation error: {e}")
        raise


def delete_donation(donation_id):
    try:
        donation = get_donation_by_id(donation_id)
        if donation:
            db = get_db()
            cur = db.cursor()
            cur.execute("DELETE FROM donations WHERE id = %s", (donation_id,))
            db.commit()
            cur.close()
        return donation
    except Exception as e:
        print(f"delete_donation error: {e}")
        return None


def get_view_all_data(search_term='', selected_year=None, donor_type_filter=None):
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        donor_key = _donor_key_sql()
        display_name = _display_name_sql()
        search_sql, search_params = _search_clause(search_term)

        sql_summary = f"""
            SELECT
                {donor_key} AS donor_key,
                {display_name} AS name,
                d.user_id,
                MAX(COALESCE(d.donor_type, 'guest')) AS donor_type,
                MAX(COALESCE(u.username, '')) AS username,
                MAX(COALESCE(u.email, d.donor_email, '')) AS contact_email,
                MAX(COALESCE(u.phone, d.donor_phone, '')) AS contact_phone,
                COALESCE(SUM(d.amount), 0.0) AS total_donations,
                COUNT(*) AS number_of_donations
            FROM donations d
            LEFT JOIN users u ON d.user_id = u.id
            WHERE {search_sql}
        """
        params = list(search_params)

        if selected_year:
            sql_summary += f" AND YEAR(STR_TO_DATE(d.date, '{_DATE_FMT_BIND}')) = %s"
            params.append(int(selected_year))

        if donor_type_filter and donor_type_filter in DONOR_TYPES:
            sql_summary += " AND COALESCE(d.donor_type, 'guest') = %s"
            params.append(donor_type_filter)

        sql_summary += f"""
            GROUP BY donor_key, name, d.user_id
            ORDER BY MAX(STR_TO_DATE(d.date, '{_DATE_FMT_BIND}')) DESC
        """
        cur.execute(sql_summary, params)
        summary = cur.fetchall()

        detailed = {}
        for donor in summary:
            key = donor['donor_key']
            if donor.get('user_id'):
                donor_where = "d.user_id = %s"
                detail_params = [donor['user_id']]
            else:
                donor_where = "d.user_id IS NULL AND LOWER(TRIM(d.name)) = LOWER(TRIM(%s))"
                detail_params = [donor['name']]

            sql_detail = f"""
                SELECT d.id, d.date, d.amount, d.method, d.notes,
                       d.confirmation_number, d.goods_services_provided,
                       COALESCE(d.donor_type, 'guest') AS donor_type,
                       COALESCE(d.donor_email, u.email, '') AS contact_email,
                       COALESCE(d.donor_phone, u.phone, '') AS contact_phone
                FROM donations d
                LEFT JOIN users u ON d.user_id = u.id
                WHERE {donor_where}
            """

            if selected_year:
                sql_detail += f" AND YEAR(STR_TO_DATE(d.date, '{_DATE_FMT_BIND}')) = %s"
                detail_params.append(int(selected_year))
            if donor_type_filter and donor_type_filter in DONOR_TYPES:
                sql_detail += " AND COALESCE(d.donor_type, 'guest') = %s"
                detail_params.append(donor_type_filter)

            sql_detail += f" ORDER BY STR_TO_DATE(d.date, '{_DATE_FMT_BIND}') DESC"
            cur.execute(sql_detail, detail_params)
            detailed[key] = cur.fetchall()

        years = get_donation_years()
        cur.close()
        return summary, detailed, years
    except Exception as e:
        print(f"get_view_all_data error: {e}\n{traceback.format_exc()}")
        return [], {}, get_donation_years()


def get_reports_data(selected_year=None, selected_month=None, donor_type_filter=None):
    years = get_donation_years()
    empty = {
        'years': years,
        'donations': [],
        'total_amount': 0.0,
        'total_count': 0,
        'donation_types': [],
        'monthly_totals': [],
        'donor_type_breakdown': [],
        'top_donors': [],
        'member_total': 0.0,
        'guest_total': 0.0,
        'business_total': 0.0,
    }
    if not selected_year:
        return empty

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        year = int(selected_year)
        month = int(selected_month) if selected_month else None
        donor_key = _donor_key_sql()
        display_name = _display_name_sql()

        base_where = f"YEAR(STR_TO_DATE(d.date, '{_DATE_FMT_BIND}')) = %s"
        params = [year]
        if month:
            base_where += f" AND MONTH(STR_TO_DATE(d.date, '{_DATE_FMT_BIND}')) = %s"
            params.append(month)
        if donor_type_filter and donor_type_filter in DONOR_TYPES:
            base_where += " AND COALESCE(d.donor_type, 'guest') = %s"
            params.append(donor_type_filter)

        cur.execute(f"""
            SELECT d.name, d.amount, d.date, d.method, d.notes,
                   COALESCE(d.donor_type, 'guest') AS donor_type,
                   COALESCE(u.username, '') AS username,
                   COALESCE(u.email, d.donor_email, '') AS contact_email
            FROM donations d
            LEFT JOIN users u ON d.user_id = u.id
            WHERE {base_where}
            ORDER BY STR_TO_DATE(d.date, '{_DATE_FMT_BIND}') DESC
        """, params)
        donations = cur.fetchall()

        cur.execute(f"""
            SELECT COALESCE(SUM(d.amount), 0.0) AS total_amount,
                   COALESCE(COUNT(*), 0) AS total_count
            FROM donations d WHERE {base_where}
        """, params)
        totals = cur.fetchone() or {}

        cur.execute(f"""
            SELECT d.method,
                   COALESCE(SUM(d.amount), 0.0) AS total_amount,
                   COALESCE(COUNT(*), 0) AS total_count
            FROM donations d
            WHERE {base_where}
            GROUP BY d.method
            ORDER BY total_amount DESC
        """, params)
        donation_types = cur.fetchall()

        cur.execute(f"""
            SELECT COALESCE(d.donor_type, 'guest') AS donor_type,
                   COALESCE(SUM(d.amount), 0.0) AS total_amount,
                   COALESCE(COUNT(*), 0) AS total_count
            FROM donations d
            WHERE {base_where}
            GROUP BY donor_type
            ORDER BY total_amount DESC
        """, params)
        donor_type_breakdown = cur.fetchall()

        cur.execute(f"""
            SELECT {display_name} AS name,
                   {donor_key} AS donor_key,
                   COALESCE(SUM(d.amount), 0.0) AS total_amount,
                   COUNT(*) AS donation_count,
                   MAX(COALESCE(d.donor_type, 'guest')) AS donor_type
            FROM donations d
            LEFT JOIN users u ON d.user_id = u.id
            WHERE {base_where}
            GROUP BY donor_key, name
            ORDER BY total_amount DESC
            LIMIT 15
        """, params)
        top_donors = cur.fetchall()

        month_names = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December',
        ]
        monthly_totals = []
        if not month:
            for m in range(1, 13):
                cur.execute(f"""
                    SELECT COALESCE(SUM(d.amount), 0.0) AS total_amount,
                           COALESCE(COUNT(*), 0) AS total_count
                    FROM donations d
                    WHERE YEAR(STR_TO_DATE(d.date, '{_DATE_FMT_BIND}')) = %s
                      AND MONTH(STR_TO_DATE(d.date, '{_DATE_FMT_BIND}')) = %s
                """, (year, m))
                row = cur.fetchone() or {}
                monthly_totals.append({
                    'month': month_names[m - 1],
                    'total_amount': float(row.get('total_amount') or 0),
                    'total_count': int(row.get('total_count') or 0),
                })

        member_total = guest_total = business_total = 0.0
        for row in donor_type_breakdown:
            amt = float(row.get('total_amount') or 0)
            dtype = row.get('donor_type') or 'guest'
            if dtype == 'member':
                member_total = amt
            elif dtype == 'business':
                business_total = amt
            else:
                guest_total = amt

        cur.close()
        return {
            'years': years,
            'donations': donations,
            'total_amount': float(totals.get('total_amount') or 0),
            'total_count': int(totals.get('total_count') or 0),
            'donation_types': donation_types,
            'monthly_totals': monthly_totals,
            'donor_type_breakdown': donor_type_breakdown,
            'top_donors': top_donors,
            'member_total': member_total,
            'guest_total': guest_total,
            'business_total': business_total,
        }
    except Exception as e:
        print(f"get_reports_data error: {e}\n{traceback.format_exc()}")
        return empty


def get_export_years():
    return get_donation_years()


def get_donations_for_export(name, year, user_id=None):
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        if user_id:
            cur.execute(f"""
                SELECT date, amount, method, confirmation_number, notes, goods_services_provided
                FROM donations
                WHERE user_id = %s
                  AND YEAR(STR_TO_DATE(date, '{_DATE_FMT_BIND}')) = %s
                ORDER BY STR_TO_DATE(date, '{_DATE_FMT_BIND}') DESC
            """, (user_id, int(year)))
        else:
            cur.execute(f"""
                SELECT date, amount, method, confirmation_number, notes, goods_services_provided
                FROM donations
                WHERE name = %s
                  AND user_id IS NULL
                  AND YEAR(STR_TO_DATE(date, '{_DATE_FMT_BIND}')) = %s
                ORDER BY STR_TO_DATE(date, '{_DATE_FMT_BIND}') DESC
            """, (name, int(year)))
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as e:
        print(f"get_donations_for_export error: {e}")
        return []


def get_unique_donor_names(year):
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(f"""
            SELECT DISTINCT name
            FROM donations
            WHERE YEAR(STR_TO_DATE(date, '{_DATE_FMT_BIND}')) = %s
            ORDER BY name
        """, (int(year),))
        names = [row['name'] for row in cur.fetchall()]
        cur.close()
        return names
    except Exception as e:
        print(f"get_unique_donor_names error: {e}")
        return []


def get_members_with_donations(year):
    """Members with donations by user_id link OR legacy name match."""
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(f"""
            SELECT DISTINCT u.id, u.first_name, u.last_name, u.username, u.email
            FROM users u
            WHERE EXISTS (
                SELECT 1 FROM donations d
                WHERE d.user_id = u.id
                  AND YEAR(STR_TO_DATE(d.date, '{_DATE_FMT_BIND}')) = %s
            )
            OR EXISTS (
                SELECT 1 FROM donations d
                WHERE d.user_id IS NULL
                  AND d.name = CONCAT(u.first_name, ' ', u.last_name)
                  AND YEAR(STR_TO_DATE(d.date, '{_DATE_FMT_BIND}')) = %s
            )
            ORDER BY u.last_name, u.first_name
        """, (int(year), int(year)))
        members = cur.fetchall()
        cur.close()
        return members
    except Exception as e:
        print(f"get_members_with_donations error: {e}")
        return []


def get_non_member_donors_for_export(year):
    """Guest/business donors not linked to a user account."""
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(f"""
            SELECT name,
                   MAX(COALESCE(donor_email, '')) AS donor_email,
                   MAX(COALESCE(donor_phone, '')) AS donor_phone,
                   MAX(COALESCE(donor_type, 'guest')) AS donor_type,
                   COALESCE(SUM(amount), 0.0) AS total_amount
            FROM donations
            WHERE user_id IS NULL
              AND YEAR(STR_TO_DATE(date, '{_DATE_FMT_BIND}')) = %s
            GROUP BY LOWER(TRIM(name)), name
            ORDER BY name
        """, (int(year),))
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as e:
        print(f"get_non_member_donors_for_export error: {e}")
        return []