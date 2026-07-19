from .models import FaithTradition
from .permissions import ALL_CAPS, role_caps

# Per-faith UI labels so one template set serves every tradition.
FAITH_BRANDING = {
    FaithTradition.ISLAM: {
        "place": "Mosque",
        "accent": "emerald",
        "icon": "🕌",
    },
    FaithTradition.HINDUISM: {
        "place": "Mandir",
        "accent": "orange",
        "icon": "🛕",
    },
    FaithTradition.CHRISTIANITY: {
        "place": "Church",
        "accent": "indigo",
        "icon": "⛪",
    },
    FaithTradition.SIKHISM: {
        "place": "Gurudwara",
        "accent": "amber",
        "icon": "🪯",
    },
    FaithTradition.BUDDHISM: {
        "place": "Temple",
        "accent": "yellow",
        "icon": "☸️",
    },
    FaithTradition.JUDAISM: {
        "place": "Synagogue",
        "accent": "blue",
        "icon": "🕍",
    },
    FaithTradition.JAINISM: {
        "place": "Derasar",
        "accent": "red",
        "icon": "🛕",
    },
    FaithTradition.BAHAI: {
        "place": "Bahá'í House of Worship",
        "accent": "rose",
        "icon": "⭐",
    },
}

DEFAULT_BRANDING = {"place": "Worship Place", "accent": "slate", "icon": "🙏"}

# Concrete hex values for each accent so raw CSS (e.g. form-control focus rings,
# custom <select> chevrons) can be brand-tinted — Tailwind utility classes alone
# can't reach a global stylesheet. Keys: soft (100), ring (200), base (500),
# strong (600). Falls back to slate for any unmapped accent name.
ACCENT_HEX = {
    "emerald": {"soft": "#d1fae5", "ring": "#a7f3d0", "base": "#10b981", "strong": "#059669"},
    "orange": {"soft": "#ffedd5", "ring": "#fed7aa", "base": "#f97316", "strong": "#ea580c"},
    "indigo": {"soft": "#e0e7ff", "ring": "#c7d2fe", "base": "#6366f1", "strong": "#4f46e5"},
    "amber": {"soft": "#fef3c7", "ring": "#fde68a", "base": "#f59e0b", "strong": "#d97706"},
    "yellow": {"soft": "#fef9c3", "ring": "#fef08a", "base": "#eab308", "strong": "#ca8a04"},
    "blue": {"soft": "#dbeafe", "ring": "#bfdbfe", "base": "#3b82f6", "strong": "#2563eb"},
    "red": {"soft": "#fee2e2", "ring": "#fecaca", "base": "#ef4444", "strong": "#dc2626"},
    "rose": {"soft": "#ffe4e6", "ring": "#fecdd3", "base": "#f43f5e", "strong": "#e11d48"},
    "teal": {"soft": "#ccfbf1", "ring": "#99f6e4", "base": "#14b8a6", "strong": "#0d9488"},
    "slate": {"soft": "#f1f5f9", "ring": "#e2e8f0", "base": "#64748b", "strong": "#475569"},
}


def organization(request):
    """Expose the current organization and its faith branding to all templates.

    The faith tradition sets the defaults; an org can override the accent colour
    and icon via its customisable settings (core.preferences)."""
    org = getattr(request, "organization", None)
    if org is None:
        branding = dict(DEFAULT_BRANDING)
        branding["hex"] = ACCENT_HEX["slate"]
        return {"current_org": None, "branding": branding}

    branding = dict(FAITH_BRANDING.get(org.faith_tradition, DEFAULT_BRANDING))
    if org.pref("accent_color"):
        branding["accent"] = org.pref("accent_color")
    if org.pref("icon"):
        branding["icon"] = org.pref("icon")
    branding["hex"] = ACCENT_HEX.get(branding["accent"], ACCENT_HEX["slate"])
    return {"current_org": org, "branding": branding}


def capabilities(request):
    """Expose the signed-in user's role and capabilities to every template so
    the nav and page controls can hide areas the role can't reach.

    `caps` is a flat name→bool map (e.g. `caps.finance_access`); `org_role` and
    `org_role_label` describe the current role. Fails closed: no role → nothing
    granted."""
    role = getattr(request, "org_role", None)
    granted = role_caps(role)
    membership = getattr(request, "org_membership", None)
    return {
        "caps": {cap: (cap in granted) for cap in ALL_CAPS},
        "org_role": role,
        "org_role_label": membership.role_label if membership else "",
    }
