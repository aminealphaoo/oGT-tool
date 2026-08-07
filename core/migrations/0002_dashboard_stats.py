from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="DashboardStats",
            fields=[
                ("config", models.OneToOneField(on_delete=models.CASCADE, primary_key=True, related_name="dashboard_stats", serialize=False, to="core.siteconfig")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Last time stats were updated")),
                ("total_eps", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Total EPs")),
                ("expa_applied", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="EXPA Applied")),
                ("expa_accepted", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="EXPA Accepted")),
                ("expa_approved", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="EXPA Approved")),
                ("expa_realized", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="EXPA Realized")),
                ("expa_finished", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="EXPA Finished / Completed")),
                ("stage_open", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Stage: Open")),
                ("stage_matched", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Stage: Matched with Opp")),
                ("stage_applied", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Stage: Applied")),
                ("stage_accepted", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Stage: Accepted")),
                ("stage_approved", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Stage: Approved")),
                ("stage_papers", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Stage: Papers")),
                ("stage_realized", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Stage: Realized")),
                ("problem_cases", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Problem Cases")),
                ("stale_cases", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Stale Cases")),
                ("pipeline_value", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="EPs in Pipeline")),
                ("realized_last_30", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Realized (last 30 days)")),
                ("ir_partners", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="IR Partners")),
                ("open_opps", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Open Opportunities")),
                ("interactions_period", models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Interactions this period")),
            ],
            options={"verbose_name": "Dashboard Stats", "verbose_name_plural": "Dashboard Stats"},
        ),
    ]
