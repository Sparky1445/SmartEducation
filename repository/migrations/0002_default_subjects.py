from django.db import migrations

SUBJECTS = [
    ("Science", "science"), ("Mathematics", "mathematics"), ("Social Science", "social-science"),
    ("Geography", "geography"), ("History", "history"), ("English", "english"), ("Hindi", "hindi"),
    ("Marathi", "marathi"), ("Konkani", "konkani"), ("Computer Science", "computer-science"),
]


def add_subjects(apps, schema_editor):
    Subject = apps.get_model("repository", "Subject")
    for name, slug in SUBJECTS:
        Subject.objects.get_or_create(slug=slug, defaults={"name": name})


def remove_subjects(apps, schema_editor):
    apps.get_model("repository", "Subject").objects.filter(slug__in=[s for _, s in SUBJECTS], resources__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("repository", "0001_initial")]
    operations = [migrations.RunPython(add_subjects, remove_subjects)]
