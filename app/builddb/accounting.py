# Church accounting: chart of accounts, ledger, vendors, expenses, budgets, payroll.


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acct_accounts (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            code VARCHAR(32) NOT NULL,
            name VARCHAR(255) NOT NULL,
            account_type VARCHAR(32) NOT NULL,
            parent_id INT UNSIGNED NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            is_system TINYINT(1) NOT NULL DEFAULT 0,
            description VARCHAR(500) NULL,
            sort_order INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_acct_code (code),
            INDEX idx_acct_type (account_type, is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acct_vendors (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(255) NOT NULL,
            contact_name VARCHAR(160) NULL,
            email VARCHAR(255) NULL,
            phone VARCHAR(40) NULL,
            address TEXT NULL,
            website VARCHAR(500) NULL,
            tax_id VARCHAR(64) NULL,
            default_expense_account_id INT UNSIGNED NULL,
            payment_terms VARCHAR(80) NULL,
            notes TEXT NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_acct_vendor_name (name),
            INDEX idx_acct_vendor_active (is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acct_journal_entries (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            entry_date DATE NOT NULL,
            reference VARCHAR(80) NULL,
            memo VARCHAR(500) NULL,
            source VARCHAR(40) NOT NULL DEFAULT 'manual',
            source_id INT UNSIGNED NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'posted',
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_acct_je_date (entry_date),
            INDEX idx_acct_je_source (source, source_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acct_journal_lines (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            entry_id INT UNSIGNED NOT NULL,
            account_id INT UNSIGNED NOT NULL,
            description VARCHAR(500) NULL,
            debit DECIMAL(14,2) NOT NULL DEFAULT 0,
            credit DECIMAL(14,2) NOT NULL DEFAULT 0,
            INDEX idx_acct_jl_entry (entry_id),
            INDEX idx_acct_jl_account (account_id),
            CONSTRAINT fk_acct_jl_entry
                FOREIGN KEY (entry_id) REFERENCES acct_journal_entries(id) ON DELETE CASCADE,
            CONSTRAINT fk_acct_jl_account
                FOREIGN KEY (account_id) REFERENCES acct_accounts(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acct_expenses (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            expense_date DATE NOT NULL,
            vendor_id INT UNSIGNED NULL,
            vendor_name VARCHAR(255) NULL,
            amount DECIMAL(14,2) NOT NULL,
            expense_account_id INT UNSIGNED NOT NULL,
            payment_account_id INT UNSIGNED NULL,
            payment_method VARCHAR(40) NULL,
            reference VARCHAR(80) NULL,
            description VARCHAR(500) NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'posted',
            journal_entry_id INT UNSIGNED NULL,
            bill_id INT UNSIGNED NULL,
            bill_payment_id INT UNSIGNED NULL,
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_acct_exp_date (expense_date),
            INDEX idx_acct_exp_vendor (vendor_id),
            INDEX idx_acct_exp_account (expense_account_id),
            INDEX idx_acct_exp_bill (bill_id),
            INDEX idx_acct_exp_bill_pay (bill_payment_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'acct_expenses'
    """)
    exp_cols = {row[0] for row in cursor.fetchall()}
    for col_name, col_def in {
        'bill_id': "INT UNSIGNED NULL",
        'bill_payment_id': "INT UNSIGNED NULL",
    }.items():
        if col_name not in exp_cols:
            print(f"Migration: Adding acct_expenses.{col_name}")
            cursor.execute(f"ALTER TABLE acct_expenses ADD COLUMN {col_name} {col_def}")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acct_budgets (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(160) NOT NULL,
            fiscal_year INT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'active',
            notes TEXT NULL,
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_acct_budget_year_name (fiscal_year, name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acct_budget_lines (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            budget_id INT UNSIGNED NOT NULL,
            account_id INT UNSIGNED NOT NULL,
            amount DECIMAL(14,2) NOT NULL DEFAULT 0,
            notes VARCHAR(255) NULL,
            UNIQUE KEY uq_acct_budget_acct (budget_id, account_id),
            CONSTRAINT fk_acct_bl_budget
                FOREIGN KEY (budget_id) REFERENCES acct_budgets(id) ON DELETE CASCADE,
            CONSTRAINT fk_acct_bl_account
                FOREIGN KEY (account_id) REFERENCES acct_accounts(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acct_employees (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id INT UNSIGNED NULL,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            email VARCHAR(255) NULL,
            phone VARCHAR(40) NULL,
            title VARCHAR(120) NULL,
            pay_type VARCHAR(24) NOT NULL DEFAULT 'salary',
            pay_rate DECIMAL(14,2) NOT NULL DEFAULT 0,
            pay_frequency VARCHAR(24) NOT NULL DEFAULT 'biweekly',
            expense_account_id INT UNSIGNED NULL,
            active TINYINT(1) NOT NULL DEFAULT 1,
            hire_date DATE NULL,
            notes TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_acct_emp_active (active),
            INDEX idx_acct_emp_name (last_name, first_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acct_pay_runs (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            pay_date DATE NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'draft',
            notes TEXT NULL,
            journal_entry_id INT UNSIGNED NULL,
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_at TIMESTAMP NULL,
            INDEX idx_acct_pr_dates (pay_date, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acct_pay_items (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            pay_run_id INT UNSIGNED NOT NULL,
            employee_id INT UNSIGNED NOT NULL,
            description VARCHAR(255) NULL,
            gross_pay DECIMAL(14,2) NOT NULL DEFAULT 0,
            deductions DECIMAL(14,2) NOT NULL DEFAULT 0,
            net_pay DECIMAL(14,2) NOT NULL DEFAULT 0,
            hours DECIMAL(8,2) NULL,
            notes VARCHAR(500) NULL,
            INDEX idx_acct_pi_run (pay_run_id),
            CONSTRAINT fk_acct_pi_run
                FOREIGN KEY (pay_run_id) REFERENCES acct_pay_runs(id) ON DELETE CASCADE,
            CONSTRAINT fk_acct_pi_emp
                FOREIGN KEY (employee_id) REFERENCES acct_employees(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # Seed chart of accounts if empty
    cursor.execute("SELECT COUNT(*) FROM acct_accounts")
    n = cursor.fetchone()[0]
    if not n:
        seeds = [
            # Assets
            ('1000', 'Cash - Operating', 'asset', 10),
            ('1010', 'Cash - Savings', 'asset', 20),
            ('1100', 'Accounts Receivable', 'asset', 30),
            ('1200', 'Prepaid Expenses', 'asset', 40),
            # Liabilities
            ('2000', 'Accounts Payable', 'liability', 100),
            ('2100', 'Payroll Liabilities', 'liability', 110),
            ('2200', 'Deferred Revenue', 'liability', 120),
            # Equity / Net assets
            ('3000', 'Unrestricted Net Assets', 'equity', 200),
            ('3100', 'Temporarily Restricted Net Assets', 'equity', 210),
            # Income
            ('4000', 'Tithes & Offerings', 'income', 300),
            ('4100', 'Special Offerings', 'income', 310),
            ('4200', 'Event Income', 'income', 320),
            ('4300', 'Other Income', 'income', 330),
            # Expenses
            ('5000', 'Salaries & Wages', 'expense', 400),
            ('5100', 'Payroll Taxes & Benefits', 'expense', 410),
            ('5200', 'Facilities & Utilities', 'expense', 420),
            ('5300', 'Ministry Programs', 'expense', 430),
            ('5400', 'Missions & Outreach', 'expense', 440),
            ('5500', 'Office & Admin', 'expense', 450),
            ('5600', 'Insurance', 'expense', 460),
            ('5700', 'Technology', 'expense', 470),
            ('5800', 'Other Expenses', 'expense', 480),
        ]
        for code, name, atype, sort in seeds:
            cursor.execute(
                """
                INSERT INTO acct_accounts (code, name, account_type, is_system, sort_order)
                VALUES (%s,%s,%s,1,%s)
                """,
                (code, name, atype, sort),
            )
