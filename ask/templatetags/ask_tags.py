import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def cite_marks(text):
    """Escape the answer, then turn [2] into a small superscript link to source 2."""
    safe = escape(text)
    return mark_safe(
        re.sub(r"\[(\d+)\]", r'<sup class="cite"><a href="#src-\1">\1</a></sup>', safe)
    )


@register.filter
def match_label(score):
    score = int(score or 0)
    if score >= 80:
        return "strong match"
    if score >= 55:
        return "good match"
    return "weak match"
