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
        try:
            from app.donations_import.mailbox import run_scheduled_mailbox_scans
            scan = run_scheduled_mailbox_scans()
            if scan and not scan.get('skipped'):
                print(
                    f"Donation mailboxes: scanned {scan.get('scanned', 0)}, "
                    f"fetched {scan.get('fetched', 0)}, new {scan.get('new', 0)}"
                )
            elif scan and scan.get('skipped'):
                print("Donation mailbox scan skipped (auto-check off or import disabled).")
        except Exception as e:
            print(f"Donation mailbox scan error: {e}")
        sent = run_bill_reminder_scheduler()
        _mark_scheduler_run()
        print(f"Scheduled emails complete. Bill reminders sent: {sent}")


if __name__ == '__main__':
    main()