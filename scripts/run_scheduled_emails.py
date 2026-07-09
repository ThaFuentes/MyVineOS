#!/usr/bin/env python3
"""Run scheduled email jobs (bill reminders, etc.).

Use with cron instead of relying on dashboard-triggered runs:
  0 8 * * * cd /path/to/myvineos && .venv/bin/python scripts/run_scheduled_emails.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app
from app.utils.scheduled_emails import run_bill_reminder_scheduler, _mark_scheduler_run


def main():
    app = create_app()
    with app.app_context():
        sent = run_bill_reminder_scheduler()
        _mark_scheduler_run()
        print(f"Scheduled emails complete. Bill reminders sent: {sent}")


if __name__ == '__main__':
    main()