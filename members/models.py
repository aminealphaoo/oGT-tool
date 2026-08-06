from django.contrib.auth.models import User
from django.db import models


class Team(models.Model):
    """A team within the LC (e.g. oGT, iGT, oTE, iTE)."""

    name = models.CharField(max_length=100, unique=True)
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
        return self.name

    @property
    def member_count(self):
        return self.members.count()


class Member(models.Model):
    """An LC member — identity is session-based, with optional password auth."""

    class Role(models.TextChoices):
        OPS = "OPS", "OPS Member"
        IR = "IR", "IR Member"
        TL = "TL", "Team Leader"
        VP = "VP", "Vice President"

    name = models.CharField(max_length=150)
    role = models.CharField(max_length=5, choices=Role.choices, default=Role.OPS)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"

    def is_vp(self):
        return self.role == self.Role.VP

    def is_tl(self):
        return self.role == self.Role.TL

    def is_ops(self):
        return self.role == self.Role.OPS

    def is_ir(self):
        return self.role == self.Role.IR

    def can_view_ep(self, ep) -> bool:
        """Check if this member can view a given EP."""
        if self.role == self.Role.VP:
            return True
        if self.role == self.Role.TL and self.team and ep.assigned_to and ep.assigned_to.team == self.team:
            return True
        if ep.assigned_to == self:
            return True
        return False

    def can_view_ir(self, ir) -> bool:
        """Check if this member can view a given IR."""
        if self.role == self.Role.VP:
            return True
        if ir.assigned_to == self:
            return True
        return False

    # ── Scoped querysets ──────────────────────────────────────────────
    def get_visible_eps(self):
        """Return EP queryset scoped to this member's role."""
        from ops.models import EP

        if self.role == self.Role.VP:
            return EP.objects.all()
        if self.role == self.Role.TL and self.team:
            return EP.objects.filter(assigned_to__team=self.team)
        return EP.objects.filter(assigned_to=self)

    def get_visible_irs(self):
        """Return IR queryset scoped to this member's role."""
        from partners.models import IR

        if self.role == self.Role.VP:
            return IR.objects.all()
        return IR.objects.filter(assigned_to=self)
