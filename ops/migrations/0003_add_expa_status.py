# Generated manually — adds expa_status field to EP model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0002_alter_ep_email_alter_ep_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="ep",
            name="expa_status",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Raw EXPA status from the API (open, applied, accepted, approved, realized, finished, completed, rejected, etc.)",
                max_length=30,
            ),
        ),
    ]
