from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Member, Team

@login_required
def member_list(request):
    """List all LC members."""
    # Anyone authenticated can view members list, but only VP has action capabilities.
    members = Member.objects.select_related('user', 'team').all()
    teams = Team.objects.all()
    context = {
        "members": members,
        "teams": teams,
        "roles": Member.Role.choices,
        "is_vp": request.current_member.is_vp() if request.current_member else False,
    }
    return render(request, "members/members_list.html", context)

@login_required
def member_create(request):
    """Register a new member (VP only)."""
    if not request.current_member or not request.current_member.is_vp():
        return render(request, "403.html", status=403)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        role = request.POST.get("role", "OPS")
        team_id = request.POST.get("team", "")
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()

        if not name or not username or not password:
            messages.error(request, "Name, Username, and Password are required.")
            return redirect("member_list")

        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
            return redirect("member_list")

        # Create Django auth user
        user = User.objects.create(
            username=username,
            password=make_password(password),
            email=email,
            first_name=name
        )

        # Create AIESEC LC Member profile
        team = get_object_or_404(Team, pk=team_id) if team_id else None
        Member.objects.create(
            user=user,
            name=name,
            role=role,
            team=team,
            email=email,
            phone=phone,
            is_active=True
        )

        messages.success(request, f"✅ Member '{name}' registered successfully.")
    return redirect("member_list")

@login_required
def member_edit(request, pk):
    """Edit an existing member (VP only)."""
    if not request.current_member or not request.current_member.is_vp():
        return render(request, "403.html", status=403)

    member_to_edit = get_object_or_404(Member, pk=pk)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        role = request.POST.get("role", member_to_edit.role)
        team_id = request.POST.get("team", "")
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "").strip()
        is_active = request.POST.get("is_active") == "on"

        if not name:
            messages.error(request, "Name cannot be empty.")
            return redirect("member_list")

        # Update member fields
        member_to_edit.name = name
        member_to_edit.role = role
        member_to_edit.team = get_object_or_404(Team, pk=team_id) if team_id else None
        member_to_edit.email = email
        member_to_edit.phone = phone
        member_to_edit.is_active = is_active
        member_to_edit.save()

        # Update Django User fields
        django_user = member_to_edit.user
        if django_user:
            django_user.email = email
            django_user.first_name = name
            if password:
                django_user.password = make_password(password)
            django_user.is_active = is_active
            django_user.save()

        messages.success(request, f"✅ Member '{name}' updated successfully.")
    return redirect("member_list")
