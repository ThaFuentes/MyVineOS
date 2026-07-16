# Realistic mock payment notification emails for offline testing of the importer.

FIXTURES = [
    {
        'uid': 'fixture-stripe-card-001',
        'processor': 'stripe',
        'subject': 'You received a payment of $125.00 USD',
        'from_address': 'receipts@stripe.com',
        'body_text': """
Stripe

You received a payment

Payment from Jane Q. Donor
Amount $125.00 USD
Date Mar 12, 2026
Payment ID pi_3OxStripeDemoABC123
Payment method Visa •••• 4242
Receipt number 2403-9124

Customer email jane.donor@example.com

Thanks,
Stripe
""".strip(),
    },
    {
        'uid': 'fixture-stripe-ach-002',
        'processor': 'stripe',
        'subject': 'Payment receipt from First Community Church',
        'from_address': 'receipts@stripe.com',
        'body_text': """
Stripe ACH payment succeeded

Customer: Robert Bankman
Email: robert.bankman@example.org
Amount: $250.00
Date: 2026-03-10
Payment method: US bank account (ACH)
Payment ID: py_1AchStripeDemoXYZ789
Fund: Building Fund

ACH Trace reference available in Dashboard.
""".strip(),
    },
    {
        'uid': 'fixture-paypal-003',
        'processor': 'paypal',
        'subject': "You've received $75.00 USD from Maria Lopez",
        'from_address': 'service@paypal.com',
        'body_text': """
Hello First Community Church,

You received a payment from Maria Lopez (maria.lopez@example.com).

Amount: $75.00 USD
Transaction ID: 8A712345678901234
Date: Mar 11, 2026
Note: Tithe

This is not a receipt for the sender's records.
PayPal
""".strip(),
    },
    {
        'uid': 'fixture-paypal-sub-004',
        'processor': 'paypal',
        'subject': 'Subscription payment received - $50.00 USD',
        'from_address': 'service@paypal.com',
        'body_text': """
Recurring payment received

You received $50.00 USD from David Recurring (david.r@example.com).
Subscription / monthly gift
Transaction ID: 9B99887766554433
Date: March 1, 2026
""".strip(),
    },
    {
        'uid': 'fixture-cashapp-005',
        'processor': 'cashapp',
        'subject': 'Alex Rivers sent you $40',
        'from_address': 'cash@square.com',
        'body_text': """
Cash App

Alex Rivers sent you $40.00
Cashtag $alexrivers
Payment #CA4F9K2M
Mar 9, 2026

For: Sunday offering
Square, Inc.
""".strip(),
    },
    {
        'uid': 'fixture-venmo-006',
        'processor': 'venmo',
        'subject': 'Chris Park paid you $20.00',
        'from_address': 'venmo@venmo.com',
        'body_text': """
Venmo

Chris Park paid you $20.00
Note: Missions offering
Mar 8, 2026

View transaction in the Venmo app.
""".strip(),
    },
    {
        'uid': 'fixture-ach-bank-007',
        'processor': 'ach',
        'subject': 'ACH Credit Posted - $500.00',
        'from_address': 'alerts@businessbank.example',
        'body_text': """
Business Banking Alert

ACH Credit received
Amount: $500.00
Effective date: 03/07/2026
Company name: GIVINGFUND PROCESSOR
Individual Name: SAMANTHA GRACE
Trace number: 021000021234567
SEC Code: PPD

Your available balance has been updated.
""".strip(),
    },
    {
        'uid': 'fixture-tithely-008',
        'processor': 'tithely',
        'subject': 'You received a donation of $100.00',
        'from_address': 'noreply@tithe.ly',
        'body_text': """
Tithe.ly

You received a donation

Donor: Pastor Support Friend
Email: friend@example.com
Amount: $100.00
Fund: General
Date: 2026-03-06
Donation ID: TL-99887766
Payment method: Card
""".strip(),
    },
    {
        'uid': 'fixture-zelle-009',
        'processor': 'zelle',
        'subject': 'John Smith sent you $60 with Zelle®',
        'from_address': 'noreply@zellepay.com',
        'body_text': """
Zelle

John Smith sent you $60.00
Mar 5, 2026
Memo: Love offering

Money is typically available immediately.
""".strip(),
    },
    {
        'uid': 'fixture-stripe-recurring-010',
        'processor': 'stripe',
        'subject': 'You received a payment of $50.00 USD',
        'from_address': 'receipts@stripe.com',
        'body_text': """
Stripe

Recurring subscription payment received

Payment from Elena Monthly
Customer email: elena.m@example.com
Amount $50.00 USD
Date Mar 1, 2026
Payment ID pi_3OxRecurringGift001
Payment method Visa •••• 1881
Subscription / monthly gift
Fund: General Tithe
""".strip(),
    },
    {
        'uid': 'fixture-pushpay-011',
        'processor': 'pushpay',
        'subject': 'Church donation received - $30.00',
        'from_address': 'noreply@pushpay.com',
        'body_text': """
Pushpay

You received a church donation

Donor: Michael Guest
Email: michael.guest@example.com
Amount: $30.00
Date: 2026-03-04
Transaction ID: PP-44112233
Fund: Missions
Payment method: Card
""".strip(),
    },
]


def all_fixtures():
    return list(FIXTURES)
