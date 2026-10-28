from django.core.management.base import BaseCommand

from policyengine import script_runtime


class Command(BaseCommand):
    help = (
        "Write the generated-policy capabilities manifest (ctx methods, events, "
        "actions) to policyengine/generated_policy_manifest.json. Re-run and "
        "commit whenever the script runtime changes; a test fails until you do."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", default=str(script_runtime.MANIFEST_PATH), help="where to write it"
        )

    def handle(self, *args, **options):
        with open(options["output"], "w", encoding="utf-8") as f:
            f.write(script_runtime.manifest_json())
        self.stdout.write(self.style.SUCCESS(f"wrote {options['output']}"))
