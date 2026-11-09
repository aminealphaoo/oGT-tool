from django.db import models
from django.utils import timezone

from members.models import Member


from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

from members.models import Member, Team


class EP(models.Model):
    """Exchange Participant — the core entity."""

    class Track(models.TextChoices):
        GLOBAL_TALENT = "GTa", "Global Talent"
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

    # ── Matching Profile Fields ───────────────────────────────────────
    skills = models.JSONField(default=list, help_text="Liste de compétences: ['Python', 'Marketing', 'Design']")
    languages = models.JSONField(default=dict, help_text="{'Français': 'C1', 'Anglais': 'B2'}")
    study_field = models.CharField(max_length=100, blank=True, help_text="Domaine d'études: Informatique, Business, Éducation...")
    study_level = models.CharField(max_length=50, blank=True, help_text="Bac, Bac+3, Bac+5...")
    preferred_countries = models.JSONField(default=list, help_text="Liste des pays prioritaires")
    preferred_domains = models.JSONField(default=list, help_text="['IT', 'Marketing', 'Business', 'Education']")
    experience_level = models.CharField(max_length=50, blank=True, choices=[('Junior','Junior'),('Intermédiaire','Intermédiaire'),('Senior','Senior')])
    availability_date = models.DateField(null=True, blank=True, help_text="Date à partir de laquelle l'EP peut partir")
    duration_preference = models.PositiveIntegerField(null=True, blank=True, help_text="Durée souhaitée en mois")
    keywords = models.TextField(blank=True, help_text="Mots-clés libres séparés par des virgules")

    # ── Assignment & Scoping ──────────────────────────────────────────
    assigned_to = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_eps",
        help_text="OPS member or TL responsible (legacy field)",
    )
    assigned_area = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eps",
        help_text="The functional Key Area team managing this EP",
    )
    assigned_member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="my_eps",
        help_text="The specific member assigned to manage this EP",
    )
    
    @property
    def matched_opportunity(self):
        match = self.match_records.filter(
            status__in=['proposed', 'interview_scheduled', 'approved', 'Proposed', 'Interview Scheduled', 'Approved']
        ).first()
        return match.opportunity if match else None

    @property
    def match_history(self):
        return self.match_records.order_by('created_at')

    # ── Acquisition Sources (Marketing & Comms) ───────────────────────
    acquisition_source = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ('Social Media', 'Social Media'),
            ('Event', 'Événement'),
            ('Referral', 'Parrainage'),
            ('University', 'Université'),
            ('Website', 'Site Web'),
            ('Other', 'Autre'),
        ]
    )
    lead_date = models.DateField(null=True, blank=True, help_text="Date de première prise de contact (lead)")

    # ── Metadata ──────────────────────────────────────────────────────
    term = models.CharField(max_length=20, default="2026-S1", help_text="e.g. 2026-S1")
    source = models.CharField(
        max_length=20,
        choices=[("manual", "Manual")],
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
    def current_stage_days(self) -> int:
        """Calculate days spent in the current stage based on latest stage history or last activity."""
        latest_change = self.stage_history.filter(stage=self.current_stage).order_by("-changed_at").first()
        start_time = latest_change.changed_at if latest_change else self.last_activity_at
        if not start_time:
            return 0
        return (timezone.now() - start_time).days

    @property
    def stage_alert_level(self) -> str:
        """
        Calculates problem level for applied, matched_with_opp, accepted:
        - 'red': > 7 days in stage
        - 'orange': 3 to 7 days in stage
        - 'normal': < 3 days or in other stages
        """
        ALERT_STAGES = ["applied", "matched_with_opp", "accepted"]
        if self.current_stage not in ALERT_STAGES:
            return "normal"
        
        days = self.current_stage_days
        if days > 7:
            return "red"
        elif days >= 3:
            return "orange"
        return "normal"

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

    def get_match_history(self):
        return self.match_records.all()

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

    class Meta:
        indexes = [
            models.Index(fields=["current_stage", "is_archived"], name="ep_stage_archived_idx"),
            models.Index(fields=["track", "current_stage"], name="ep_track_stage_idx"),
            models.Index(fields=["assigned_member", "current_stage"], name="ep_member_stage_idx"),
            models.Index(fields=["-last_activity_at", "is_archived"], name="ep_last_activity_idx"),
        ]

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
        CV = "cv", "CV"
        CONTRACT = "contract", "Contract"
        APPROVAL_MAIL = "approval_mail", "Approval mail"
        ACCEPTANCE_MAIL = "acceptance_mail", "Acceptance mail"
        HEALTH_INSURANCE = "health_insurance", "Health insurance"
        GOAL_SETTING = "goal_setting", "Goal setting before realization"
        OPS_INVITATION = "ops_invitation", "OPS invitation"
        OPS_DELIVERY = "ops_delivery", "OPS delivery"
        COMMUNICATION = "communication", "Communication with EP"
        DEBRIEF = "debrief", "Debrief"
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

    @property
    def file_url(self):
        if not self.file:
            return ""
        url = self.file.url
        if "cloudinary.com" in url and "/image/upload/" in url:
            file_name = getattr(self.file, "name", "")
            if file_name.lower().endswith(".pdf") and not url.lower().endswith(".pdf"):
                return f"{url}.pdf"
        return url


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


# ==================== MARC : Marketing & Communications ====================
class Campaign(models.Model):
    name = models.CharField(max_length=200)
    key_area = models.ForeignKey(Team, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    channel = models.CharField(max_length=50, choices=[
        ('Instagram', 'Instagram'), ('LinkedIn', 'LinkedIn'), 
        ('Facebook', 'Facebook'), ('Campus', 'Campus'), ('Email', 'Email'), ('Other', 'Other')
    ])
    target_audience = models.TextField(blank=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    leads_generated = models.PositiveIntegerField(default=0)
    eps_converted = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(Member, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=[('Planned','Planifiée'),('Active','Active'),('Completed','Terminée')], default='Planned')

    def __str__(self):
        return self.name


class Lead(models.Model):
    """Prospect avant conversion en EP"""
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    university = models.CharField(max_length=200, blank=True)
    study_field = models.CharField(max_length=100, blank=True)
    interest_track = models.CharField(max_length=20, choices=[('GTa','Global Talent'),('GTe','Global Teacher')])
    source_campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    assigned_marc_member = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    status = models.CharField(max_length=20, choices=[
        ('New','Nouveau'),('Contacted','Contacté'),('Interested','Intéressé'),
        ('Applied','Candidaté'),('Converted','Converti en EP'),('Lost','Perdu')
    ], default='New')
    created_at = models.DateTimeField(auto_now_add=True)
    converted_to_ep = models.ForeignKey(EP, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.status})"


class MarComEvent(models.Model):
    """Événements de recrutement (info sessions, stands...)"""
    name = models.CharField(max_length=200)
    event_type = models.CharField(max_length=50, choices=[
        ('Info Session','Session d\'info'),('Stand','Stand université'),
        ('Workshop','Atelier'),('Online Webinar','Webinaire')
    ])
    date = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True)
    attendees_count = models.PositiveIntegerField(default=0)
    leads_generated = models.PositiveIntegerField(default=0)
    eps_converted = models.PositiveIntegerField(default=0)
    organized_by = models.ForeignKey(Member, on_delete=models.CASCADE)
    key_area = models.ForeignKey(Team, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


# ==================== FINANCE & LEGAL ====================
class Contract(models.Model):
    CONTRACT_TYPES = [
        ('EP_Agreement','Contrat EP'),
        ('IR_Partnership','Accord Partenariat IR'),
        ('University_Agreement','Convention Université'),
        ('Sponsor','Contrat Sponsoring'),
    ]
    contract_type = models.CharField(max_length=50, choices=CONTRACT_TYPES)
    related_ep = models.ForeignKey(EP, on_delete=models.CASCADE, null=True, blank=True)
    related_partner = models.ForeignKey('partners.IR', on_delete=models.CASCADE, null=True, blank=True)
    file = models.FileField(upload_to='contracts/%Y/%m/')
    status = models.CharField(max_length=20, choices=[
        ('Draft','Brouillon'),('Sent','Envoyé'),('Signed','Signé'),
        ('Expired','Expiré'),('Cancelled','Annulé')
    ], default='Draft')
    signed_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(Member, on_delete=models.CASCADE)
    key_area = models.ForeignKey(Team, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.get_contract_type_display()} ({self.status})"

    @property
    def file_url(self):
        if not self.file:
            return ""
        url = self.file.url
        if "cloudinary.com" in url and "/image/upload/" in url:
            file_name = getattr(self.file, "name", "")
            if file_name.lower().endswith(".pdf") and not url.lower().endswith(".pdf"):
                return f"{url}.pdf"
        return url


class Payment(models.Model):
    PAYMENT_TYPES = [('EP_Fee','Frais EP'),('Partner_Fee','Frais Partenaire'),('Sponsorship','Sponsoring')]
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES)
    related_ep = models.ForeignKey(EP, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    status = models.CharField(max_length=20, choices=[
        ('Pending','En attente'),('Partial','Partiel'),('Paid','Payé'),('Overdue','En retard'),('Waived','Exonéré')
    ], default='Pending')
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(Member, on_delete=models.CASCADE)
    key_area = models.ForeignKey(Team, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.get_payment_type_display()} - {self.amount} {self.currency} ({self.status})"


class LegalDocument(models.Model):
    """Documents légaux requis pour chaque EP"""
    DOCUMENT_TYPES = [
        ('Passport','Passeport'),('Visa','Visa'),('Insurance','Assurance'),
        ('University_Certificate','Certificat Université'),('Medical','Certificat Médical'),
        ('Parental_Consent','Autorisation Parentale'),('Criminal_Record','Casier Judiciaire'),
    ]
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    ep = models.ForeignKey(EP, on_delete=models.CASCADE, related_name='legal_documents')
    file = models.FileField(upload_to='legal_docs/%Y/%m/')
    status = models.CharField(max_length=20, choices=[
        ('Missing','Manquant'),('Submitted','Soumis'),('Validated','Validé'),('Rejected','Rejeté')
    ], default='Missing')
    submitted_date = models.DateField(null=True, blank=True)
    validated_by = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.get_document_type_display()} for {self.ep.full_name}"

    @property
    def file_url(self):
        if not self.file:
            return ""
        url = self.file.url
        if "cloudinary.com" in url and "/image/upload/" in url:
            file_name = getattr(self.file, "name", "")
            if file_name.lower().endswith(".pdf") and not url.lower().endswith(".pdf"):
                return f"{url}.pdf"
        return url


# ==================== BUSINESS DEVELOPMENT ====================
class Prospect(models.Model):
    """Pistes de nouveaux partenariats (entreprises, universités, autres LCs)"""
    PROSPECT_TYPES = [
        ('Company','Entreprise'),('University','Université'),
        ('NGO','ONG'),('Other_LC','Autre LC AIESEC'),('Other','Autre')
    ]
    name = models.CharField(max_length=200)
    prospect_type = models.CharField(max_length=20, choices=PROSPECT_TYPES)
    country = models.CharField(max_length=100, blank=True)
    contact_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    interest_areas = models.JSONField(default=list, help_text="['IT', 'Marketing', 'Education']")
    status = models.CharField(max_length=20, choices=[
        ('Identified','Identifié'),('Contacted','Contacté'),('Meeting_Scheduled','RDV Pris'),
        ('Proposal_Sent','Proposition Envoyée'),('Negotiation','Négociation'),
        ('Won','Gagné - Converti en Partenaire'),('Lost','Perdu')
    ], default='Identified')
    estimated_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Valeur estimée du partenariat")
    probability = models.PositiveIntegerField(default=0, help_text="Probabilité de conversion %")
    assigned_bd_member = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, related_name='prospects')
    next_action_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    converted_to_partner = models.ForeignKey('partners.IR', on_delete=models.SET_NULL, null=True, blank=True)
    key_area = models.ForeignKey(Team, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class Proposal(models.Model):
    """Propositions commerciales envoyées"""
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='proposals')
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='proposals/%Y/%m/', null=True, blank=True)
    description = models.TextField(blank=True)
    sent_date = models.DateField()
    response_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('Draft','Brouillon'),('Sent','Envoyée'),('Under_Review','En révision'),
        ('Accepted','Acceptée'),('Rejected','Rejetée'),('Negotiating','En négociation')
    ], default='Draft')
    created_by = models.ForeignKey(Member, on_delete=models.CASCADE)

    def __str__(self):
        return self.title


class Task(models.Model):
    PRIORITY_CHOICES = [('Basse','Basse'), ('Moyenne','Moyenne'), ('Haute','Haute'), ('Urgente','Urgente')]
    STATUS_CHOICES = [('À faire','À faire'), ('En cours','En cours'), ('Terminée','Terminée'), ('Annulée','Annulée')]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Moyenne')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='À faire')
    assigned_to = models.ForeignKey(Member, on_delete=models.CASCADE)
    related_ep = models.ForeignKey(EP, on_delete=models.CASCADE, null=True, blank=True)
    related_partner = models.ForeignKey('partners.IR', on_delete=models.CASCADE, null=True, blank=True)
    created_by = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='created_tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Scoping functional Key Area
    key_area = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True)

    # Generic relation to target any system object
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey('content_type', 'object_id')

    def save(self, *args, **kwargs):
        if self.status == 'Terminée' and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class MatchRecord(models.Model):
    """Tracks the matching process between an EP and an Opportunity."""
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        INTERVIEW_SCHEDULED = "interview_scheduled", "Interview Scheduled"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class RejectionReason(models.TextChoices):
        SKILLS_MISMATCH = "skills", "Skills mismatch"
        LANGUAGE = "language", "Language"
        TIMING = "timing", "Timing"
        EP_WITHDREW = "ep_withdrew", "EP withdrew"
        PARTNER_WITHDREW = "partner_withdrew", "Partner withdrew"
        OTHER = "other", "Other"

    ep = models.ForeignKey('EP', on_delete=models.CASCADE, related_name="match_records")
    opportunity = models.ForeignKey('partners.Opportunity', on_delete=models.CASCADE, related_name="match_records")
    proposed_by = models.ForeignKey('members.Member', on_delete=models.SET_NULL, null=True, related_name="proposed_matches")
    proposed_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PROPOSED)
    interview_date = models.DateTimeField(null=True, blank=True)
    partner_feedback = models.TextField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=30, choices=RejectionReason.choices, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    # Dual TL approval (Match Lab)
    approved_by_ir_tl = models.BooleanField(default=False)
    approved_by_product_tl = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["ep", "opportunity"]

    def is_fully_approved(self):
        return self.approved_by_ir_tl and self.approved_by_product_tl

    def clean(self):
        super().clean()
        if self.status == self.Status.REJECTED and not self.rejection_reason:
            from django.core.exceptions import ValidationError
            raise ValidationError({'rejection_reason': 'Rejection reason is required when status is Rejected.'})

    def __str__(self):
        return f"{self.ep.full_name} -> {self.opportunity.title} ({self.get_status_display()})"


# ── Sprint 2 Models ──────────────────────────────────────────────────


class DeliveryChecklist(models.Model):
    """CXP delivery tracking for an EP from Approved → Realized."""
    class VisaStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETE = "complete", "Complete"
        NA = "na", "N/A"

    ep = models.OneToOneField(EP, on_delete=models.CASCADE, related_name="delivery_checklist")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Communication
    expectation_email_sent = models.BooleanField(default=False)
    expectation_email_date = models.DateField(null=True, blank=True)

    # Documents & Admin
    visa_status = models.CharField(max_length=20, choices=VisaStatus.choices, default=VisaStatus.NOT_STARTED)
    insurance_status = models.CharField(max_length=20, choices=VisaStatus.choices, default=VisaStatus.NOT_STARTED)
    contract_status = models.CharField(max_length=20, choices=VisaStatus.choices, default=VisaStatus.NOT_STARTED)

    # Logistics
    flight_booked = models.BooleanField(default=False)
    pickup_arranged = models.BooleanField(default=False)
    first_day_confirmed = models.BooleanField(default=False)

    # Welfare checks
    welfare_check_1 = models.DateField(null=True, blank=True)
    welfare_check_2 = models.DateField(null=True, blank=True)
    welfare_check_3 = models.DateField(null=True, blank=True)

    # Testimonial
    testimonial_collected = models.BooleanField(default=False)
    testimonial_text = models.TextField(null=True, blank=True)

    # Reintegration
    reintegration_done = models.BooleanField(default=False)

    def completion_pct(self):
        """Returns percentage of checklist items completed."""
        fields = [
            self.expectation_email_sent, self.flight_booked, self.pickup_arranged,
            self.first_day_confirmed, self.testimonial_collected, self.reintegration_done,
            self.visa_status == 'complete', self.insurance_status == 'complete',
            self.contract_status == 'complete',
        ]
        done = sum(1 for f in fields if f)
        return round(done / len(fields) * 100)

    def __str__(self):
        return f"CXP Checklist: {self.ep.full_name} ({self.completion_pct()}%)"


class HandoffRecord(models.Model):
    """Product TL → CXP TL handoff record. Required before EP can advance to Approved."""
    ep = models.ForeignKey(EP, on_delete=models.CASCADE, related_name="handoffs")
    from_tl = models.ForeignKey(
        'members.Member', on_delete=models.SET_NULL, null=True,
        related_name="handoffs_sent"
    )
    to_tl = models.ForeignKey(
        'members.Member', on_delete=models.SET_NULL, null=True,
        related_name="handoffs_received"
    )
    handoff_date = models.DateTimeField(auto_now_add=True)
    ep_context = models.TextField(help_text="Context for CXP TL: partner details, EP concerns, expectations")
    documents_status = models.TextField(blank=True, help_text="State of docs at time of handoff")
    accepted = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-handoff_date"]

    def __str__(self):
        return f"Handoff: {self.ep.full_name} ({self.from_tl} → {self.to_tl})"


class Testimonial(models.Model):
    """EP testimonial for brand/content use."""
    class Status(models.TextChoices):
        RAW = "raw", "Raw"
        EDITED = "edited", "Edited"
        PUBLISHED = "published", "Published"

    ep = models.ForeignKey(EP, on_delete=models.SET_NULL, null=True, blank=True, related_name="testimonials")
    ancient_ep_name = models.CharField(max_length=200, blank=True, help_text="For EPs not yet in the system")
    ancient_ep_email = models.EmailField(blank=True)
    content = models.TextField()
    video_url = models.URLField(blank=True)
    photo = models.ImageField(upload_to="testimonials/", null=True, blank=True)
    collected_by = models.ForeignKey('members.Member', on_delete=models.SET_NULL, null=True, related_name="collected_testimonials")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RAW)
    instagram_url = models.URLField(blank=True)
    publish_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def ep_name(self):
        return self.ep.full_name if self.ep else self.ancient_ep_name

    def __str__(self):
        return f"Testimonial: {self.ep_name()} ({self.get_status_display()})"


class ContentCalendar(models.Model):
    """Brand content planning and scheduling."""
    class ContentType(models.TextChoices):
        POST = "post", "Post"
        REEL = "reel", "Reel"
        STORY = "story", "Story"
        CAROUSEL = "carousel", "Carousel"

    class VisualStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        READY = "ready", "Ready"

    class PublishStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Review"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=ContentType.choices, default=ContentType.POST)
    concept = models.TextField(blank=True)
    caption = models.TextField(blank=True)
    visual_status = models.CharField(max_length=20, choices=VisualStatus.choices, default=VisualStatus.NOT_STARTED)
    publish_date = models.DateField(null=True, blank=True)
    responsible = models.ForeignKey('members.Member', on_delete=models.SET_NULL, null=True, blank=True, related_name="content_items")
    status = models.CharField(max_length=20, choices=PublishStatus.choices, default=PublishStatus.DRAFT)
    testimonial = models.ForeignKey(Testimonial, on_delete=models.SET_NULL, null=True, blank=True, related_name="content_items")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["publish_date", "status"]

    def __str__(self):
        return f"[{self.get_type_display()}] {self.title} ({self.get_status_display()})"


class WelfareCheck(models.Model):
    """
    Time-series CXP welfare data per EP.
    Each row is a snapshot at a point in time — enables trend tracking across the exchange lifecycle.
    """
    class Mood(models.IntegerChoices):
        VERY_BAD = 1, "Very Bad 😢"
        BAD = 2, "Bad 😞"
        NEUTRAL = 3, "Neutral 😐"
        GOOD = 4, "Good 😊"
        VERY_GOOD = 5, "Very Good 😄"

    class CheckType(models.TextChoices):
        WEEKLY = "weekly", "Weekly Check-in"
        ARRIVAL = "arrival", "Arrival Check"
        MIDTERM = "midterm", "Mid-term Review"
        COMPLETION = "completion", "Completion Review"
        EMERGENCY = "emergency", "Emergency Flag"

    ep = models.ForeignKey(
        EP,
        on_delete=models.CASCADE,
        related_name="welfare_checks",
    )
    checked_by = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        null=True,
        related_name="welfare_checks_conducted",
    )
    check_type = models.CharField(max_length=20, choices=CheckType.choices, default=CheckType.WEEKLY)
    mood_score = models.IntegerField(choices=Mood.choices, null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    host_issues = models.BooleanField(default=False, help_text="Is there a problem with the host entity?")
    ep_issues = models.BooleanField(default=False, help_text="Is the EP experiencing personal difficulties?")
    needs_intervention = models.BooleanField(default=False, help_text="Flag for immediate CXP escalation")
    checked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-checked_at"]
        verbose_name = "Welfare Check"
        verbose_name_plural = "Welfare Checks"

    def __str__(self):
        return f"{self.ep.full_name} — {self.get_check_type_display()} @ {self.checked_at:%Y-%m-%d}"
