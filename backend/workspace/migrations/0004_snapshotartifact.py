import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("workspace", "0003_enginesnapshot_reference_json")]

    operations = [
        migrations.CreateModel(
            name="SnapshotArtifact",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key", models.SlugField(max_length=160)),
                ("category", models.CharField(max_length=32)),
                ("source_path", models.CharField(blank=True, default="", max_length=1000)),
                ("media_type", models.CharField(default="application/json", max_length=100)),
                ("byte_size", models.PositiveBigIntegerField(default=0)),
                ("sha256", models.CharField(max_length=64)),
                ("raw_text", models.TextField(blank=True, default="")),
                ("parsed_json", models.JSONField(default=dict)),
                ("generated_at", models.DateTimeField(blank=True, null=True)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="artifacts", to="workspace.enginesnapshot")),
            ],
            options={"ordering": ["category", "key"]},
        ),
        migrations.AddConstraint(
            model_name="snapshotartifact",
            constraint=models.UniqueConstraint(fields=("snapshot", "key"), name="workspace_snapshot_artifact_key_uniq"),
        ),
        migrations.AddIndex(
            model_name="snapshotartifact",
            index=models.Index(fields=["snapshot", "category", "key"], name="ws_artifact_snapshot_cat_idx"),
        ),
    ]
