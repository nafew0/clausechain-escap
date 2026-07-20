from django.db import migrations, models

import accounts.branding


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_sitesettings_signup_rate_limits_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="branding_favicon",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=accounts.branding.branding_asset_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="branding_login_banner",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=accounts.branding.branding_asset_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="branding_logo",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=accounts.branding.branding_asset_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="branding_register_banner",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=accounts.branding.branding_asset_upload_to,
            ),
        ),
    ]
