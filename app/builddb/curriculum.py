# Curriculum / discipleship study courses, lessons, interactive blocks.


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_series (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            title VARCHAR(255) NOT NULL,
            subtitle VARCHAR(500) NULL,
            description TEXT NULL,
            cover_image VARCHAR(500) NULL,
            audience VARCHAR(40) NOT NULL DEFAULT 'everyone',
            status VARCHAR(24) NOT NULL DEFAULT 'draft',
            visibility VARCHAR(24) NOT NULL DEFAULT 'pastoral',
            tags VARCHAR(500) NULL,
            estimated_minutes INT UNSIGNED NULL,
            sort_order INT NOT NULL DEFAULT 0,
            created_by INT UNSIGNED NULL,
            published_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_curriculum_series_status (status),
            INDEX idx_curriculum_series_audience (audience),
            INDEX idx_curriculum_series_sort (sort_order)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_lessons (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            series_id INT UNSIGNED NOT NULL,
            title VARCHAR(255) NOT NULL,
            summary TEXT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'draft',
            estimated_minutes INT UNSIGNED NULL,
            sort_order INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_curriculum_lessons_series (series_id, sort_order),
            CONSTRAINT fk_curriculum_lessons_series
                FOREIGN KEY (series_id) REFERENCES curriculum_series(id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # Content blocks: text material, image, video, multiple-choice, true/false, fill-blank
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_blocks (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            lesson_id INT UNSIGNED NOT NULL,
            block_type VARCHAR(32) NOT NULL DEFAULT 'text',
            title VARCHAR(255) NULL,
            body MEDIUMTEXT NULL,
            media_url VARCHAR(1000) NULL,
            media_path VARCHAR(500) NULL,
            media_alt VARCHAR(255) NULL,
            question_prompt TEXT NULL,
            correct_answers_json TEXT NULL,
            explanation TEXT NULL,
            points INT NOT NULL DEFAULT 1,
            is_required TINYINT(1) NOT NULL DEFAULT 1,
            sort_order INT NOT NULL DEFAULT 0,
            settings_json TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_curriculum_blocks_lesson (lesson_id, sort_order),
            INDEX idx_curriculum_blocks_type (block_type),
            CONSTRAINT fk_curriculum_blocks_lesson
                FOREIGN KEY (lesson_id) REFERENCES curriculum_lessons(id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_choices (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            block_id INT UNSIGNED NOT NULL,
            label VARCHAR(500) NOT NULL,
            is_correct TINYINT(1) NOT NULL DEFAULT 0,
            sort_order INT NOT NULL DEFAULT 0,
            INDEX idx_curriculum_choices_block (block_id, sort_order),
            CONSTRAINT fk_curriculum_choices_block
                FOREIGN KEY (block_id) REFERENCES curriculum_blocks(id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # Learner progress (member study mode)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_progress (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id INT UNSIGNED NOT NULL,
            series_id INT UNSIGNED NOT NULL,
            lesson_id INT UNSIGNED NULL,
            block_id INT UNSIGNED NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'started',
            answer_json TEXT NULL,
            is_correct TINYINT(1) NULL,
            score INT NULL,
            completed_at TIMESTAMP NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_curriculum_progress_user_block (user_id, block_id),
            INDEX idx_curriculum_progress_user_series (user_id, series_id),
            INDEX idx_curriculum_progress_lesson (user_id, lesson_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_enrollments (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id INT UNSIGNED NOT NULL,
            series_id INT UNSIGNED NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'active',
            last_lesson_id INT UNSIGNED NULL,
            progress_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            UNIQUE KEY uq_curriculum_enroll (user_id, series_id),
            INDEX idx_curriculum_enroll_series (series_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
