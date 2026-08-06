from django.db import models
from django.utils import timezone

from members.models import Member


class EP(models.Model):
    """Exchange Participant — the core entity."""

    class Track(models.TextChoices):
        GLOBAL_TALENT = "GT", "Global Talent"
        GLOBAL_TEACHER = "GTe", "Global Teacher"

    class Stage(models.TextChoices):
        OPEN = "open", "Open"
        MATCHED_WITH_OPP = "matched_with_opp", "Matched with opp"
        APPLIED = "applied", "Applied"
        ACCEPTED = "accepted", "Accepted"
        APPROVED = "approved", "Approved"
        ALL_PAPERS_DONE = "all_papers_done", "All papers Done"
        NOT_ALL_PAPERS_DONE = "not_all_papers_done", "Not all papers done"
        DO_PAPERS = "do_papers", "Do Papers"
        REALIZED = "realized", "Realized"

    class ProblemFlag(models.TextChoices):
        NONE = "none", "None"
        FIX_EP_PROBLEM = "fix_ep_problem", "Fix EP Problem"
        FIX_IR_PROBLEM = "fix_ir_problem", "Fix IR Problem"
        PROBLEM_FIXED = "problem_fixed", "Problem Fixed"

    # ── Personal info ─────────────────────────────────────────────────
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, default="", db_index=True)
    socials = models.TextField(blank=True, default="", help_text="WhatsApp, Messenger, etc.")

    # ── Academic ──────────────────────────────────────────────────────
    university = models.CharField(max_length=200, blank=True, default="")
    major = models.CharField(max_length=200, blank=True, default="")
    year_of_study = models.CharField(max_length=50, blank=True, default="")

    # ── Pipeline ──────────────────────────────────────────────────────
    track = models.CharField(max_length=5, choices=Track.choices, default=Track.GLOBAL_TALENT, db_index=True)
    current_stage = models.CharField(
        max_length=30, choices=Stage.choices, default=Stage.OPEN, db_index=True
    )
    problem_flag = models.CharField(
        max_length=20, choices=ProblemFlag.choices, default=ProblemFlag.NONE, db_index=True
    )

    # ── Assignment ────────────────────────────────────────────────────
    assigned_to = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_eps",
        help_text="OPS member or TL responsible",
    )
    matched_opportunity = models.ForeignKey(
        "partners.Opportunity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matched_eps",
    )

    # ── Metadata ──────────────────────────────────────────────────────
    term = models.CharField(max_length=20, default="2026-S1", help_text="e.g. 2026-S1")
    source = models.CharField(
        max_length=20,
        choices=[("manual", "Manual"), ("expa_sync", "EXPA Sync")],
        default="manual",
        db_index=True,
    )
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    tl_notes = models.TextField(blank=True, default="", help_text="Private notes visible only to TL and VP")
    last_edited_by = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_eps",
    )
    last_edited_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False, db_index=True, help_text="Soft-delete — hidden from lists by default")

    class Meta:
        ordering = ["-last_activity_at"]
        verbose_name = "Exchange Participant"
        verbose_name_plural = "Exchange Participants"

    def __str__(self):
        return f"{self.full_name} ({self.get_track_display()} — {self.get_current_stage_display()})"

    def advance_stage(self, new_stage: str, changed_by: Member, note: str = ""):
        """Advance EP to a new stage, logging the history."""
        old_stage = self.current_stage
        self.current_stage = new_stage
        self.last_activity_at = timezone.now()
        self.save(update_fields=["current_stage", "last_activity_at"])

        StageHistory.objects.create(
            ep=self,
            stage=new_stage,
            previous_stage=old_stage,
            changed_by=changed_by,
            note=note,
        )

    def set_problem_flag(self, flag: str, changed_by: Member, note: str = ""):
        """Set problem flag and log the change."""
        self.problem_flag = flag
        self.last_activity_at = timezone.now()
        self.save(update_fields=["problem_flag", "last_activity_at"])

        StageHistory.objects.create(
            ep=self,
            stage=self.current_stage,
            previous_stage=self.current_stage,
            changed_by=changed_by,
            note=f"Problem flag: {flag}" + (f" — {note}" if note else ""),
        )

    @property
    def is_stale(self) -> bool:
        """Check if the EP is stale based on per-stage idle thresholds."""
        from core.models import SiteConfig

        config = SiteConfig.get()
        threshold_days = config.get_threshold(self.current_stage)
        idle = (timezone.now() - self.last_activity_at).days
        return idle > threshold_days

    @property
    def idle_days(self) -> int:
        return (timezone.now() - self.last_activity_at).days

    @property
    def whatsapp_number(self) -> str | None:
        """Extract first WhatsApp-style phone number from socials field."""
        import re

        if not self.socials:
            return None
        # Match phone numbers: +216XXXXXXXX, 00216XXXXXXXX, 2XXXXXXXX
        match = re.search(r'\+?\d{8,15}', self.socials.replace(" ", "").replace("-", ""))
        return match.group(0) if match else None

    @property
    def stage_order(self) -> int:
        """Numeric order for funnel ordering."""
        order_map = {
            "open": 0,
            "matched_with_opp": 1,
            "applied": 2,
            "accepted": 3,
            "approved": 4,
            "all_papers_done": 5,
            "not_all_papers_done": 5,
            "do_papers": 6,
            "realized": 7,
        }
        return order_map.get(self.current_stage, 99)

    def revert_stage(self, changed_by: Member, note: str = ""):
        """Revert to the previous stage — logs the reversal."""
        previous = (
            StageHistory.objects.filter(ep=self)
            .exclude(stage=self.current_stage)
            .order_by("-changed_at")
            .first()
        )
        old_stage = self.current_stage
        new_stage = previous.stage if previous else "open"
        self.current_stage = new_stage
        self.last_activity_at = timezone.now()
        self.save(update_fields=["current_stage", "last_activity_at"])

        StageHistory.objects.create(
            ep=self,
            stage=new_stage,
            previous_stage=old_stage,
            changed_by=changed_by,
            note=f"Reverted from {EP.Stage(old_stage).label}" + (f" — {note}" if note else ""),
        )


class StageHistory(models.Model):
    """Audit trail of EP stage changes — powers funnel reporting."""

    ep = models.ForeignKey(EP, on_delete=models.CASCADE, related_name="stage_history")
    stage = models.CharField(max_length=30, choices=EP.Stage.choices)
    previous_stage = models.CharField(max_length=30, choices=EP.Stage.choices, blank=True, default="")
    changed_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, related_name="stage_changes"
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-changed_at"]
        verbose_name_plural = "Stage histories"

    def __str__(self):
        return f"{self.ep.full_name} → {self.get_stage_display()} @ {self.changed_at:%Y-%m-%d %H:%M}"


class Interaction(models.Model):
    """Replaces WhatsApp scrollback — log of every interaction with an EP."""

    ep = models.ForeignKey(EP, on_delete=models.CASCADE, related_name="interactions")
    author = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, related_name="interactions"
    )
    date = models.DateTimeField(default=timezone.now)
    note = models.TextField()

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.ep.full_name} — {self.author.name if self.author else '?'} @ {self.date:%Y-%m-%d}"


class Attachment(models.Model):
    """Contracts, ID scans, papers — attached to an EP."""

    class Label(models.TextChoices):
        CONTRACT = "contract", "Contract"
        PASSPORT = "passport", "Passport / ID"
        CV = "cv", "CV"
        ACCEPTANCE = "acceptance", "Acceptance Letter"
        OTHER = "other", "Other"

    ep = models.ForeignKey(EP, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="attachments/%Y/%m/")
    label = models.CharField(max_length=20, choices=Label.choices, default=Label.OTHER)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, related_name="uploads"
    )

    def __str__(self):
        return f"{self.ep.full_name} — {self.get_label_display()}"


class SavedFilter(models.Model):
    """User-bookmarked filter preset for the EP list."""

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="saved_filters")
    name = models.CharField(max_length=100)
    query_params = models.JSONField(default=dict, help_text="URL query params as JSON")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [["member", "name"]]

    def __str__(self):
        return f"{self.member.name}: {self.name}"
