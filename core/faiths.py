"""Faith presets — the single source of truth for faith-aware terminology.

Pick a faith when you set up your place of worship and everything downstream
(labels, wording, defaults) comes predefined from here. Later phases (members,
money, events) read their vocabulary from these presets, so the whole app speaks
the language of the tradition it serves.

Most traditions also carry a `script` block: the same words again in the
language the place actually speaks — Urdu for a masjid, Gurmukhi for a
gurudwara, Hebrew for a synagogue. When a place has one, the app shows both,
English first and the mother tongue beside it, so someone who reads only one of
the two can still find their way around every screen.

Keep this file boring and declarative — no logic, just data. To support a new
tradition, add one entry to FAITHS; the `script` block is optional.
"""

FAITHS = {
    "masjid": {
        "label": "Masjid",
        "tradition": "Islam",
        "icon": "🕌",
        # What we call the place, its people, its giving, its leader, its gatherings.
        "place_term": "Masjid",
        "member_term": "Musalli",
        "community_term": "Jamaat",
        "donation_term": "Chanda",
        "leader_term": "Imam",
        "event_term": "Jalsa",
        "greeting": "Assalamu Alaikum",
        "currency": "INR",
        # Starting vocabulary — the place edits and grows these as it works.
        "income_categories": ["Chanda", "Zakat", "Sadaqah", "Fitrah", "Donation box"],
        "event_categories": ["Jumuah", "Jalsa", "Taraweeh", "Nikah", "Class"],
        "script": {
            "language": "Urdu",
            "native_name": "اردو",
            "code": "ur",
            "direction": "rtl",
            "font": "Noto Nastaliq Urdu",
            "terms": {
                "place_term": "مسجد",
                "member_term": "مصلی",
                "community_term": "جماعت",
                "donation_term": "چندہ",
                "leader_term": "امام",
                "event_term": "جلسہ",
                "greeting": "السلام علیکم",
            },
            "nav": {
                "home": "صفحۂ اول", "members": "جماعت", "finance": "حساب",
                "events": "پروگرام", "notices": "اعلانات", "rentals": "کرایہ",
                "team": "ٹیم", "settings": "ترتیبات",
            },
        },
    },
    "mandir": {
        "label": "Mandir",
        "tradition": "Hinduism",
        "icon": "🛕",
        "place_term": "Mandir",
        "member_term": "Bhakt",
        "community_term": "Sangat",
        "donation_term": "Daan",
        "leader_term": "Pujari",
        "event_term": "Puja",
        "greeting": "Namaste",
        "currency": "INR",
        "income_categories": ["Daan", "Dakshina", "Annadaan", "Hundi"],
        "event_categories": ["Puja", "Aarti", "Bhajan", "Katha", "Festival"],
        "script": {
            "language": "Hindi",
            "native_name": "हिन्दी",
            "code": "hi",
            "direction": "ltr",
            "font": "Noto Sans Devanagari",
            "terms": {
                "place_term": "मंदिर",
                "member_term": "भक्त",
                "community_term": "संगत",
                "donation_term": "दान",
                "leader_term": "पुजारी",
                "event_term": "पूजा",
                "greeting": "नमस्ते",
            },
            "nav": {
                "home": "मुख्य पृष्ठ", "members": "संगत", "finance": "हिसाब",
                "events": "कार्यक्रम", "notices": "सूचनाएँ", "rentals": "किराया",
                "team": "टीम", "settings": "सेटिंग्स",
            },
        },
    },
    "church": {
        "label": "Church",
        "tradition": "Christianity",
        "icon": "⛪",
        "place_term": "Church",
        "member_term": "Member",
        "community_term": "Congregation",
        "donation_term": "Offering",
        "leader_term": "Pastor",
        "event_term": "Service",
        "greeting": "Peace be with you",
        "currency": "INR",
        "income_categories": ["Offering", "Tithe", "Mission fund"],
        "event_categories": ["Service", "Sunday school", "Prayer meeting", "Wedding", "Baptism"],
    },
    "gurudwara": {
        "label": "Gurudwara",
        "tradition": "Sikhism",
        "icon": "🛕",
        "place_term": "Gurudwara",
        "member_term": "Sewadar",
        "community_term": "Sangat",
        "donation_term": "Chadhava",
        "leader_term": "Granthi",
        "event_term": "Kirtan",
        "greeting": "Sat Sri Akaal",
        "currency": "INR",
        "income_categories": ["Chadhava", "Golak", "Langar seva", "Daswandh"],
        "event_categories": ["Kirtan", "Path", "Langar", "Gurpurab", "Anand Karaj"],
        "script": {
            "language": "Punjabi",
            "native_name": "ਪੰਜਾਬੀ",
            "code": "pa",
            "direction": "ltr",
            "font": "Noto Sans Gurmukhi",
            "terms": {
                "place_term": "ਗੁਰਦੁਆਰਾ",
                "member_term": "ਸੇਵਾਦਾਰ",
                "community_term": "ਸੰਗਤ",
                "donation_term": "ਚੜ੍ਹਾਵਾ",
                "leader_term": "ਗ੍ਰੰਥੀ",
                "event_term": "ਕੀਰਤਨ",
                "greeting": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ",
            },
            "nav": {
                "home": "ਮੁੱਖ ਪੰਨਾ", "members": "ਸੰਗਤ", "finance": "ਹਿਸਾਬ",
                "events": "ਪ੍ਰੋਗਰਾਮ", "notices": "ਸੂਚਨਾਵਾਂ", "rentals": "ਕਿਰਾਇਆ",
                "team": "ਟੀਮ", "settings": "ਸੈਟਿੰਗਾਂ",
            },
        },
    },
    "vihara": {
        "label": "Vihara",
        "tradition": "Buddhism",
        "icon": "☸️",
        "place_term": "Vihara",
        "member_term": "Upasaka",
        "community_term": "Sangha",
        "donation_term": "Dana",
        "leader_term": "Bhante",
        "event_term": "Puja",
        "greeting": "Namo Buddhaya",
        "currency": "INR",
        "income_categories": ["Dana", "Alms fund", "Robe offering", "Library fund"],
        "event_categories": ["Puja", "Meditation", "Dhamma talk", "Uposatha", "Vesak"],
        "script": {
            "language": "Hindi",
            "native_name": "हिन्दी",
            "code": "hi",
            "direction": "ltr",
            "font": "Noto Sans Devanagari",
            "terms": {
                "place_term": "विहार",
                "member_term": "उपासक",
                "community_term": "संघ",
                "donation_term": "दान",
                "leader_term": "भंते",
                "event_term": "पूजा",
                "greeting": "नमो बुद्धाय",
            },
            "nav": {
                "home": "मुख्य पृष्ठ", "members": "संघ", "finance": "हिसाब",
                "events": "कार्यक्रम", "notices": "सूचनाएँ", "rentals": "किराया",
                "team": "टीम", "settings": "सेटिंग्स",
            },
        },
    },
    "derasar": {
        "label": "Derasar",
        "tradition": "Jainism",
        "icon": "🛕",
        "place_term": "Derasar",
        "member_term": "Shravak",
        "community_term": "Sangh",
        "donation_term": "Daan",
        "leader_term": "Acharya",
        "event_term": "Puja",
        "greeting": "Jai Jinendra",
        "currency": "INR",
        "income_categories": ["Daan", "Bhandar", "Boli", "Swamivatsalya"],
        "event_categories": ["Puja", "Snatra Puja", "Pratikraman", "Paryushan", "Aarti"],
        "script": {
            "language": "Gujarati",
            "native_name": "ગુજરાતી",
            "code": "gu",
            "direction": "ltr",
            "font": "Noto Sans Gujarati",
            "terms": {
                "place_term": "દેરાસર",
                "member_term": "શ્રાવક",
                "community_term": "સંઘ",
                "donation_term": "દાન",
                "leader_term": "આચાર્ય",
                "event_term": "પૂજા",
                "greeting": "જય જિનેન્દ્ર",
            },
            "nav": {
                "home": "મુખ્ય પાનું", "members": "સંઘ", "finance": "હિસાબ",
                "events": "કાર્યક્રમ", "notices": "સૂચનાઓ", "rentals": "ભાડું",
                "team": "ટીમ", "settings": "સેટિંગ્સ",
            },
        },
    },
    "synagogue": {
        "label": "Synagogue",
        "tradition": "Judaism",
        "icon": "🕍",
        "place_term": "Synagogue",
        "member_term": "Member",
        "community_term": "Kehillah",
        "donation_term": "Tzedakah",
        "leader_term": "Rabbi",
        "event_term": "Service",
        "greeting": "Shalom",
        "currency": "INR",
        "income_categories": ["Tzedakah", "Membership dues", "Building fund", "Yahrzeit"],
        "event_categories": ["Shabbat service", "Torah study", "Festival", "Bar Mitzvah", "Wedding"],
        "script": {
            "language": "Hebrew",
            "native_name": "עברית",
            "code": "he",
            "direction": "rtl",
            "font": "Noto Sans Hebrew",
            "terms": {
                "place_term": "בית כנסת",
                "member_term": "חבר",
                "community_term": "קהילה",
                "donation_term": "צדקה",
                "leader_term": "רב",
                "event_term": "תפילה",
                "greeting": "שלום",
            },
            "nav": {
                "home": "בית", "members": "קהילה", "finance": "כספים",
                "events": "אירועים", "notices": "הודעות", "rentals": "השכרות",
                "team": "צוות", "settings": "הגדרות",
            },
        },
    },
    "agiary": {
        "label": "Agiary",
        "tradition": "Zoroastrianism",
        "icon": "🔥",
        "place_term": "Agiary",
        "member_term": "Behdin",
        "community_term": "Anjuman",
        "donation_term": "Ashodad",
        "leader_term": "Mobed",
        "event_term": "Jashan",
        "greeting": "Sahebji",
        "currency": "INR",
        "income_categories": ["Ashodad", "Muktad fund", "Sandalwood", "Trust donation"],
        "event_categories": ["Jashan", "Navjote", "Muktad", "Gahambar", "Wedding"],
        "script": {
            "language": "Gujarati",
            "native_name": "ગુજરાતી",
            "code": "gu",
            "direction": "ltr",
            "font": "Noto Sans Gujarati",
            "terms": {
                "place_term": "અગિયારી",
                "member_term": "બહેદિન",
                "community_term": "અંજુમન",
                "donation_term": "આશોદાદ",
                "leader_term": "મોબેદ",
                "event_term": "જશન",
                "greeting": "સાહેબજી",
            },
            "nav": {
                "home": "મુખ્ય પાનું", "members": "અંજુમન", "finance": "હિસાબ",
                "events": "કાર્યક્રમ", "notices": "સૂચનાઓ", "rentals": "ભાડું",
                "team": "ટીમ", "settings": "સેટિંગ્સ",
            },
        },
    },
    # The catch-all, so no place is turned away for not being on the list above.
    # Plain English words only — whoever picks this renames things as they go,
    # the same way every other place edits its categories.
    "other": {
        "label": "Place of worship",
        "tradition": "Any tradition",
        "icon": "🏛️",
        "place_term": "Place",
        "member_term": "Member",
        "community_term": "Community",
        "donation_term": "Donation",
        "leader_term": "Leader",
        "event_term": "Gathering",
        "greeting": "Welcome",
        "currency": "INR",
        "income_categories": ["Donation", "Offering", "Membership"],
        "event_categories": ["Gathering", "Prayer", "Class", "Festival"],
    },
}

# Categories every place needs whatever its tradition, merged into the above.
COMMON_INCOME_CATEGORIES = ["Rent", "Grant"]
COMMON_EXPENSE_CATEGORIES = [
    "Electricity", "Water", "Salary", "Repairs", "Cleaning", "Supplies", "Charity",
]
# What a place rents out. Every place owns a different mix — shops on the street
# side, a hall upstairs, an open ground — so this is a starting vocabulary the
# place grows by typing, exactly like the money and event labels above.
COMMON_PROPERTY_CATEGORIES = ["Hall", "Shop", "Room", "Ground", "Guest room"]

# (value, human label) pairs for the faith dropdown / model choices.
FAITH_CHOICES = [(key, preset["label"]) for key, preset in FAITHS.items()]

# Currency code -> display symbol. Extend as more currencies are supported.
CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "GBP": "£", "EUR": "€"}


def currency_symbol(code):
    return CURRENCY_SYMBOLS.get(code, code)


def faith_options():
    """The traditions, with enough detail to show what picking one changes.

    Sign-up shows these as tiles rather than a dropdown: the choice sets the
    app's whole vocabulary — and its second language — so it should show its
    consequences, not hide them.
    """
    return [
        {
            "value": key,
            "label": preset["label"],
            "tradition": preset["tradition"],
            "icon": preset["icon"],
            "greeting": preset["greeting"],
            "member_term": preset["member_term"],
            "donation_term": preset["donation_term"],
            # Named in both languages, so the tile can say "also in Urdu · اردو"
            # before anyone commits to the choice.
            "language": preset.get("script", {}).get("language", ""),
            "native_name": preset.get("script", {}).get("native_name", ""),
            "native_greeting": preset.get("script", {}).get("terms", {}).get("greeting", ""),
            "script_code": preset.get("script", {}).get("code", ""),
            "script_direction": preset.get("script", {}).get("direction", "ltr"),
        }
        for key, preset in FAITHS.items()
    ]


def get_preset(faith):
    """Return the preset dict for a faith key (empty dict if unknown)."""
    return FAITHS.get(faith, {})


def get_script(faith):
    """The second language for this tradition — an empty dict if it has none.

    Empty is a perfectly ordinary answer (a church gets English only), so every
    caller reads this as "show the second word if there is one".
    """
    return get_preset(faith).get("script", {})


def script_fonts():
    """Every font the second languages need, for the sign-up page.

    Sign-up is the one screen that shows all the traditions at once; every other
    screen only ever needs its own place's font.
    """
    return sorted({s["font"] for s in (get_script(f) for f in FAITHS) if s})


# The words the app speaks, and what each one is for — the settings screen
# lists them in this order so a place can see its whole vocabulary at once.
TERM_KEYS = [
    ("place_term", "The place itself"),
    ("member_term", "One person"),
    ("community_term", "Everyone together"),
    ("donation_term", "Money given"),
    ("leader_term", "Who leads"),
    ("event_term", "A gathering"),
    ("greeting", "How you greet"),
]


def vocabulary(faith):
    """Every word this tradition uses, English beside its own script."""
    preset, terms = get_preset(faith), get_script(faith).get("terms", {})
    return [
        {"what": what, "english": preset.get(key, ""), "native": terms.get(key, "")}
        for key, what in TERM_KEYS
        if preset.get(key)
    ]


def default_categories(faith):
    """Starting categories for a new place, keyed by scope.

    Deliberately short lists: enough that the first entry needs no thought,
    few enough that the place's own words quickly take over.
    """
    preset = get_preset(faith)
    return {
        "income": preset.get("income_categories", []) + COMMON_INCOME_CATEGORIES,
        "expense": list(COMMON_EXPENSE_CATEGORIES),
        "event": preset.get("event_categories", []),
        "property": list(COMMON_PROPERTY_CATEGORIES),
    }
