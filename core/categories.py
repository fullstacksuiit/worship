"""The category box — one text input that remembers.

The whole point is that nobody has to manage categories. You type a word into
the same box you always type into; if the place has used it before it appears
as a suggestion, and if it hasn't, typing it is what adds it. No setup screen,
no dropdown that's missing the option you need.
"""
from django import forms
from django.utils.html import format_html, format_html_join

from .models import Category


class CategoryInput(forms.TextInput):
    """A text box with a list of the labels this place already uses.

    The obvious build is a native `<datalist>`, and that's what this was — but
    the browser draws that panel itself, ignoring every style the app sets, so
    it landed as a black box over the next field. The list here is ordinary
    markup instead: it looks like the rest of the app, and typing something new
    still just works. Behaviour lives in `base.html` next to the other shell
    scripts; without JavaScript this degrades to a plain text box, which is
    exactly what the field is anyway.
    """

    def __init__(self, attrs=None):
        super().__init__(attrs)
        self.suggestions = []

    def render(self, name, value, attrs=None, renderer=None):
        attrs = {**(attrs or {}), "autocomplete": "off"}
        if not self.suggestions:
            return super().render(name, value, attrs, renderer)

        list_id = f"{attrs.get('id') or 'id_' + name}__options"
        attrs.update({
            "role": "combobox",
            "aria-expanded": "false",
            "aria-autocomplete": "list",
            "aria-controls": list_id,
        })
        return format_html(
            '<div class="combo" data-combo>'
            '{}'
            '<button type="button" class="combo-toggle" tabindex="-1"'
            ' aria-label="Show suggestions">'
            '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8"'
            ' stroke-linecap="round" stroke-linejoin="round"><path d="M6 8l4 4 4-4"/></svg>'
            '</button>'
            '<ul class="combo-list" id="{}" role="listbox" hidden>{}</ul>'
            '</div>',
            super().render(name, value, attrs, renderer),
            list_id,
            format_html_join(
                "", '<li class="combo-option" role="option">{}</li>',
                ((s,) for s in self.suggestions),
            ),
        )


class CategoryField(forms.CharField):
    """Free-text category that cleans to a `Category` row, creating it on first use.

    Drop it over a `category` ForeignKey in a ModelForm's `__init__` and the
    rest of the form works unchanged — the cleaned value is a real row, so
    saving, filtering and reporting all group reliably.
    """

    widget = CategoryInput

    def __init__(self, organization, scope, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("max_length", 100)
        super().__init__(**kwargs)
        self.organization = organization
        self.scope = scope
        self.widget.suggestions = (
            Category.names(organization, scope) if organization else []
        )
        self.widget.attrs.setdefault("placeholder", "Type or pick…")

    def prepare_value(self, value):
        """Show the label, whatever we were handed — a row, its id, or raw text."""
        if isinstance(value, Category):
            return value.name
        if isinstance(value, int):
            return Category.objects.filter(pk=value).values_list("name", flat=True).first() or ""
        return value

    def clean(self, value):
        return Category.resolve(self.organization, self.scope, super().clean(value))
