# Starter copy when creating a notice for an empty category.

CATEGORY_STARTER_TEMPLATES = {
    'community_guidelines': (
        'Community Guidelines',
        """Our online community exists to encourage faith, fellowship, and respectful dialogue. We ask all members and visitors to:

- Treat others with kindness, humility, and respect
- Share content that edifies and builds up the body of Christ
- Avoid harassment, hate speech, profanity, or personal attacks
- Respect privacy — do not share others' personal information without consent
- Stay on topic and contribute meaningfully to discussions

Content that violates these guidelines may be removed. Repeat violations may result in restricted access to commenting features.""",
    ),
    'comment_policy': (
        'Comment & Content Policy',
        """You are welcome to participate in discussions, leave comments, and share your thoughts on our community pages. By posting content, you agree to the following:

We reserve the right to remove, edit, or hide any comment or user-submitted content for any reason or no reason, with or without prior notice.

When we moderate content, we usually explain that the material does not align with our Community Guidelines. We are not obligated to provide an explanation in every case.

We may also remove content that appears to be spam, abusive, off-topic, or harmful to our community.

By using this site, you acknowledge that moderation decisions are at the sole discretion of church leadership and designated moderators.""",
    ),
    'terms': (
        'Terms of Use',
        """By accessing and using this church website and its community features, you agree to these Terms of Use.

This site is provided for church ministry, fellowship, and communication. You agree to use it lawfully and in a manner consistent with our published Community Guidelines and Comment Policy.

We may update these terms at any time. Continued use of the site after changes are posted constitutes acceptance of the updated terms.

The church reserves the right to suspend or restrict access to site features at its discretion.""",
    ),
    'privacy': (
        'Privacy Policy',
        """We respect your privacy. This policy describes how we handle information collected through this website.

Information you provide (such as account details, prayer requests, comments, or event sign-ups) is used to operate church ministry features and communicate with you as appropriate.

We do not sell your personal information. Access to member data is limited to authorized church leadership and volunteers who need it for ministry purposes.

If you have questions about this policy or wish to request correction or removal of your information, please contact the church office.""",
    ),
    'general': (
        'General Legal Notice',
        """This section contains general legal notices and disclaimers published by the church.

Content on this website is provided for informational and ministry purposes. The church makes reasonable efforts to keep information accurate but does not guarantee completeness or suitability for every purpose.

Add your church-specific disclaimers, copyright notices, or other legal statements here.""",
    ),
}


def starter_for_category(category_slug: str):
    return CATEGORY_STARTER_TEMPLATES.get(category_slug)