from .models import FaithTradition

# Per-faith UI labels so one template set serves all four traditions.
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
}

DEFAULT_BRANDING = {"place": "Worship Place", "accent": "slate", "icon": "🙏"}


def organization(request):
    """Expose the current organization and its faith branding to all templates.

    The faith tradition sets the defaults; an org can override the accent colour
    and icon via its customisable settings (core.preferences)."""
    org = getattr(request, "organization", None)
    if org is None:
        return {"current_org": None, "branding": DEFAULT_BRANDING}

    branding = dict(FAITH_BRANDING.get(org.faith_tradition, DEFAULT_BRANDING))
    if org.pref("accent_color"):
        branding["accent"] = org.pref("accent_color")
    if org.pref("icon"):
        branding["icon"] = org.pref("icon")
    return {"current_org": org, "branding": branding}
