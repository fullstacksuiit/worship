"""The app's module list — one definition, used by the shell nav and the home screen.

Adding a module means adding one entry here: it shows up in the sidebar, in the
mobile drawer, in the phone tab bar (if `tab`) and as a card on the dashboard.
Labels come from the faith preset so the nav speaks the tradition's language.
"""

from .permissions import get_role


def modules(org):
    """Every module, in nav order. `org` supplies the faith-aware wording.

    `native_label` is the same label in the place's own script — blank when the
    tradition has no second language or the place switched it off — so the nav
    can carry both without knowing anything about languages.
    """
    p = org.preset
    n = org.script.get("nav", {})
    return [
        {
            "key": "home", "label": "Home", "icon": "🏠", "url": "core:dashboard",
            "desc": "Everything at a glance", "ns": "core",
            "not_prefix": ("team", "invite", "settings", "category"), "tab": True,
            "native_label": n.get("home", ""),
        },
        {
            "key": "members", "label": p["community_term"], "icon": "👥",
            "url": "members:list", "ns": "members", "tab": True,
            "desc": f"Your {p['member_term'].lower()}s, families and contacts",
            "native_label": n.get("members", ""),
        },
        {
            "key": "finance", "label": "Money", "icon": "💰",
            "url": "finance:overview", "ns": "finance", "tab": True,
            "desc": f"{p['donation_term']}, income and expenses",
            "native_label": n.get("finance", ""),
        },
        {
            "key": "events", "label": "Events", "icon": "📅",
            "url": "events:list", "ns": "events", "tab": True,
            "desc": f"{p['event_term']}, programs and attendance",
            "native_label": n.get("events", ""),
        },
        {
            "key": "notices", "label": "Notices", "icon": "📢",
            "url": "notices:list", "ns": "notices",
            "desc": f"Announcements for your {p['community_term'].lower()}",
            "native_label": n.get("notices", ""),
        },
        {
            "key": "rentals", "label": "Rentals", "icon": "🏛️",
            "url": "rentals:list", "ns": "rentals",
            "desc": "Halls, rooms and property bookings",
            "native_label": n.get("rentals", ""),
        },
        {
            "key": "team", "label": "Team", "icon": "🧑‍🤝‍🧑",
            "url": "core:team_list", "ns": "core", "prefix": ("team", "invite"),
            "admin_only": True,
            "desc": "Who can log in, and what they may change",
            "native_label": n.get("team", ""),
        },
        {
            "key": "settings", "label": "Settings", "icon": "⚙️",
            "url": "core:settings", "ns": "core", "prefix": ("settings", "category"),
            "admin_only": True,
            "desc": ("Your place's name, city and language" if org.language
                     else "Your place's name and city"),
            "native_label": n.get("settings", ""),
        },
    ]


def _is_active(resolver_match, item):
    """Is the request currently inside this module?

    Namespace alone isn't enough for `core`, which holds Home, Team and the
    invite screens — so an item may also require (or forbid) url-name prefixes.
    """
    if resolver_match is None or resolver_match.namespace != item["ns"]:
        return False
    name = resolver_match.url_name or ""
    if "prefix" in item and not name.startswith(item["prefix"]):
        return False
    if "not_prefix" in item and name.startswith(item["not_prefix"]):
        return False
    return True


def visible_modules(org, user, resolver_match=None):
    """The modules this user may see, each marked `active` for the current page."""
    is_admin = get_role(user) == "admin"
    out = []
    for item in modules(org):
        if item.get("admin_only") and not is_admin:
            continue
        out.append({**item, "active": _is_active(resolver_match, item)})
    return out
