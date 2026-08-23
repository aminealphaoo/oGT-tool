from django.contrib.auth.models import User
from django.db import models


class Team(models.Model):
    """A functional key area/pole within the LC."""

    KEY_AREA_CHOICES = [
        ('BD', 'BRAND&DATA'),
        ('GTE', 'Product GTe'),
        ('GTA', 'Product GTa'),
        ('IR', 'IR&Partneships'),
        ('AUD', 'AUDIT&CXP'),
    ]
    name = models.CharField(max_length=100, unique=True)
    key_area = models.CharField(max_length=4, choices=KEY_AREA_CHOICES, unique=True, null=True, blank=True)
    description = models.TextField(blank=True)
    tl = models.OneToOneField(
        "Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_team",
        help_text="Team Leader for this team",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_key_area_display()})"

    @property
    def member_count(self):
        return self.members.count()


class Member(models.Model):
    """An LC member — identity is session-based, with optional password auth."""

    class Role(models.TextChoices):
        MEMBER = "MEM", "Member"
        TL = "TL", "Team Leader"
        VP = "VP", "Vice President"

    name = models.CharField(max_length=150)
    role = models.CharField(max_length=5, choices=Role.choices, default=Role.MEMBER)
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    phone = models.CharField(max_length=30, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name="member_profile")
    is_active = models.BooleanField(default=True, help_text="Inactive members hidden from picker")

    can_cross_area = models.BooleanField(default=False, help_text="VP only - has transversal vision across key areas")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"

    def is_vp(self):
        return self.role == self.Role.VP or self.can_cross_area

    def is_tl(self):
        return self.role == self.Role.TL

    def is_ops(self):
        return self.role == self.Role.MEMBER

    def is_ir(self):
        return self.role == self.Role.MEMBER


    def can_view_ep(self, ep) -> bool:
        """Check if this member can view a given EP."""
        if self.is_vp():
            return True
        if self.is_tl() and self.team and ep.assigned_area == self.team:
            return True
        if ep.assigned_member == self or ep.assigned_to == self:
            return True
        return False

    def can_view_ir(self, ir) -> bool:
        """Check if this member can view a given IR."""
        if self.is_vp():
            return True
        if ir.assigned_to == self:
            return True
        return False

    # ── Scoped querysets ──────────────────────────────────────────────
    def get_visible_eps(self):
        """Return EP queryset scoped to this member's role and key area."""
        from ops.models import EP

        if self.is_vp():
            return EP.objects.all()
        if self.is_tl() and self.team:
            return EP.objects.filter(assigned_area=self.team)
        return EP.objects.filter(assigned_member=self)

    def get_visible_irs(self):
        """Return IR queryset scoped to this member's role."""
        from partners.models import IR

        if self.is_vp():
            return IR.objects.all()
        return IR.objects.filter(assigned_to=self)

