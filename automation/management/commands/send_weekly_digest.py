from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from members.models import Member
from ops.models import EP, MatchRecord, Task
from partners.models import Opportunity
from django.core.mail import send_mail
from django.conf import settings

class Command(BaseCommand):
    help = 'Send weekly digest emails to members summarizing their portfolio'

    def handle(self, *args, **options):
        members = Member.objects.filter(is_active=True).exclude(email="")
        
        sent_count = 0
        for member in members:
            # Gather EP stats
            my_eps = EP.objects.filter(assigned_to=member, is_archived=False)
            total_eps = my_eps.count()
            cold_eps = my_eps.filter(last_activity_at__lt=timezone.now() - timedelta(days=7)).count()
            
            # Gather match stats (recent matches proposed for or by this member's EPs)
            recent_matches = MatchRecord.objects.filter(
                ep__in=my_eps,
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count()

            # Gather ghost opps if they are an IR member
            ghost_opps_msg = ""
            if member.is_ir_team() or member.is_vp():
                ghost_opps = Opportunity.objects.filter(
                    ir__assigned_to=member,
                    is_open=True,
                    match_records__isnull=True,
                    created_at__lt=timezone.now() - timedelta(days=10)
                ).count()
                if ghost_opps > 0:
                    ghost_opps_msg = f"- 👻 Ghost Opportunities (No Matches >10 days): {ghost_opps}\n"

            # Gather pending tasks
            pending_tasks = Task.objects.filter(
                assigned_to=member,
                status="pending",
                due_date__lte=timezone.now() + timedelta(days=7)
            ).count()
            
            # Compose email
            subject = f"Weekly Digest: Your oGT Portfolio ({timezone.now().strftime('%b %d')})"
            body = f"""Hi {member.name},

Here is your weekly oGT digest:

- 👤 Total Active EPs: {total_eps}
- 🧊 Cold EPs (No activity >7 days): {cold_eps}
- 🔗 New Matches Proposed (Last 7 days): {recent_matches}
{ghost_opps_msg}
- 📋 Upcoming / Overdue Tasks: {pending_tasks}

Log in to the tool to follow up on your cold EPs and pending tasks!
"""
            
            # In a real app we would use an EmailTemplate and send HTML.
            # We'll use simple text for the command.
            try:
                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL or 'noreply@aiesec.org',
                    [member.email],
                    fail_silently=False,
                )
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f"Sent digest to {member.email}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to send to {member.email}: {e}"))

        self.stdout.write(self.style.SUCCESS(f'Successfully sent {sent_count} weekly digests.'))
