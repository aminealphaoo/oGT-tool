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


    def is_ir_team(self) -> bool:
        return self.team and self.team.key_area == "IR"

    def is_bd_team(self) -> bool:
        return self.team and self.team.key_area == "BD"

    def is_cxp_team(self) -> bool:
        return self.team and self.team.key_area == "AUD"

    def is_product_team(self) -> bool:
        return self.team and self.team.key_area in ("GTE", "GTA")

    def can_view_ep(self, ep) -> bool:
        """Check if this member can view a given EP."""
        if self.is_vp():
            return True
        if self.is_tl() and self.team:
            # TL sees their team's EPs only
            if (ep.assigned_area == self.team or
                    (ep.assigned_to and ep.assigned_to.team == self.team) or
                    (ep.assigned_member and ep.assigned_member.team == self.team)):
                return True
        if ep.assigned_member == self or ep.assigned_to == self:
            return True
        # IR members can read EP profiles (skills/languages), handled in view
        if self.is_ir_team():
            return True
        # BD members can read all EPs for data hygiene
        if self.is_bd_team():
            return True
        # CXP members can see EPs in Approved+ stages
        if self.is_cxp_team():
            CXP_STAGES = ["approved", "all_papers_done", "not_all_papers_done", "do_papers", "realized"]
            return ep.current_stage in CXP_STAGES
        return False

    def can_see_ep_contact(self, ep) -> bool:
        """Check if member can see EP phone/email. IR and BD members cannot."""
        if self.is_vp():
            return True
        if self.is_ir_team() or self.is_bd_team():
            return False
        if self.is_tl() and self.team:
            if (ep.assigned_area == self.team or
                    (ep.assigned_to and ep.assigned_to.team == self.team)):
                return True
        return ep.assigned_member == self or ep.assigned_to == self

    def can_edit_ep(self, ep) -> bool:
        """Check if member can edit a given EP."""
        if self.is_vp():
            return True
        if self.is_tl() and self.team:
            if (ep.assigned_area == self.team or
                    (ep.assigned_to and ep.assigned_to.team == self.team)):
                return True
        # CXP can edit EPs in Approved+ stages only
        if self.is_cxp_team():
            CXP_STAGES = ["approved", "all_papers_done", "not_all_papers_done", "do_papers", "realized"]
            return ep.current_stage in CXP_STAGES
        return ep.assigned_member == self or ep.assigned_to == self

    def can_view_ir(self, ir) -> bool:
        """All members can see IR name and entity. Contact details gated separately."""
        return True

    def can_see_ir_contact(self, ir) -> bool:
        """IR contact details: TL+ and VP can see. Plain members cannot."""
        if self.is_vp() or self.is_tl():
            return True
        return False

    def can_edit_ir(self, ir) -> bool:
        """Only TL of IR team and VP can edit IRs."""
        if self.is_vp():
            return True
        if self.is_tl() and self.is_ir_team():
            return True
        return False

    # ── Scoped querysets ──────────────────────────────────────────────
    def get_visible_eps(self):
        """Return EP queryset scoped to this member's role and key area."""
        from ops.models import EP

        if self.is_vp():
            return EP.objects.all()
        if self.is_tl() and self.team:
            return EP.objects.filter(
                models.Q(assigned_area=self.team) |
                models.Q(assigned_to__team=self.team) |
                models.Q(assigned_member__team=self.team)
            ).distinct()
        # IR members see all EPs for match lab (no contact details)
        if self.is_ir_team():
            return EP.objects.all()
        # BD members see all EPs for data hygiene (no contact details)
        if self.is_bd_team():
            return EP.objects.all()
        # CXP members see only Approved+ EPs
        if self.is_cxp_team():
            CXP_STAGES = ["approved", "all_papers_done", "not_all_papers_done", "do_papers", "realized"]
            return EP.objects.filter(current_stage__in=CXP_STAGES)
        # Default: own EPs only
        return EP.objects.filter(models.Q(assigned_member=self) | models.Q(assigned_to=self)).distinct()

    def get_visible_irs(self):
        """Return IR queryset scoped to this member's role."""
        from partners.models import IR

        return IR.objects.all()

