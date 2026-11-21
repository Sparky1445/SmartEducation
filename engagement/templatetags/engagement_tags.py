"""Drop-in comment threads and star ratings for any page (Unit III: inclusion tags).

    {% load engagement_tags %}
    {% rating_for kit %}
    {% comments_for kit %}
"""

from django import template
from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch

from ..forms import CommentForm
from ..models import Comment, Rating

register = template.Library()


def _count_label(n: int) -> str:
    return f"{n} comment{'s' if n != 1 else ''}"


@register.inclusion_tag("engagement/_comments.html", takes_context=True)
def comments_for(context, obj):
    request = context["request"]
    visible = Comment.objects.filter(is_visible=True).select_related("user")
    comments = (
        Comment.objects.for_object(obj)
        .filter(is_visible=True, parent__isnull=True)
        .select_related("user")
        .prefetch_related(Prefetch("replies", queryset=visible))
    )
    return {
        "request": request,
        "user": request.user,
        "obj": obj,
        "ct_id": ContentType.objects.get_for_model(obj).pk,
        "comments": comments,
        "count_label": _count_label(Comment.objects.for_object(obj).filter(is_visible=True).count()),
        "form": CommentForm(),
    }


@register.inclusion_tag("engagement/_rating.html", takes_context=True)
def rating_for(context, obj):
    request = context["request"]
    mine = None
    if request.user.is_authenticated:
        mine = Rating.objects.for_object(obj).filter(user=request.user).values_list("stars", flat=True).first()
    return {
        "request": request,
        "user": request.user,
        "obj": obj,
        "ct_id": ContentType.objects.get_for_model(obj).pk,
        "summary": Rating.summary(obj),
        "mine": mine,
        "stars": range(1, 6),
    }


@register.filter
def stars_text(value):
    """3.4 -> '★★★☆☆'."""
    full = int(round(float(value or 0)))
    return "★" * full + "☆" * (5 - full)
