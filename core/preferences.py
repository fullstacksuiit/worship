"""The customisable-settings registry.

Each entry below defines one organization setting: how it's labelled, what kind
of input it uses, its default, and which section of the settings page it appears
under. The settings form and template are both generated from this list, so
adding a new customisable option is a one-line change here — no migration (values
live in Organization.preferences JSON), no new form field, no template edit.
"""

# Tailwind palette colours usable as a faith-independent accent override. These
# strings are interpolated into class names (bg-{accent}-600 etc.), so they must
# be real Tailwind colours.
ACCENT_CHOICES = [
    ("", "Match faith tradition"),
    ("emerald", "Emerald"),
    ("orange", "Orange"),
    ("indigo", "Indigo"),
    ("amber", "Amber"),
    ("rose", "Rose"),
    ("blue", "Blue"),
    ("teal", "Teal"),
    ("violet", "Violet"),
    ("slate", "Slate"),
]

MONTH_CHOICES = [
    ("1", "January"), ("2", "February"), ("3", "March"), ("4", "April"),
    ("5", "May"), ("6", "June"), ("7", "July"), ("8", "August"),
    ("9", "September"), ("10", "October"), ("11", "November"), ("12", "December"),
]

DATE_FORMAT_CHOICES = [
    ("d M Y", "31 Dec 2026"),
    ("M j, Y", "Dec 31, 2026"),
    ("Y-m-d", "2026-12-31"),
    ("d/m/Y", "31/12/2026"),
    ("m/d/Y", "12/31/2026"),
]


# type is one of: "bool", "text", "choice".
# Each dict: key, label, group, type, default, (choices for "choice"), help.
ORG_PREFERENCES = [
    # --- Appearance ----------------------------------------------------------
    {
        "key": "accent_color",
        "label": "Accent colour",
        "group": "Appearance",
        "type": "choice",
        "choices": ACCENT_CHOICES,
        "default": "",
        "help": "Override the colour derived from your faith tradition.",
    },
    {
        "key": "icon",
        "label": "Brand icon",
        "group": "Appearance",
        "type": "text",
        "default": "",
        "help": "A single emoji shown beside your name (blank uses the default).",
    },
    # --- Donations -----------------------------------------------------------
    {
        "key": "receipt_prefix",
        "label": "Receipt number prefix",
        "group": "Donations",
        "type": "text",
        "default": "",
        "help": 'Printed before receipt numbers, e.g. "AL-" → AL-1024.',
    },
    {
        "key": "thank_you_message",
        "label": "Receipt thank-you message",
        "group": "Donations",
        "type": "text",
        "default": "Thank you for your generous contribution.",
        "help": "Shown at the foot of donation receipts.",
    },
    # --- Regional ------------------------------------------------------------
    {
        "key": "date_format",
        "label": "Date format",
        "group": "Regional",
        "type": "choice",
        "choices": DATE_FORMAT_CHOICES,
        "default": "d M Y",
        "help": "How dates are displayed throughout the app.",
    },
    {
        "key": "fiscal_year_start_month",
        "label": "Financial year starts in",
        "group": "Regional",
        "type": "choice",
        "choices": MONTH_CHOICES,
        "default": "1",
        "help": "Used to group budgets and financial reporting.",
    },
    # --- Privacy -------------------------------------------------------------
    {
        "key": "hide_anonymous_donors",
        "label": "Hide anonymous donors in reports",
        "group": "Privacy",
        "type": "bool",
        "default": False,
        "help": "Exclude gifts marked anonymous from member-facing reports.",
    },
]

# Section order on the settings page (groups not listed fall to the end).
PREFERENCE_GROUP_ORDER = ["Appearance", "Donations", "Regional", "Privacy"]

# Per-group presentation: a short description and a Heroicons-style SVG path
# (24x24, stroke=currentColor) for the tab and panel header, matching the rest
# of the app. A group without an entry still renders, just without an icon.
PREFERENCE_GROUP_META = {
    "Appearance": {
        "description": "Colours and branding shown across the app.",
        "icon": "M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 "
                "4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 "
                "2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01",
    },
    "Donations": {
        "description": "Defaults applied to gifts and receipts.",
        "icon": "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 "
                "0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 "
                "12a9 9 0 11-18 0 9 9 0 0118 0z",
    },
    "Regional": {
        "description": "How dates and the financial year are handled.",
        "icon": "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 "
                "00-2 2v12a2 2 0 002 2z",
    },
    "Privacy": {
        "description": "Control what is shown about your donors.",
        "icon": "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 "
                "0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 "
                "5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
    },
}


def preference_default(key):
    """Default value for a preference key, or None if the key is unknown."""
    for spec in ORG_PREFERENCES:
        if spec["key"] == key:
            return spec["default"]
    return None
