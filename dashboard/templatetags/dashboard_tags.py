from django import template

register = template.Library()


@register.inclusion_tag("dashboard/_stat_card.html")
def stat_card(label, value, unit="", note="", accent=False):
    """{% stat_card "Questions" q.total note="last 14 days" %}"""
    return {"label": label, "value": value, "unit": unit, "note": note, "accent": accent}


@register.filter
def percent_of(part, whole):
    try:
        return round(100 * float(part) / float(whole)) if float(whole) else 0
    except (TypeError, ValueError):
        return 0
