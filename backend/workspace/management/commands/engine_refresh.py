import json

from django.core.management.base import BaseCommand, CommandError

from workspace.importer import SnapshotImportError, import_snapshot


class Command(BaseCommand):
    help = "Atomically import the current ClauseChain engine review artifacts."

    def add_arguments(self, parser):
        parser.add_argument("--keep", type=int, default=5)

    def handle(self, *args, **options):
        try:
            snapshot, created = import_snapshot(keep=max(1, options["keep"]))
        except SnapshotImportError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps(
                {
                    "snapshot_id": str(snapshot.pk),
                    "source_hash": snapshot.source_hash,
                    "created": created,
                    "counts": snapshot.counts_json,
                },
                sort_keys=True,
            )
        )
