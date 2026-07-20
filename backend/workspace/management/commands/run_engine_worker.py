import time

from django.core.management.base import BaseCommand

from workspace.engine_worker import claim_next_action, execute_action


class Command(BaseCommand):
    help = "Claim and execute allowlisted ClauseChain engine actions."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-seconds", type=float, default=2.0)

    def handle(self, *args, **options):
        while True:
            action = claim_next_action()
            if action is not None:
                self.stdout.write(f"Running {action.kind} action {action.pk}")
                execute_action(action)
                self.stdout.write(f"Action {action.pk}: {action.status}")
            if options["once"]:
                return
            time.sleep(max(0.25, options["poll_seconds"]))
