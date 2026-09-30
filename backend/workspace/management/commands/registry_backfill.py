import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from workspace.models import EngineSnapshot
from workspace.registry import reconcile_snapshot


class Command(BaseCommand):
    help = "Create the initial ESCAP evidence registry from the active stored snapshot."

    def handle(self, *args, **options):
        snapshot = EngineSnapshot.objects.filter(active=True).first()
        if snapshot is None:
            raise CommandError("No active engine snapshot is available.")
        if hasattr(snapshot, "evidence_change_set"):
            change_set = snapshot.evidence_change_set
            created = False
        else:
            with transaction.atomic():
                try:
                    change_set = reconcile_snapshot(snapshot)
                except ValueError as exc:
                    raise CommandError(str(exc)) from exc
            created = True
        self.stdout.write(
            json.dumps(
                {
                    "created": created,
                    "snapshot_id": str(snapshot.pk),
                    "change_set_id": str(change_set.pk),
                    "state": change_set.state,
                    "counts": change_set.counts_json,
                },
                sort_keys=True,
            )
        )
