"""Bilingual wording — one word, shown in both of the place's languages.

`{% term org "member_term" %}` prints the English word and, when the place has
a second language switched on, the same word in its own script beside it. Every
screen uses this instead of reaching for `org.preset.x` directly, so turning the
second language on or off is one switch, not an edit in forty templates.
"""

from django import template
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import mark_safe

from ..faiths import script_fonts

register = template.Library()


@register.simple_tag
def term(org, key, lower=False):
    """The place's word for `key`, in English and in its own script.

    `key` is a preset key — "member_term", "community_term", "greeting"… Pass
    `lower=True` where the word sits mid-sentence; the second script is left
    alone, since most writing systems have no case to change.
    """
    if org is None:
        return ""

    english = org.preset.get(key, "")
    if lower:
        english = english.lower()

    native = org.native.get(key, "")
    if not native:
        return conditional_escape(english)

    script = org.script
    return format_html(
        '{}<span class="native" lang="{}" dir="{}">{}</span>',
        english, script.get("code", ""), script.get("direction", "ltr"), native,
    )


@register.simple_tag
def native(org, key):
    """Just the second-language word — for places that already say it in English.

    Renders nothing at all when the place has no second language, so it can be
    dropped beside a heading without an `{% if %}` around it.
    """
    if org is None or not org.native.get(key):
        return ""
    script = org.script
    return format_html(
        '<span class="native" lang="{}" dir="{}">{}</span>',
        script.get("code", ""), script.get("direction", "ltr"), org.native[key],
    )


@register.simple_tag
def native_text(org, text, code="", direction="", css=""):
    """Wrap an already-translated string (a nav label, a language name).

    The word comes from the caller rather than from a preset key; the language
    and direction default to the place's own. `css` adds utility classes — how
    a caller drops the leading gap inside brackets, say.
    """
    if not text:
        return ""
    script = getattr(org, "script", {}) if org is not None else {}
    return format_html(
        '<span class="native {}" lang="{}" dir="{}">{}</span>',
        css,
        code or script.get("code", ""),
        direction or script.get("direction", "ltr"),
        text,
    )


@register.simple_tag
def native_font_url(org):
    """The Google Fonts URL for this place's script — nothing if it needs none.

    Only the one font the place actually reads is fetched; a masjid never pays
    for the Hebrew face, and an English-only place fetches nothing.
    """
    font = getattr(org, "script", {}).get("font", "") if org is not None else ""
    if not font:
        return ""
    return mark_safe(_font_url([font]))


@register.simple_tag
def every_script_font_url():
    """Every script's font in one request — for sign-up, which shows them all."""
    return mark_safe(_font_url(script_fonts()))


def _font_url(fonts):
    families = "&".join(f"family={f.replace(' ', '+')}:wght@400;600" for f in sorted(set(fonts)))
    return f"https://fonts.googleapis.com/css2?{families}&display=swap"
