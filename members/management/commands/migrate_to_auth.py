from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from members.models import Member
import string
import random

class Command(BaseCommand):
    help = 'Migrate existing Member instances to auth.User models.'

    def handle(self, *args, **options):
        members = Member.objects.filter(user__isnull=True)
        created_count = 0
        
        for member in members:
            # Generate a simple username (first name + random string if needed)
            base_username = member.name.lower().replace(" ", "")
            if not base_username:
                base_username = f"user_{member.id}"
                
            username = base_username
            suffix = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{suffix}"
                suffix += 1
            
            # Generate a temporary random password
            temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            
            # Create user
            user = User.objects.create_user(
                username=username,
                email=member.email or f"{username}@aiesec.net",
                password=temp_password,
                first_name=member.name[:150]
            )
            
            # If VP, make superuser
            if member.role == Member.Role.VP:
                user.is_staff = True
                user.is_superuser = True
                user.save()
                
            member.user = user
            member.save()
            created_count += 1
            
            self.stdout.write(self.style.SUCCESS(f"Created User '{username}' for Member '{member.name}' with temp password: {temp_password}"))
            
        self.stdout.write(self.style.SUCCESS(f"Successfully migrated {created_count} members to auth.User."))
