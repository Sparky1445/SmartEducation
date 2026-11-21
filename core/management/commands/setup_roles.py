"""python manage.py setup_roles  - creates the Teacher group with the right permissions.

Add a user to "Teacher" in the admin to let them upload lessons, make and publish
outreach kits, moderate comments and see the teacher dashboard.
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

TEACHER = [
    ("repository", "add_resource"), ("repository", "change_resource"), ("repository", "delete_resource"),
    ("repository", "add_tag"), ("outreach_studio", "add_outreachkit"), ("outreach_studio", "change_outreachkit"),
    ("outreach_studio", "publish_outreachkit"), ("engagement", "change_comment"), ("engagement", "delete_comment"),
    ("engagement", "view_feedback"), ("engagement", "change_feedback"),
]


class Command(BaseCommand):
    help = "Create or update the Teacher group."

    def handle(self, *args, **options):
        group, created = Group.objects.get_or_create(name="Teacher")
        perms = [Permission.objects.get(content_type__app_label=app, codename=code) for app, code in TEACHER]
        group.permissions.set(perms)
        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} Teacher group with {len(perms)} permissions."))
