from django.conf import settings
from django.shortcuts import redirect, render

from .models import Member


def identity_picker(request):
    """Identity picker — click to select, enter password if required."""
    members = Member.objects.filter(is_active=True).select_related("team")

    if request.method == "POST":
        member_id = request.POST.get("member_id")
        password = request.POST.get("password", "")
        try:
            member = Member.objects.get(pk=member_id, is_active=True)

            # Check password if member has one
            if member.has_password and not member.check_password(password):
                ops_members = members.filter(role=Member.Role.OPS)
                ir_members = members.filter(role=Member.Role.IR)
                tl_members = members.filter(role=Member.Role.TL)
                vp_members = members.filter(role=Member.Role.VP)
                return render(
                    request,
                    "members/picker.html",
                    {
                        "ops_members": ops_members,
                        "ir_members": ir_members,
                        "tl_members": tl_members,
                        "vp_members": vp_members,
                        "current_member": getattr(request, "current_member", None),
                        "error": f"Wrong password for {member.name}.",
                        "failed_member_id": member.pk,
                    },
                    status=403,
                )

            request.session["identity_member_id"] = member.pk
            request.session["identity_member_name"] = member.name
            request.session["identity_member_role"] = member.role
            next_url = request.GET.get("next", "/")
            return redirect(next_url)
        except Member.DoesNotExist:
            pass

    # Group members by role
    ops_members = members.filter(role=Member.Role.OPS)
    ir_members = members.filter(role=Member.Role.IR)
    tl_members = members.filter(role=Member.Role.TL)
    vp_members = members.filter(role=Member.Role.VP)

    return render(
        request,
        "members/picker.html",
        {
            "ops_members": ops_members,
            "ir_members": ir_members,
            "tl_members": tl_members,
            "vp_members": vp_members,
            "current_member": getattr(request, "current_member", None),
        },
    )


def identity_clear(request):
    """Log out (clear session identity)."""
    request.session.pop("identity_member_id", None)
    request.session.pop("identity_member_name", None)
    request.session.pop("identity_member_role", None)
    return redirect("identity_picker")
