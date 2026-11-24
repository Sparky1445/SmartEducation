from .models import Announcement


def announcements(request):
    """Site-wide banner: current announcements, important ones first. Visitors can hide one (session)."""
    hidden = set(request.session.get("hidden_announcements", [])) if hasattr(request, "session") else set()
    return {"announcements": [a for a in Announcement.objects.current()[:3] if a.pk not in hidden]}
