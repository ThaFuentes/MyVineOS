# Parse payment-provider notification emails into structured gift data.
# Fixtures mirror real-world wording from Stripe, PayPal, Cash App, ACH banks, Venmo, Tithe.ly.

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ParsedGift:
    processor: str
    amount: float
    currency: str = 'USD'
    donor_name: str = ''
    donor_email: str = ''
    confirmation_number: str = ''
    method: str = ''
    date: str = ''  # YYYY-MM-DD
    notes: str = ''
    fund_label: str = ''
    is_recurring: bool = False
    external_id: str = ''
    confidence: float = 0.0
    raw_subject: str = ''
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# Prefer labeled money ($12.00 / Amount: 12.00) — never bare decimals from IPs
AMOUNT_LABELED_RE = re.compile(
    r'(?:'
    r'(?:amount|total|payment|paid|sent you|received|donation|gift|credit)\s*[:\-]?\s*'
    r'|(?:USD\s*)\$?\s*'
    r'|\$\s*'
    r')'
    r'([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+\.[0-9]{2})'
    r'(?:\s*(?:USD|usd))?',
    re.I,
)
AMOUNT_DOLLAR_RE = re.compile(
    r'\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+\.[0-9]{2})\b',
    re.I,
)
# Keep legacy name for any external imports
AMOUNT_RE = AMOUNT_DOLLAR_RE
IP_V4_RE = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b')
EMAIL_RE = re.compile(r'[\w.+-]+@[\w.-]+\.\w+', re.I)
DATE_RE = re.compile(
    r'\b('
    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}'
    r'|\d{4}-\d{2}-\d{2}'
    r'|\d{1,2}/\d{1,2}/\d{2,4}'
    r')\b',
    re.I,
)

NON_PAYMENT_MARKERS = (
    'client configuration settings',
    'mail client manual settings',
    'calendar & contacts manual settings',
    'imap port',
    'pop3 port',
    'smtp port',
    'cpanel',
    'mail delivery failed',
    'mailer-daemon',
    'undelivered mail returned',
    'delivery status notification',
    'password reset',
    'reset your password',
    'verify your email',
    'confirm your email',
    'two-factor',
    'ssl/tls settings',
    'do not reply to this automated message',
    'mobileconfig',
    'carddav',
    'caldav',
)

PAYMENT_SIGNAL_MARKERS = (
    'you received a payment',
    'you received a donation',
    "you've received",
    'sent you $',
    'paid you $',
    'payment from',
    'payment id',
    'transaction id',
    'donation id',
    'receipt number',
    'ach credit',
    'ach deposit',
    'direct deposit',
    'tithe',
    'offering',
    'stripe.com',
    'paypal.com',
    'cash app',
    'venmo',
    'zelle',
    'tithe.ly',
    'pushpay',
    'givelify',
    'planning center',
    'amount $',
    'amount:',
    'payment method',
)


def _mask_non_money_numbers(text: str) -> str:
    t = text or ''
    t = IP_V4_RE.sub('[ip]', t)
    t = re.sub(r'(?i)\bport\s*:\s*\d+', 'port: [n]', t)
    return t


def _first_amount(text: str) -> Optional[float]:
    cleaned = _mask_non_money_numbers(text or '')
    for cre in (AMOUNT_LABELED_RE, AMOUNT_DOLLAR_RE):
        m = cre.search(cleaned)
        if not m:
            continue
        try:
            val = float(m.group(1).replace(',', ''))
        except ValueError:
            continue
        if 0.01 <= val <= 1_000_000:
            return val
    return None


def is_non_payment_email(subject: str, body: str, from_addr: str = '') -> bool:
    blob = f'{subject or ""}\n{from_addr or ""}\n{body or ""}'.lower()
    if any(m in blob for m in NON_PAYMENT_MARKERS):
        return True
    from_l = (from_addr or '').lower()
    if 'cpanel' in from_l or 'mailer-daemon' in from_l or 'postmaster@' in from_l:
        return True
    return False


def has_payment_signals(subject: str, body: str, from_addr: str = '', processor: str = 'unknown') -> bool:
    if processor and processor not in ('unknown', ''):
        return True
    blob = f'{subject or ""}\n{from_addr or ""}\n{body or ""}'.lower()
    return any(m in blob for m in PAYMENT_SIGNAL_MARKERS)


def _normalize_date(raw: str) -> str:
    raw = (raw or '').strip()
    if not raw:
        return datetime.utcnow().strftime('%Y-%m-%d')
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%B %d, %Y', '%b %d, %Y', '%b %d %Y'):
        try:
            return datetime.strptime(raw.replace(',', ''), fmt.replace(',', '')).strftime('%Y-%m-%d')
        except ValueError:
            continue
    # try with comma in month day year
    for fmt in ('%B %d, %Y', '%b %d, %Y'):
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return datetime.utcnow().strftime('%Y-%m-%d')


def _find_date(text: str) -> str:
    m = DATE_RE.search(text or '')
    return _normalize_date(m.group(1) if m else '')


def detect_processor(subject: str, body: str, from_addr: str = '') -> str:
    """Identify payment processor. Prefer From-domain, then unique brand markers."""
    blob = f'{subject}\n{from_addr}\n{body}'.lower()
    from_l = (from_addr or '').lower()

    # Domain / brand in From header (highest confidence)
    domain_rules = [
        ('stripe', ('stripe.com',)),
        ('paypal', ('paypal.com',)),
        ('cashapp', ('cash.app', 'square.com', 'squareup.com')),
        ('venmo', ('venmo.com',)),
        ('tithely', ('tithe.ly',)),
        ('zelle', ('zellepay.com', 'zelle.com')),
        ('pushpay', ('pushpay.com',)),
        ('givelify', ('givelify.com',)),
        ('planning_center', ('planningcenteronline.com', 'churchcenter.com')),
    ]
    for name, domains in domain_rules:
        if any(d in from_l for d in domains):
            return name

    # Explicit brand strings in subject/body (specific first — avoid generic phrases)
    content_rules = [
        ('zelle', ('zelle®', 'with zelle', 'zelle',)),
        ('stripe', ('stripe.com', 'stripe payment', 'stripe ach', ' payment id pi_', ' payment id ch_', ' payment id py_')),
        ('paypal', ('paypal.com', 'paypal', "you've received", 'transaction id:')),
        ('cashapp', ('cash app', 'cash.app', 'square, inc', 'cashtag')),
        ('venmo', ('venmo', 'paid you')),
        ('tithely', ('tithe.ly', 'tithely', 'you received a donation')),
        ('pushpay', ('pushpay',)),
        ('givelify', ('givelify',)),
        ('planning_center', ('planning center', 'church center')),
        ('ach', ('ach credit', 'ach deposit', 'electronic deposit', 'direct deposit', 'ach payment', 'nacha', 'sec code:')),
        # Generic last — only if nothing brand-specific matched
        ('stripe', ('you received a payment', 'payment receipt from')),
        ('cashapp', ('sent you $',)),
    ]
    for name, needles in content_rules:
        if any(n in blob for n in needles):
            return name
    return 'unknown'


def default_donation_parse_mode() -> str:
    """
    Software chooses how to parse — staff should not pick a format.
    Prefer AI when configured; otherwise rules with auto AI fallback.
    """
    try:
        from app.utils.ai_assist_parse import ai_configured
        if ai_configured():
            return 'ai'
    except Exception:
        pass
    return 'auto'


def parse_payment_email(
    subject: str,
    body: str,
    from_addr: str = '',
    received_at: str = '',
    *,
    use_ai: str | bool | None = None,
) -> ParsedGift:
    """
    Best-effort multi-processor parser. Staff do not pick email format —
    software detects Stripe/PayPal/etc. and fills amount/donor/method.

    use_ai:
      - None          — software default (AI first when configured)
      - False/'rules' — rules only (no API call)
      - True/'ai'     — always try AI after rules, merge results
      - 'auto'        — AI when rules are weak
    """
    from app.utils.ai_assist_parse import (
        ai_parse_donation_email,
        merge_donation_parse,
        normalize_parse_mode,
    )

    if use_ai is None:
        use_ai = default_donation_parse_mode()
    mode = normalize_parse_mode(
        'ai' if use_ai is True else ('rules' if use_ai is False else str(use_ai))
    )
    gift = _parse_payment_email_rules(subject, body, from_addr, received_at)

    # Hard non-payment (cPanel, bounces, etc.) — never call AI, never invent a gift
    if (gift.extras or {}).get('not_a_payment'):
        extras = dict(gift.extras or {})
        extras['parse_mode'] = 'rules'
        extras['ai_used'] = False
        gift.extras = extras
        return gift

    need_ai = mode == 'ai' or (
        mode == 'auto'
        and gift.amount > 0
        and (gift.confidence < 70 or gift.processor == 'unknown')
    )
    # auto + no amount: stay skipped (do not spend AI on newsletters / config mail)
    if mode == 'auto' and gift.amount <= 0:
        need_ai = False
    if not need_ai:
        extras = dict(gift.extras or {})
        extras['parse_mode'] = 'rules'
        extras['ai_used'] = False
        gift.extras = extras
        return gift

    # Do not feed a dubious rules amount into AI (causes copy-through of IP false positives)
    hint = gift.to_dict()
    if gift.processor == 'unknown' or gift.confidence < 50:
        hint = dict(hint)
        hint['amount'] = 0
        hint['confidence'] = min(float(hint.get('confidence') or 0), 40)
        hint['notes'] = (
            (hint.get('notes') or '')
            + ' Rules were uncertain; verify this is really a payment email.'
        ).strip()

    ai_data, ai_err = ai_parse_donation_email(
        subject, body, from_addr, rules_hint=hint
    )
    if not ai_data:
        extras = dict(gift.extras or {})
        extras['parse_mode'] = 'rules'
        extras['ai_used'] = False
        extras['ai_error'] = ai_err or 'ai failed'
        gift.extras = extras
        return gift

    merged = merge_donation_parse(gift.to_dict(), ai_data)
    # Final safety: non-payment markers still force skip even if model is messy
    if is_non_payment_email(subject, body, from_addr):
        merged['amount'] = 0
        merged['confidence'] = 0
        extras = dict(merged.get('extras') or {})
        extras['not_a_payment'] = True
        extras['skip_reason'] = 'non_payment_markers'
        merged['extras'] = extras
    return ParsedGift(
        processor=merged.get('processor') or gift.processor,
        amount=float(merged.get('amount') or 0),
        currency=merged.get('currency') or 'USD',
        donor_name=merged.get('donor_name') or gift.donor_name,
        donor_email=merged.get('donor_email') or gift.donor_email,
        confirmation_number=merged.get('confirmation_number') or gift.confirmation_number,
        method=merged.get('method') or gift.method,
        date=merged.get('date') or gift.date,
        notes=merged.get('notes') or gift.notes,
        fund_label=merged.get('fund_label') or gift.fund_label,
        is_recurring=bool(merged.get('is_recurring')),
        external_id=merged.get('external_id') or gift.external_id,
        confidence=float(merged.get('confidence') or gift.confidence),
        raw_subject=gift.raw_subject,
        extras=merged.get('extras') or {'parse_mode': 'rules+ai', 'ai_used': True},
    )


def _parse_payment_email_rules(subject: str, body: str, from_addr: str = '', received_at: str = '') -> ParsedGift:
    """Deterministic multi-processor parser (no AI)."""
    subject = subject or ''
    body = body or ''
    text = f'{subject}\n{body}'
    processor = detect_processor(subject, body, from_addr)

    # Clear non-gifts first (cPanel config used IP 72.48.x.x as a fake $72.48 before)
    if is_non_payment_email(subject, body, from_addr):
        return ParsedGift(
            processor='unknown',
            amount=0.0,
            method='',
            donor_name='',
            confidence=0.0,
            raw_subject=subject[:500],
            notes='Not a payment notification (system / config / bounce / marketing).',
            extras={
                'from_address': from_addr,
                'not_a_payment': True,
                'skip_reason': 'non_payment_markers',
            },
        )

    amount = _first_amount(text) or 0.0
    # Unknown processor without payment language: do not treat random numbers as gifts
    if amount > 0 and not has_payment_signals(subject, body, from_addr, processor):
        amount = 0.0
    date = _find_date(text)
    if received_at and not DATE_RE.search(text):
        date = _normalize_date(str(received_at)[:10])

    donor_name = ''
    donor_email = ''
    confirmation = ''
    method = processor.title() if processor != 'unknown' else 'Online'
    is_recurring = bool(re.search(r'recurring|subscription|monthly gift|autopay', text, re.I))
    fund = ''
    external_id = ''
    notes_parts = [f'Imported from {processor} email.']

    # --- Processor-specific patterns ---
    if processor == 'stripe':
        method = 'Stripe'
        # Prefer explicit Customer: / Payment from: lines over subject "receipt from Church"
        for pat in (
            r'Customer\s*[:\-]\s*(.+)',
            r'Payment\s+from\s*[:\-]?\s*(.+)',
            r'Customer\s+email\s*[:\-]?\s*[\w.+-]+@[\w.-]+\.\w+',  # skip — email only
        ):
            m = re.search(pat, text, re.I)
            if m and 'email' not in pat.lower():
                candidate = m.group(1).strip().split('\n')[0][:120]
                if candidate and 'community church' not in candidate.lower():
                    donor_name = candidate
                    break
        if not donor_name:
            m = re.search(r'Customer\s*[:\-]\s*(.+)', text, re.I)
            if m:
                donor_name = m.group(1).strip().split('\n')[0][:120]
        m = re.search(r'(pi_[a-zA-Z0-9]+|ch_[a-zA-Z0-9]+|py_[a-zA-Z0-9]+)', text)
        if m:
            external_id = m.group(1)
            confirmation = m.group(1)
        if not confirmation:
            m = re.search(r'Receipt\s*(?:number|#)\s*[:#]?\s*([A-Z0-9-]+)', text, re.I)
            if m:
                confirmation = m.group(1)
                external_id = external_id or confirmation
        if re.search(r'\bach\b|bank debit|us_bank_account|us bank account', text, re.I):
            method = 'Stripe ACH'
        m = re.search(r'Fund\s*[:\-]\s*(.+)', text, re.I)
        if m:
            fund = m.group(1).strip().split('\n')[0][:80]
        emails = EMAIL_RE.findall(body)
        donor_email = next((e for e in emails if 'stripe.com' not in e.lower()), '') or ''

    elif processor == 'paypal':
        method = 'PayPal'
        m = re.search(
            r'(?:You received a payment from|you\'ve received \$[\d,.]+ USD from|from)\s+'
            r'([A-Za-z][A-Za-z0-9 .\'-]{1,80}?)(?:\s*\(|\s*$)',
            text,
            re.I | re.M,
        )
        if m:
            donor_name = m.group(1).strip().rstrip('.')
        if not donor_name:
            m = re.search(r'from\s+([A-Za-z][A-Za-z0-9 .\'-]{1,60})\s*\(', text, re.I)
            if m:
                donor_name = m.group(1).strip()
        m = re.search(r'Transaction\s*ID\s*[:#]?\s*([A-Z0-9]{10,25})', text, re.I)
        if m:
            confirmation = m.group(1)
            external_id = m.group(1)
        emails = EMAIL_RE.findall(body)
        donor_email = next((e for e in emails if 'paypal.com' not in e.lower()), '') or ''
        if re.search(r'subscription|recurring|monthly gift', text, re.I):
            is_recurring = True
            method = 'PayPal Recurring'
        m = re.search(r'Note\s*[:\-]\s*(.+)', text, re.I)
        if m:
            fund = fund or m.group(1).strip().split('\n')[0][:80]

    elif processor == 'cashapp':
        method = 'Cash App'
        m = re.search(r'([A-Za-z][\w .-]{0,60})\s+sent you\s+\$', text, re.I)
        if m:
            donor_name = m.group(1).strip()
        m = re.search(r'Cashtag\s+(\$[A-Za-z0-9_]{2,24})', text, re.I)
        if m:
            notes_parts.append(f'Cashtag {m.group(1)}')
            if not donor_name:
                donor_name = m.group(1)
        elif not donor_name:
            m = re.search(r'(\$[A-Za-z0-9_]{2,24})', text)
            if m:
                donor_name = m.group(1)
                notes_parts.append(f'Cashtag {m.group(1)}')
        m = re.search(r'(?:Payment\s*#|#)\s*([A-Z0-9]{6,20})', text, re.I)
        if m:
            confirmation = m.group(1)
            external_id = m.group(1)
        m = re.search(r'For\s*[:\-]\s*(.+)', text, re.I)
        if m:
            fund = m.group(1).strip().split('\n')[0][:80]

    elif processor == 'venmo':
        method = 'Venmo'
        m = re.search(r'([A-Za-z][\w .-]{1,60})\s+paid you\s+\$', text, re.I)
        if m:
            donor_name = m.group(1).strip()
        m = re.search(r'Note\s*[:\-]\s*(.+)', text, re.I)
        if m:
            notes_parts.append('Note: ' + m.group(1).strip()[:200])
            fund = m.group(1).strip()[:80]

    elif processor == 'ach':
        method = 'ACH'
        m = re.search(r'(?:Individual\s+Name|Remitter)\s*[:\-]?\s*(.+)', text, re.I)
        if m:
            donor_name = m.group(1).strip().split('\n')[0][:120]
        if not donor_name:
            m = re.search(r'(?:from|originator|company name)\s*[:\-]?\s*(.+)', text, re.I)
            if m:
                donor_name = m.group(1).strip().split('\n')[0][:120]
        m = re.search(r'(?:Trace|ACH)\s*(?:#|number)?\s*[:\-]?\s*([0-9]{6,20})', text, re.I)
        if m:
            confirmation = m.group(1)
            external_id = m.group(1)

    elif processor == 'tithely':
        method = 'Tithe.ly'
        m = re.search(r'Donor\s*[:\-]?\s*(.+)', text, re.I)
        if m:
            donor_name = m.group(1).strip().split('\n')[0][:120]
        m = re.search(r'Fund\s*[:\-]?\s*(.+)', text, re.I)
        if m:
            fund = m.group(1).strip().split('\n')[0][:80]
        m = re.search(r'(?:Donation|Transaction)\s*ID\s*[:\-]?\s*([A-Za-z0-9_-]+)', text, re.I)
        if m:
            confirmation = m.group(1)
            external_id = m.group(1)
        emails = EMAIL_RE.findall(body)
        donor_email = next((e for e in emails if 'tithe.ly' not in e.lower()), '') or donor_email

    elif processor == 'zelle':
        method = 'Zelle'
        m = re.search(r'([A-Za-z][\w .-]{1,60})\s+sent you\s+\$', text, re.I)
        if m:
            donor_name = m.group(1).strip()
        m = re.search(r'(?:Memo|Note)\s*[:\-]\s*(.+)', text, re.I)
        if m:
            fund = m.group(1).strip().split('\n')[0][:80]
            notes_parts.append('Memo: ' + fund)

    elif processor in ('pushpay', 'givelify', 'planning_center', 'tithely'):
        if processor == 'pushpay':
            method = 'Pushpay'
        elif processor == 'givelify':
            method = 'Givelify'
        elif processor == 'planning_center':
            method = 'Planning Center'
        m = re.search(r'Donor\s*[:\-]?\s*(.+)', text, re.I)
        if m and not donor_name:
            donor_name = m.group(1).strip().split('\n')[0][:120]
        m = re.search(r'Fund\s*[:\-]?\s*(.+)', text, re.I)
        if m:
            fund = m.group(1).strip().split('\n')[0][:80]
        m = re.search(r'(?:Donation|Transaction)\s*ID\s*[:\-]?\s*([A-Za-z0-9_-]+)', text, re.I)
        if m:
            confirmation = m.group(1)
            external_id = m.group(1)
        emails = EMAIL_RE.findall(body)
        skip = ('noreply', 'no-reply', 'pushpay.com', 'givelify.com', 'planningcenter')
        donor_email = next((e for e in emails if not any(s in e.lower() for s in skip)), '') or donor_email

    # Fallbacks
    if not donor_name:
        m = re.search(r'(?:from|sender|payer|donor)\s*[:\-]?\s*([A-Za-z][^\n@]{1,80})', text, re.I)
        if m:
            donor_name = m.group(1).strip()[:120]
    if not donor_name:
        donor_name = 'Online Donor'
    if not donor_email:
        emails = EMAIL_RE.findall(body)
        skip = ('noreply', 'no-reply', 'stripe.com', 'paypal.com', 'cash.app', 'venmo.com', 'tithe.ly')
        donor_email = next((e for e in emails if not any(s in e.lower() for s in skip)), '') or ''
    if not external_id and confirmation:
        external_id = confirmation
    if not external_id:
        # Stable digest so re-imports dedupe across process restarts
        digest = hashlib.sha256(
            f'{subject}|{amount}|{date}|{from_addr}|{donor_name}'.encode('utf-8', errors='replace')
        ).hexdigest()[:16]
        external_id = f'em-{digest}'

    score = 10.0
    if amount > 0:
        score += 35
    if donor_name and donor_name != 'Online Donor':
        score += 15
    # Only real provider IDs boost confidence — not synthetic em-* digests
    real_id = bool(confirmation) or (
        bool(external_id) and not str(external_id).startswith('em-')
    )
    if real_id:
        score += 15
    if processor != 'unknown':
        score += 20
    if donor_email:
        score += 10
    if amount <= 0:
        score = min(score, 25.0)
    if processor == 'unknown' and amount > 0:
        # Cautious: money-like number without a known processor
        score = min(score, 55.0)
    score = min(100.0, score)

    return ParsedGift(
        processor=processor,
        amount=float(amount or 0),
        currency='USD',
        donor_name=donor_name if amount > 0 else '',
        donor_email=donor_email if amount > 0 else '',
        confirmation_number=(confirmation or external_id) if amount > 0 else '',
        method=method if amount > 0 else '',
        date=date,
        notes=' '.join(notes_parts),
        fund_label=fund,
        is_recurring=is_recurring,
        external_id=external_id if amount > 0 else '',
        confidence=score,
        raw_subject=subject[:500],
        extras={'from_address': from_addr},
    )
