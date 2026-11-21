"""Shared template helpers for the Ledger design system (Unit III: custom tags)."""

from django import template

register = template.Library()


@register.inclusion_tag("core/_section_head.html")
def section_head(title, meta=""):
    """Serif section title with a mono caption on the right."""
    return {"title": title, "meta": meta}


@register.filter
def initials(text):
    """'Smart Education' -> 'SE'; used for avatar placeholders."""
    return "".join(word[0] for word in str(text).split()[:2]).upper()
