from django.db import migrations


def backfill(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Profile = apps.get_model("accounts", "Profile")
    for user in User.objects.filter(profile__isnull=True):
        is_teacher = user.is_staff or user.groups.filter(name="Teacher").exists()
        Profile.objects.create(user=user, role="teacher" if is_teacher else "visitor")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
