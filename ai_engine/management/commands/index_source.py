"""python manage.py index_source repository.Resource 3 media/resources/water-cycle.pdf

Makes one object's file searchable on the Ask page (normally done automatically
when a resource is uploaded).
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from ai_engine import services
from ai_engine.ingest import UnsupportedFile


class Command(BaseCommand):
    help = "Index a file for an object so the Ask page can answer from it."

    def add_arguments(self, parser):
        parser.add_argument("model", help="app_label.ModelName, e.g. repository.Resource")
        parser.add_argument("pk", type=int)
        parser.add_argument("path", help="PDF, PPTX, TXT or MD file")

    def handle(self, *args, **options):
        try:
            model = apps.get_model(options["model"])
            obj = model.objects.get(pk=options["pk"])
        except (LookupError, ValueError) as exc:
            raise CommandError(f"Unknown model {options['model']!r}") from exc
        except Exception as exc:  # DoesNotExist of any model
            raise CommandError(f"No {options['model']} with id {options['pk']}") from exc
        try:
            count = services.index_source(obj, path=options["path"])
        except (UnsupportedFile, FileNotFoundError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Indexed {obj} into {count} chunks."))
