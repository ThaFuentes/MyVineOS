# Custom church modules - schema-driven pages with themes and group permissions.

import json


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_module_types (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            type_key VARCHAR(64) NOT NULL UNIQUE,
            name VARCHAR(120) NOT NULL,
            description TEXT,
            icon VARCHAR(16) DEFAULT '',
            schema_json TEXT NOT NULL,
            default_theme VARCHAR(32) NOT NULL DEFAULT 'ocean',
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_modules (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            type_key VARCHAR(64) NOT NULL,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(64) NOT NULL UNIQUE,
            description TEXT,
            theme VARCHAR(32) NOT NULL DEFAULT 'ocean',
            visibility VARCHAR(20) NOT NULL DEFAULT 'members'
                CHECK(visibility IN ('public', 'members', 'group')),
            group_id INT UNSIGNED NULL,
            manage_group_id INT UNSIGNED NULL,
            show_on_dashboard TINYINT(1) NOT NULL DEFAULT 1,
            is_enabled TINYINT(1) NOT NULL DEFAULT 1,
            created_by INT UNSIGNED NULL,
            updated_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL,
            FOREIGN KEY (manage_group_id) REFERENCES groups(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_module_records (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            module_id INT UNSIGNED NOT NULL,
            title VARCHAR(255) NOT NULL DEFAULT '',
            data_json TEXT NOT NULL,
            is_published TINYINT(1) NOT NULL DEFAULT 1,
            created_by INT UNSIGNED NULL,
            updated_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (module_id) REFERENCES custom_modules(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    for idx_sql in (
        "CREATE INDEX idx_custom_modules_enabled ON custom_modules(is_enabled)",
        "CREATE INDEX idx_custom_modules_slug ON custom_modules(slug)",
        "CREATE INDEX idx_custom_module_records_module ON custom_module_records(module_id)",
    ):
        try:
            cursor.execute(idx_sql)
        except Exception:
            pass

    _seed_module_types(cursor)


def _seed_module_types(cursor):
    types = [
        (
            'bus_routes',
            'Bus Routes',
            'Pickup stops, times, and drivers for church transportation.',
            '',
            'forest',
            {
                'list_label': 'Routes & Stops',
                'record_label': 'Stop',
                'title_field': 'stop_name',
                'fields': [
                    {'key': 'stop_name', 'label': 'Stop Name', 'type': 'text', 'required': True},
                    {'key': 'pickup_time', 'label': 'Pickup Time', 'type': 'time'},
                    {'key': 'dropoff_location', 'label': 'Drop-off Location', 'type': 'text'},
                    {'key': 'driver_name', 'label': 'Driver', 'type': 'text'},
                    {'key': 'route_notes', 'label': 'Notes', 'type': 'textarea'},
                ],
            },
        ),
        (
            'youth_group',
            'Youth Group',
            'Events, meetings, and activities for youth ministry.',
            '',
            'youth',
            {
                'list_label': 'Youth Events',
                'record_label': 'Event',
                'title_field': 'event_title',
                'fields': [
                    {'key': 'event_title', 'label': 'Event Title', 'type': 'text', 'required': True},
                    {'key': 'event_date', 'label': 'Date', 'type': 'date'},
                    {'key': 'start_time', 'label': 'Start Time', 'type': 'time'},
                    {'key': 'location', 'label': 'Location', 'type': 'text'},
                    {'key': 'leader', 'label': 'Leader', 'type': 'text'},
                    {'key': 'description', 'label': 'Description', 'type': 'textarea'},
                    {'key': 'max_attendees', 'label': 'Max Attendees', 'type': 'number'},
                ],
            },
        ),
        (
            'resource_list',
            'Equipment & Rooms',
            'Optional - track what the church owns or lends out (sound board, van keys, Room 3). Not a chat or reservation system; just a shared list managers update.',
            '',
            'slate',
            {
                'list_label': 'Resources',
                'record_label': 'Resource',
                'title_field': 'item_name',
                'fields': [
                    {'key': 'item_name', 'label': 'Item Name', 'type': 'text', 'required': True},
                    {'key': 'category', 'label': 'Category', 'type': 'select',
                     'options': ['Equipment', 'Room', 'Vehicle', 'Supplies', 'Other']},
                    {'key': 'quantity', 'label': 'Quantity', 'type': 'number'},
                    {'key': 'location', 'label': 'Location', 'type': 'text'},
                    {'key': 'contact_person', 'label': 'Contact Person', 'type': 'text'},
                    {'key': 'notes', 'label': 'Notes', 'type': 'textarea'},
                ],
            },
        ),
        (
            'weekly_schedule',
            'Ministry Calendar',
            'Optional - post when ministries meet (e.g. "Wednesday Youth 7pm, Room B"). One-way bulletin, not a signup or forum.',
            '',
            'royal',
            {
                'list_label': 'Schedule Items',
                'record_label': 'Schedule Item',
                'title_field': 'title',
                'fields': [
                    {'key': 'title', 'label': 'Title', 'type': 'text', 'required': True},
                    {'key': 'day_of_week', 'label': 'Day', 'type': 'select',
                     'options': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']},
                    {'key': 'start_time', 'label': 'Start Time', 'type': 'time'},
                    {'key': 'end_time', 'label': 'End Time', 'type': 'time'},
                    {'key': 'location', 'label': 'Location', 'type': 'text'},
                    {'key': 'leader', 'label': 'Leader / Contact', 'type': 'text'},
                    {'key': 'details', 'label': 'Details', 'type': 'textarea'},
                ],
            },
        ),
    ]

    for type_key, name, desc, icon, theme, schema in types:
        cursor.execute("""
            INSERT IGNORE INTO custom_module_types
                (type_key, name, description, icon, schema_json, default_theme)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (type_key, name, desc, icon, json.dumps(schema), theme))

    # Refresh labels/help text on existing installs
    for type_key, name, desc in (
        ('resource_list', 'Equipment & Rooms',
         'Optional - track church equipment and rooms (sound board, van, Room 3). Managers update the list; members read it.'),
        ('weekly_schedule', 'Ministry Calendar',
         'Optional - when ministries meet (e.g. Wednesday Youth 7pm). Bulletin-style, not chat or signups.'),
        ('bus_routes', 'Bus Routes',
         'Pickup stops, times, and drivers for church transportation.'),
        ('youth_group', 'Youth Group',
         'Youth events and meetings - dates, locations, leaders.'),
    ):
        cursor.execute("""
            UPDATE custom_module_types SET name = %s, description = %s WHERE type_key = %s
        """, (name, desc, type_key))

    print("Custom module types seeded: bus_routes, youth_group, ministry calendar, equipment & rooms.")