"""
Tests for EP/IR models and views — Phase 4.
Run: python manage.py test ops partners dashboard
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import SiteConfig
from members.models import Member, Team
from ops.models import EP, StageHistory, Interaction, Attachment


class EPModelTests(TestCase):
    """Core EP model behavior."""

    def setUp(self):
        self.member = Member.objects.create(name="Test OPS", role="OPS")
        self.ep = EP.objects.create(
            full_name="Ahmed Ben Salah",
            phone="+21620123456",
            email="ahmed@test.com",
            track="GT",
            current_stage="open",
            assigned_to=self.member,
        )

    def test_ep_creation(self):
        self.assertEqual(self.ep.full_name, "Ahmed Ben Salah")
        self.assertEqual(self.ep.current_stage, "open")
        self.assertEqual(self.ep.track, "GT")
        self.assertEqual(str(self.ep), "Ahmed Ben Salah (Global Talent — Open)")

    def test_advance_stage(self):
        self.ep.advance_stage("matched_with_opp", changed_by=self.member, note="Found match")
        self.ep.refresh_from_db()
        self.assertEqual(self.ep.current_stage, "matched_with_opp")

        # Check history was logged
        history = StageHistory.objects.filter(ep=self.ep)
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().stage, "matched_with_opp")
        self.assertEqual(history.first().previous_stage, "open")

    def test_set_problem_flag(self):
        self.ep.set_problem_flag("fix_ep_problem", changed_by=self.member, note="Missing docs")
        self.ep.refresh_from_db()
        self.assertEqual(self.ep.problem_flag, "fix_ep_problem")

    def test_stale_detection(self):
        config = SiteConfig.get()
        self.ep.current_stage = "open"
        self.ep.last_activity_at = timezone.now() - timedelta(days=20)
        self.ep.save()
        # Threshold for "open" is 14 days, so 20 > 14 → stale
        self.assertTrue(self.ep.is_stale)

        self.ep.last_activity_at = timezone.now() - timedelta(days=5)
        self.ep.save()
        self.assertFalse(self.ep.is_stale)

    def test_idle_days(self):
        self.ep.last_activity_at = timezone.now() - timedelta(days=3)
        self.ep.save()
        self.assertEqual(self.ep.idle_days, 3)


class StageHistoryTests(TestCase):
    """Audit trail for EP stage changes."""

    def setUp(self):
        self.member = Member.objects.create(name="Test OPS", role="OPS")
        self.ep = EP.objects.create(
            full_name="Sarra Trabelsi",
            track="GTe",
            assigned_to=self.member,
        )

    def test_history_creation(self):
        self.ep.advance_stage("matched_with_opp", changed_by=self.member)
        self.ep.advance_stage("applied", changed_by=self.member)

        history = StageHistory.objects.filter(ep=self.ep).order_by("changed_at")
        self.assertEqual(history.count(), 2)
        self.assertEqual(history[0].stage, "matched_with_opp")
        self.assertEqual(history[1].stage, "applied")


class InteractionTests(TestCase):
    """Interaction logging."""

    def setUp(self):
        self.member = Member.objects.create(name="Test OPS", role="OPS")
        self.ep = EP.objects.create(
            full_name="Fatma Ben Ali",
            phone="+21622123456",
            assigned_to=self.member,
        )

    def test_create_interaction(self):
        interaction = Interaction.objects.create(
            ep=self.ep,
            author=self.member,
            note="WhatsApp: sent documents",
        )
        self.assertEqual(self.ep.interactions.count(), 1)
        self.assertEqual(interaction.note, "WhatsApp: sent documents")


class MemberModelTests(TestCase):
    """Identity/access model behavior."""

    def setUp(self):
        self.team = Team.objects.create(name="oGT")
        self.vp = Member.objects.create(name="VP", role="VP")
        self.tl = Member.objects.create(name="TL", role="TL", team=self.team)
        self.ops = Member.objects.create(name="OPS", role="OPS", team=self.team)
        self.other = Member.objects.create(name="Other OPS", role="OPS")

    def test_vp_sees_all(self):
        ep = EP.objects.create(full_name="Test", assigned_to=self.ops)
        self.assertTrue(self.vp.can_view_ep(ep))

    def test_tl_sees_team(self):
        ep = EP.objects.create(full_name="Test", assigned_to=self.ops)
        self.assertTrue(self.tl.can_view_ep(ep))

    def test_tl_doesnt_see_other_team(self):
        ep = EP.objects.create(full_name="Test", assigned_to=self.other)
        self.assertFalse(self.tl.can_view_ep(ep))

    def test_ops_sees_own(self):
        ep = EP.objects.create(full_name="Test", assigned_to=self.ops)
        self.assertTrue(self.ops.can_view_ep(ep))

    def test_ops_doesnt_see_others(self):
        ep = EP.objects.create(full_name="Test", assigned_to=self.other)
        self.assertFalse(self.ops.can_view_ep(ep))


class ViewTests(TestCase):
    """Basic view smoke tests with session-based identity."""

    def setUp(self):
        SiteConfig.get_or_create(pk=1)
        self.vp = Member.objects.create(name="VP", role="VP")
        self.ops = Member.objects.create(name="OPS", role="OPS")
        EP.objects.create(full_name="Test EP", phone="+21620123456", assigned_to=self.ops)

    def _login_as(self, member):
        session = self.client.session
        session["current_member_id"] = member.pk
        session.save()

    def test_dashboard_loads(self):
        self._login_as(self.vp)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_ep_list_loads(self):
        self._login_as(self.vp)
        response = self.client.get("/eps/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test EP")

    def test_ep_list_needs_identity(self):
        response = self.client.get("/eps/")
        self.assertEqual(response.status_code, 302)  # redirects to picker

    def test_ep_detail_loads(self):
        self._login_as(self.vp)
        ep = EP.objects.first()
        response = self.client.get(f"/eps/{ep.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test EP")

    def test_ir_list_loads(self):
        self._login_as(self.vp)
        response = self.client.get("/irs/")
        self.assertEqual(response.status_code, 200)

    def test_problems_loads(self):
        self._login_as(self.vp)
        response = self.client.get("/problems/")
        self.assertEqual(response.status_code, 200)

    def test_matching_loads(self):
        self._login_as(self.vp)
        response = self.client.get("/matching/")
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_loads(self):
        self._login_as(self.vp)
        response = self.client.get("/dashboard/leaderboard/")
        self.assertEqual(response.status_code, 200)

    def test_ep_create(self):
        self._login_as(self.vp)
        response = self.client.post("/eps/new/", {
            "full_name": "New EP",
            "phone": "+21699999999",
            "track": "GT",
            "current_stage": "open",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EP.objects.count(), 2)
        self.assertEqual(EP.objects.last().full_name, "New EP")

    def test_csv_export(self):
        self._login_as(self.vp)
        response = self.client.get("/eps/export/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
