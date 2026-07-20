from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("workspace", "0002_correctionrequest_authoritative_file_hash_and_more")]

    operations = [
        migrations.AddField(
            model_name="enginesnapshot",
            name="reference_json",
            field=models.JSONField(default=dict),
        ),
    ]
