from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("workspace", "0004_snapshotartifact")]

    operations = [
        migrations.AddField(
            model_name="reviewitem",
            name="review_subject_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="evidencerow",
            name="review_subject_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="findingdecision",
            name="review_subject_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
