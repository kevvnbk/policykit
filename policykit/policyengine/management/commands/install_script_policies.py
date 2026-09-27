from django.core.management.base import BaseCommand

from policyengine import script_runtime
from policyengine.models import GeneratedPolicy


class Command(BaseCommand):
    help = (
        "Run setup(ctx) for script policies that have never been installed. "
        "Needed for policies created before the runtime tracked installs; "
        "the deploy API installs new ones itself."
    )

    def add_arguments(self, parser):
        parser.add_argument("--policy-id", type=int, default=None, help="install just this policy")
        parser.add_argument(
            "--force", action="store_true", help="re-run setup() even if already installed"
        )
        parser.add_argument("--dry-run", action="store_true", help="list what would be installed")

    def handle(self, *args, **options):
        policies = GeneratedPolicy.objects.all()
        if options["policy_id"]:
            policies = policies.filter(pk=options["policy_id"])
        if not options["force"]:
            policies = policies.filter(initialized=False)

        if not policies.exists():
            self.stdout.write("Nothing to install.")
            return

        for policy in policies:
            label = f"[{policy.pk}] {policy.name}"
            if options["dry_run"]:
                self.stdout.write(f"would install {label}")
                continue

            # setup() does real work against the real platform (channel lookups,
            # and whatever else a script does), so this is not a dry run.
            try:
                registry = script_runtime.install_script_policy(policy, force=options["force"])
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"failed  {label}: {type(e).__name__}: {e}"))
                continue
            self.stdout.write(self.style.SUCCESS(f"installed {label} -> {registry or 'no handlers'}"))
