"""python manage.py ai_ping "Hello"  - checks the engine from the terminal."""

from django.core.management.base import BaseCommand

from ai_engine import services


class Command(BaseCommand):
    help = "Send one message to the Librarian agent and print the reply."

    def add_arguments(self, parser):
        parser.add_argument("message", nargs="?", default="Hello Librarian, are you online?")

    def handle(self, *args, **options):
        info = services.engine_status()
        self.stdout.write(f"provider: {info.active} ({info.model})")
        if info.fell_back:
            self.stdout.write(self.style.WARNING(f"fell back to MOCK: {info.reason}"))
        run = services.ping(options["message"])
        self.stdout.write(self.style.SUCCESS(f"run #{run.pk} · {run.status} · {run.duration_ms} ms"))
        self.stdout.write(run.output.get("reply", ""))
