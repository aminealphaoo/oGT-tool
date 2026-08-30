import csv
import io
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import models as dj_models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import AuditLog, Notification, SiteConfig
from members.models import Member
from partners.models import IR, Opportunity

from .forms import AttachmentForm, EPForm, InteractionForm, ProblemFlagForm, StageAdvanceForm, TaskForm
from .models import EP, Attachment, Interaction, SavedFilter, Task

# ── Stage Prerequisites ────────────────────────────────────────────────
# "hard" = blocks advance, "soft" = warns but allows
# ── Stage Order ──────────────────────────────────────────────────────
# Ordered list of stages — used to validate advancement (no skipping)
STAGE_ORDER = [
    "open", "matched_with_opp", "applied", "accepted",
    "approved", "all_papers_done", "not_all_papers_done",
    "do_papers", "realized",
]

STAGE_ORDER_MAP = {s: i for i, s in enumerate(STAGE_ORDER)}


def _get_next_stage(current_stage):
    """Return the next logical stage, or None if already at the end."""
    idx = STAGE_ORDER_MAP.get(current_stage, -1)
    if idx >= 0 and idx + 1 < len(STAGE_ORDER):
        return STAGE_ORDER[idx + 1]
    return None


def _get_previous_stage(current_stage):
    """Return the previous stage, or None if already at the start."""
    idx = STAGE_ORDER_MAP.get(current_stage, -1)
    if idx > 0:
        return STAGE_ORDER[idx - 1]
    return None


STAGE_PREREQUISITES = {
    "matched_with_opp": {"hard": [], "soft": []},
    "applied": {"hard": ["matched_opportunity"], "soft": ["has_cv"]},
    "accepted": {"hard": [], "soft": ["has_cv"]},
    "approved": {"hard": ["has_attachment"], "soft": []},
    "all_papers_done": {"hard": ["has_attachment"], "soft": []},
    "not_all_papers_done": {"hard": [], "soft": []},
    "do_papers": {"hard": ["has_attachment"], "soft": []},
    "realized": {"hard": ["has_attachment"], "soft": []},
}


def _check_prerequisites(ep, target_stage):
    """Return (ok: bool, missing_hard: list, missing_soft: list)."""
    prereqs = STAGE_PREREQUISITES.get(target_stage, {"hard": [], "soft": []})
    missing_hard = []
    missing_soft = []

    for req in prereqs.get("hard", []):
        if req == "matched_opportunity" and not ep.matched_opportunity:
            missing_hard.append("No opportunity matched")
        if req == "has_attachment" and not ep.attachments.exists():
            missing_hard.append("No attachments uploaded")
        if req == "has_cv" and not ep.attachments.filter(label="cv").exists():
            missing_hard.append("No CV uploaded")

    for req in prereqs.get("soft", []):
        if req == "has_cv" and not ep.attachments.filter(label="cv").exists():
            missing_soft.append("No CV uploaded")
        if req == "matched_opportunity" and not ep.matched_opportunity:
            missing_soft.append("No opportunity matched")
        if req == "has_attachment" and not ep.attachments.exists():
            missing_soft.append("No attachments uploaded")

    ok = len(missing_hard) == 0
    return ok, missing_hard, missing_soft


def _get_prereq_status_for_all_stages(ep):
    """Return a dict {stage: (ok, missing_hard, missing_soft)} for checklist display."""
    stages_in_order = [
        "matched_with_opp", "applied", "accepted", "approved",
        "all_papers_done", "not_all_papers_done", "do_papers", "realized",
    ]
    result = {}
    for s in stages_in_order:
        result[s] = _check_prerequisites(ep, s)
    return result


def _render_ep_detail_process(request, ep):
    """Re-render the process tab for HTMX after stage changes."""
    from .forms import AttachmentForm, InteractionForm, ProblemFlagForm, StageAdvanceForm

    stage_history = ep.stage_history.select_related("changed_by")
    interactions = ep.interactions.select_related("author")
    attachments = ep.attachments.all()

    # Build allowed stages for the dropdown (next + previous for revert)
    allowed_stages = []
    next_stage = _get_next_stage(ep.current_stage)
    prev_stage = _get_previous_stage(ep.current_stage)
    if next_stage:
        allowed_stages.append((next_stage, EP.Stage(next_stage).label))
    if prev_stage:
        allowed_stages.append((prev_stage, EP.Stage(prev_stage).label + " (revert)"))

    prereq_status = _get_prereq_status_for_all_stages(ep)
    prev_history = ep.stage_history.exclude(stage=ep.current_stage).order_by("-changed_at").first()
    previous_stage = prev_history.stage if prev_history else None

    is_vp = request.current_member.is_vp()
    is_tl = request.current_member.is_tl()

    ctx = {
        "ep": ep,
        "stage_history": stage_history,
        "interactions": interactions,
        "attachments": attachments,
        "advance_form": StageAdvanceForm(),
        "problem_form": ProblemFlagForm(),
        "interaction_form": InteractionForm(),
        "problem_flags": EP.ProblemFlag.choices,
        "prereq_status": prereq_status,
        "previous_stage": previous_stage,
        "allowed_stages": allowed_stages,
        "is_vp": is_vp,
        "is_tl": is_tl,
    }
    return render(request, "ops/ep_detail_process.html", ctx)


def _get_stale_ep_ids(eps_qs):
    """Precompute stale EP IDs in one pass — avoids N+1 SiteConfig queries."""
    config = SiteConfig.get()
    now = timezone.now()
    stale_ids = set()
    for ep in eps_qs.only("pk", "current_stage", "last_activity_at"):
        threshold = config.get_threshold(ep.current_stage)
        if (now - ep.last_activity_at).days > threshold:
            stale_ids.add(ep.pk)
    return stale_ids


def _paginate(request, queryset, default_per_page=50):
    """Return page_obj and per_page from request GET params."""
    page = int(request.GET.get("page", 1))
    per_page = int(request.GET.get("per_page", default_per_page))
    per_page = min(max(per_page, 10), 200)
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(page), per_page


def ep_list(request):
    """Filterable EP table with pagination."""
    member = request.current_member
    eps = member.get_visible_eps().select_related("assigned_to", "matched_opportunity__ir")

    # ── Archive filter ────────────────────────────────────────────────
    show_archived = request.GET.get("archived", "") == "1"
    if not show_archived:
        eps = eps.filter(is_archived=False)

    # ── Filters ──────────────────────────────────────────────────────
    track = request.GET.get("track", "")
    stage = request.GET.get("stage", "")
    assigned = request.GET.get("assigned", "")
    problem = request.GET.get("problem", "")
    search = request.GET.get("q", "")
    source = request.GET.get("source", "")

    if track:
        eps = eps.filter(track=track)
    if stage:
        eps = eps.filter(current_stage=stage)
    if assigned:
        eps = eps.filter(assigned_to_id=assigned)
    if problem:
        eps = eps.filter(problem_flag=problem)
    if source:
        eps = eps.filter(source=source)
    if search:
        eps = eps.filter(
            dj_models.Q(full_name__icontains=search)
            | dj_models.Q(email__icontains=search)
            | dj_models.Q(university__icontains=search)
        )

    is_kanban = request.GET.get("view", "") == "kanban"

    # Stale badge — precompute for ALL visible EPs (not just current page)
    all_eps_for_stale = member.get_visible_eps()
    stale_ep_ids = _get_stale_ep_ids(all_eps_for_stale)
    stale_count = len(stale_ep_ids)

    stages_data = None
    if is_kanban:
        stages_data = []
        for s in EP.Stage.choices:
            stages_data.append({
                "val": s[0],
                "label": s[1],
                "eps": [ep for ep in eps if ep.current_stage == s[0]]
            })
        page_obj = None
        per_page = None
    else:
        # Paginate
        page_obj, per_page = _paginate(request, eps)

    from members.models import Member

    context = {
        "eps": page_obj,
        "page_obj": page_obj,
        "per_page": per_page,
        "stale_ep_ids": stale_ep_ids,
        "total_count": eps.count(),
        "tracks": EP.Track.choices,
        "stages": EP.Stage.choices,
        "problem_flags": EP.ProblemFlag.choices,
        "ops_members": Member.objects.filter(role__in=["OPS", "TL"], is_active=True),
        "current_track": track,
        "current_stage": stage,
        "current_assigned": assigned,
        "current_problem": problem,
        "current_source": source,
        "search": search,
        "stale_count": stale_count,
        "show_archived": show_archived,
        "saved_filters": SavedFilter.objects.filter(member=member).order_by("-created_at")[:8],
        "is_kanban": is_kanban,
        "stages_data": stages_data,
    }
    
    if request.headers.get("HX-Request") and not is_kanban:
        return render(request, "ops/partials/ep_table.html", context)
        
    return render(request, "ops/ep_list.html", context)


def ep_detail(request, pk):
    """EP profile: all fields, stage history, interaction log, attachments."""
    ep = get_object_or_404(
        EP.objects.select_related("assigned_to", "matched_opportunity__ir"),
        pk=pk,
    )

    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)

    stage_history = ep.stage_history.select_related("changed_by")
    interactions = ep.interactions.select_related("author")
    attachments = ep.attachments.all()

    advance_form = StageAdvanceForm()
    problem_form = ProblemFlagForm()
    interaction_form = InteractionForm()

    # Build allowed stages (next + previous) for the dropdown
    allowed_stages = []
    next_stage = _get_next_stage(ep.current_stage)
    prev_stage = _get_previous_stage(ep.current_stage)
    if next_stage:
        allowed_stages.append((next_stage, EP.Stage(next_stage).label))
    if prev_stage:
        allowed_stages.append((prev_stage, EP.Stage(prev_stage).label + " (revert)"))

    # Stage prerequisites checklist
    prereq_status = _get_prereq_status_for_all_stages(ep)
    # Previous stage for revert button
    prev_history = ep.stage_history.exclude(stage=ep.current_stage).order_by("-changed_at").first()
    previous_stage = prev_history.stage if prev_history else None

    member = request.current_member
    context = {
        "ep": ep,
        "stage_history": stage_history,
        "interactions": interactions,
        "attachments": attachments,
        "advance_form": advance_form,
        "problem_form": problem_form,
        "interaction_form": interaction_form,
        "problem_flags": EP.ProblemFlag.choices,
        "prereq_status": prereq_status,
        "previous_stage": previous_stage,
        "allowed_stages": allowed_stages,
        "can_see_contact": member.can_see_ep_contact(ep),
        "can_edit_ep": member.can_edit_ep(ep),
    }
    return render(request, "ops/ep_detail.html", context)


def ep_create(request):
    """EP entry form with duplicate detection."""
    if request.method == "POST":
        form = EPForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data.get("phone", "")
            email = form.cleaned_data.get("email", "")

            # Duplicate detection
            dup_q = dj_models.Q()
            if phone:
                dup_q |= dj_models.Q(phone=phone)
            if email:
                dup_q |= dj_models.Q(email=email)

            if dup_q:
                existing = EP.objects.filter(dup_q).distinct()
                if existing.exists():
                    names = ", ".join(
                        f'<a href="/eps/{e.pk}/" target="_blank">{e.full_name}</a>'
                        for e in existing
                    )
                    from django.contrib import messages
                    messages.warning(
                        request,
                        f"⚠️ Possible duplicate: {names} already has this phone/email.",
                    )

            ep = form.save(commit=False)
            ep.last_edited_by = request.current_member
            ep.assigned_to = request.current_member
            ep.assigned_member = request.current_member
            if request.current_member.team:
                ep.assigned_area = request.current_member.team
            ep.save()
            return redirect("ep_detail", pk=ep.pk)
    else:
        form = EPForm()

    return render(request, "ops/ep_form.html", {"form": form, "is_create": True})


def ep_edit(request, pk):
    """Edit EP fields."""
    ep = get_object_or_404(EP, pk=pk)

    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = EPForm(request.POST, instance=ep)
        if form.is_valid():
            ep = form.save(commit=False)
            ep.last_edited_by = request.current_member
            ep.save()
            return redirect("ep_detail", pk=ep.pk)
    else:
        form = EPForm(instance=ep)

    return render(request, "ops/ep_form.html", {"form": form, "ep": ep, "is_create": False})


def ep_advance_stage(request, pk):
    """Advance EP to next stage with prereq validation and order enforcement."""
    ep = get_object_or_404(EP, pk=pk)
    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = StageAdvanceForm(request.POST)
        if form.is_valid():
            target = form.cleaned_data["new_stage"]

            # Stage order validation
            current_idx = STAGE_ORDER_MAP.get(ep.current_stage, -1)
            target_idx = STAGE_ORDER_MAP.get(target, -1)
            is_revert = target_idx < current_idx

            # Forward: only allow advancing to the NEXT stage
            next_stage = _get_next_stage(ep.current_stage)
            if not is_revert and target != next_stage:
                from django.contrib import messages
                label = EP.Stage(next_stage).label if next_stage else "none (already at final stage)"
                messages.error(request, f"Cannot skip stages. Next stage is: {label}.")
                return redirect("ep_detail", pk=ep.pk)

            # Prerequisites check
            ok, missing_hard, missing_soft = _check_prerequisites(ep, target)

            if not ok and not is_revert:
                from django.contrib import messages
                messages.error(request, f"Cannot advance: {'; '.join(missing_hard)}. Fix these first.")
                return redirect("ep_detail", pk=ep.pk)

            if missing_soft and not is_revert:
                from django.contrib import messages
                messages.warning(request, f"Advancing without: {"; ".join(missing_soft)}.")

            if is_revert:
                ep.revert_stage(changed_by=request.current_member, note=form.cleaned_data.get("note", ""))
                from django.contrib import messages
                messages.info(request, f"Reverted to {EP.Stage(target).label}.")
            else:
                ep.advance_stage(new_stage=target, changed_by=request.current_member, note=form.cleaned_data.get("note", ""))
                from django.contrib import messages
                messages.success(request, f"Advanced to {EP.Stage(target).label}.")

    return redirect("ep_detail", pk=ep.pk)
def ep_revert_stage(request, pk):
    """Revert EP to the previous stage."""
    ep = get_object_or_404(EP, pk=pk)
    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        note = request.POST.get("note", "")
        ep.revert_stage(changed_by=request.current_member, note=note)
        from django.contrib import messages
        messages.info(request, f"Reverted to {EP.Stage(ep.current_stage).label}.")

    return redirect("ep_detail", pk=ep.pk)
def ep_archive(request, pk):
    """Soft-delete / archive an EP."""
    ep = get_object_or_404(EP, pk=pk)
    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)

    ep.is_archived = True
    ep.last_activity_at = timezone.now()
    ep.save(update_fields=["is_archived", "last_activity_at"])

    from django.contrib import messages
    messages.info(request, f"📦 {ep.full_name} archived. <a href='/eps/{ep.pk}/unarchive/'>Undo</a>")
    return redirect("ep_list")


def ep_unarchive(request, pk):
    """Restore an archived EP."""
    ep = get_object_or_404(EP, pk=pk)
    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)

    ep.is_archived = False
    ep.last_activity_at = timezone.now()
    ep.save(update_fields=["is_archived", "last_activity_at"])

    from django.contrib import messages
    messages.success(request, f"✅ {ep.full_name} restored.")
    return redirect("ep_detail", pk=ep.pk)


def ep_bulk_reassign(request):
    """Reassign multiple EPs to a new member at once."""
    if request.method != "POST":
        return redirect("ep_list")

    ep_ids = request.POST.getlist("ep_ids")
    new_assignee_id = request.POST.get("new_assignee", "")

    if not ep_ids or not new_assignee_id:
        from django.contrib import messages
        messages.error(request, "Select EPs and a target member.")
        return redirect("ep_list")

    new_member = get_object_or_404(Member, pk=new_assignee_id)
    eps = EP.objects.filter(pk__in=ep_ids)
    count = eps.count()

    for ep in eps:
        ep.assigned_to = new_member
        ep.last_activity_at = timezone.now()
        ep.save(update_fields=["assigned_to", "last_activity_at"])
        Interaction.objects.create(
            ep=ep,
            author=request.current_member,
            note=f"Bulk reassigned to {new_member.name}",
        )

    from django.contrib import messages
    messages.success(request, f"✅ {count} EP(s) reassigned to {new_member.name}.")
    return redirect("ep_list")


def ep_bulk_import(request):
    """Import EPs from a CSV file."""
    import csv
    import io

    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        if not csv_file:
            from django.contrib import messages
            messages.error(request, "Please upload a CSV file.")
            return redirect("ep_bulk_import")

        # Read CSV
        data = csv_file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(data))

        created = 0
        skipped = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            try:
                full_name = (row.get("full_name") or row.get("name") or "").strip()
                if not full_name:
                    skipped += 1
                    continue

                email = (row.get("email") or "").strip()
                phone = (row.get("phone") or "").strip()

                # Skip duplicates
                dup_q = dj_models.Q()
                if phone:
                    dup_q |= dj_models.Q(phone=phone)
                if email:
                    dup_q |= dj_models.Q(email=email)
                if dup_q and EP.objects.filter(dup_q).exists():
                    skipped += 1
                    continue

                EP.objects.create(
                    full_name=full_name,
                    phone=phone,
                    email=email,
                    socials=(row.get("socials") or row.get("whatsapp") or "").strip(),
                    university=(row.get("university") or "").strip(),
                    major=(row.get("major") or "").strip(),
                    year_of_study=(row.get("year_of_study") or row.get("year") or "").strip(),
                    track=(row.get("track") or "GT").strip(),
                    current_stage=(row.get("current_stage") or row.get("stage") or "open").strip(),
                    term=(row.get("term") or "2026-S1").strip(),
                    source="manual",
                    last_edited_by=request.current_member,
                )
                created += 1
            except Exception as exc:
                errors.append(f"Row {row_num}: {exc}")

        from django.contrib import messages
        messages.success(
            request,
            f"✅ {created} EPs created. {skipped} skipped (duplicates/missing name)."
        )
        if errors:
            messages.warning(request, f"⚠️ {len(errors)} errors: {'; '.join(errors[:3])}")

        return redirect("ep_list")

    return render(request, "ops/bulk_import.html", {
        "ops_members": Member.objects.filter(role__in=["OPS", "TL"], is_active=True),
    })


def ep_set_problem(request, pk):
    """Set problem flag on an EP."""
    ep = get_object_or_404(EP, pk=pk)
    if request.method == "POST":
        form = ProblemFlagForm(request.POST)
        if form.is_valid():
            ep.set_problem_flag(
                flag=form.cleaned_data["flag"],
                changed_by=request.current_member,
                note=form.cleaned_data.get("note", ""),
            )
    return redirect("ep_detail", pk=ep.pk)


def ep_add_interaction(request, pk):
    """Log an interaction."""
    ep = get_object_or_404(EP, pk=pk)
    if request.method == "POST":
        form = InteractionForm(request.POST)
        if form.is_valid():
            Interaction.objects.create(
                ep=ep,
                author=request.current_member,
                note=form.cleaned_data["note"],
            )
            # Touch EP activity
            ep.last_activity_at = timezone.now()
            ep.save(update_fields=["last_activity_at"])
    return redirect("ep_detail", pk=ep.pk)


def ep_quick_interaction(request, pk):
    """Quick inline interaction from EP list — redirects back to list."""
    ep = get_object_or_404(EP, pk=pk)
    if request.method == "POST":
        note = request.POST.get("note", "").strip()
        if note:
            Interaction.objects.create(
                ep=ep,
                author=request.current_member,
                note=note,
            )
            ep.last_activity_at = timezone.now()
            ep.save(update_fields=["last_activity_at"])
    return redirect("ep_list")


def ep_update_tl_notes(request, pk):
    """Update TL notes (TL/VP only)."""
    ep = get_object_or_404(EP, pk=pk)
    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)
    if request.method == "POST":
        if request.current_member.is_vp() or request.current_member.is_tl():
            ep.tl_notes = request.POST.get("tl_notes", "")
            ep.last_activity_at = timezone.now()
            ep.save(update_fields=["tl_notes", "last_activity_at"])
    return redirect("ep_detail", pk=ep.pk)


# ── CSV Export ─────────────────────────────────────────────────────────────

def ep_export_csv(request):
    """Export filtered EP list as CSV."""
    import csv
    from django.http import HttpResponse

    member = request.current_member
    eps = member.get_visible_eps().select_related("assigned_to", "matched_opportunity__ir")

    track = request.GET.get("track", "")
    stage = request.GET.get("stage", "")
    if track:
        eps = eps.filter(track=track)
    if stage:
        eps = eps.filter(current_stage=stage)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="eps_export.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Full Name", "Phone", "Email", "University", "Major", "Year",
        "Track", "Stage", "Problem Flag", "Assigned To",
        "IR Entity", "IR Country", "Term", "Source", "Idle Days", "Created"
    ])
    for ep in eps:
        writer.writerow([
            ep.full_name, ep.phone, ep.email, ep.university, ep.major,
            ep.year_of_study, ep.get_track_display(), ep.get_current_stage_display(),
            ep.get_problem_flag_display(),
            ep.assigned_to.name if ep.assigned_to else "",
            ep.matched_opportunity.ir.entity_name if ep.matched_opportunity else "",
            ep.matched_opportunity.ir.country if ep.matched_opportunity else "",
            ep.term, ep.get_source_display(), ep.idle_days,
            ep.created_at.strftime("%Y-%m-%d"),
        ])
    return response


# ── Attachment Upload ──────────────────────────────────────────────────────

def ep_upload_attachment(request, pk):
    """Upload a file attachment to an EP."""
    ep = get_object_or_404(EP, pk=pk)
    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = AttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.ep = ep
            attachment.uploaded_by = request.current_member
            attachment.save()
            ep.last_activity_at = timezone.now()
            ep.save(update_fields=["last_activity_at"])
    return redirect("ep_detail", pk=ep.pk)


# ── Problem Cases ──────────────────────────────────────────────────────

def problem_list(request):
    """Dedicated view for EPs with active problem flags — paginated."""
    member = request.current_member
    eps = member.get_visible_eps().filter(
        problem_flag__in=["fix_ep_problem", "fix_ir_problem"]
    ).select_related("assigned_to", "matched_opportunity__ir")

    # Filters
    track = request.GET.get("track", "")
    flag = request.GET.get("flag", "")
    assigned = request.GET.get("assigned", "")

    if track:
        eps = eps.filter(track=track)
    if flag:
        eps = eps.filter(problem_flag=flag)
    if assigned:
        eps = eps.filter(assigned_to_id=assigned)

    # Paginate
    page_obj, per_page = _paginate(request, eps)
    total_active = eps.count()  # count before pagination

    # Also show recently fixed (last 7 days) for context
    week_ago = timezone.now() - timedelta(days=7)
    recently_fixed = member.get_visible_eps().filter(
        problem_flag="problem_fixed",
        last_activity_at__gte=week_ago,
    ).select_related("assigned_to").order_by("-last_activity_at")[:5]

    context = {
        "eps": page_obj,
        "page_obj": page_obj,
        "per_page": per_page,
        "total_count": page_obj.paginator.count,
        "recently_fixed": recently_fixed,
        "tracks": EP.Track.choices,
        "problem_flags": EP.ProblemFlag.choices,
        "ops_members": Member.objects.filter(role__in=["OPS", "TL"], is_active=True),
        "current_track": track,
        "current_flag": flag,
        "current_assigned": assigned,
        "total_active": total_active,
    }
    return render(request, "ops/problems.html", context)


import math
import re

def _score_ep_opp_match(ep, opp):
    """
    Score an EP-opportunity match. Higher = better fit.
    11-factor scoring using weights from SiteConfig.
    """
    if opp.track != ep.track:
        return 0

    config = SiteConfig.get()
    
    # 1. TRACK match: base +50
    score = 50

    # 2. COMPÉTENCES (Skills)
    ep_skills = [s.strip().lower() for s in (ep.skills or []) if s.strip()]
    opp_skills = [s.strip().lower() for s in (opp.required_skills or []) if s.strip()]
    w_skills = config.get_weight("skills")
    if not ep_skills or not opp_skills:
        score += w_skills / 2  # neutral
    else:
        intersection = len(set(ep_skills) & set(opp_skills))
        max_len = max(len(ep_skills), len(opp_skills))
        score += w_skills * (intersection / max_len)

    # 3. LANGUES (Languages)
    lang_levels = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4, 'C1': 5, 'C2': 6}
    ep_langs = ep.languages or {}
    opp_langs = opp.required_languages or {}
    w_languages = config.get_weight("languages")
    
    if not opp_langs:
        score += w_languages
    else:
        valid_count = 0
        for lang, req_lvl in opp_langs.items():
            ep_lvl = ep_langs.get(lang)
            if ep_lvl and lang_levels.get(ep_lvl, 0) >= lang_levels.get(req_lvl, 0):
                valid_count += 1
        score += w_languages * (valid_count / len(opp_langs))

    # 4. DOMAINE D'ÉTUDES (Study field)
    w_study = config.get_weight("study_field")
    ep_study = (ep.study_field or "").strip().lower()
    opp_study = (opp.required_study_field or "").strip().lower()
    if not ep_study and not opp_study:
        score += 10  # neutral
    elif ep_study == opp_study and ep_study != "":
        score += w_study
    elif ep_study and opp_study:
        # Partial match
        ep_words = set(re.findall(r'\w+', ep_study))
        opp_words = set(re.findall(r'\w+', opp_study))
        if ep_words & opp_words:
            score += w_study / 2
    
    # 5. PAYS PRÉFÉRÉ (Preferred countries)
    w_countries = config.get_weight("preferred_countries")
    pref_countries = [c.strip().lower() for c in (ep.preferred_countries or []) if c.strip()]
    if opp.ir.country.strip().lower() in pref_countries:
        score += w_countries

    # 6. MOTS-CLÉS SÉMANTIQUE (Semantic keywords)
    w_semantic = config.get_weight("semantic")
    # Stopwords standard
    stopwords = {
        'le', 'la', 'les', 'de', 'des', 'un', 'une', 'et', 'en', 'pour', 'qui', 'que',
        'the', 'and', 'for', 'of', 'in', 'to', 'is', 'a', 'with', 'on', 'at', 'dans', 'par'
    }
    
    ep_text = f"{ep.keywords or ''} {ep.study_field or ''} {' '.join(ep.skills or [])}"
    opp_text = f"{opp.keywords or ''} {opp.description or ''} {' '.join(opp.required_skills or [])}"
    
    ep_tokens = set([t for t in re.findall(r'\w+', ep_text.lower()) if t not in stopwords])
    opp_tokens = set([t for t in re.findall(r'\w+', opp_text.lower()) if t not in stopwords])
    
    if not ep_tokens and not opp_tokens:
        score += w_semantic / 2
    else:
        intersection = len(ep_tokens & opp_tokens)
        max_tokens = max(len(ep_tokens), len(opp_tokens))
        if max_tokens > 0:
            score += w_semantic * (intersection / max_tokens)

    # 7. DURÉE (Duration preference)
    w_duration = config.get_weight("duration")
    if ep.duration_preference and opp.duration_months:
        if abs(ep.duration_preference - opp.duration_months) <= 1:
            score += w_duration

    # 8. DISPONIBILITÉ (Availability date)
    w_availability = config.get_weight("availability")
    if ep.availability_date:
        days_diff = (ep.availability_date - timezone.now().date()).days
        if days_diff <= 90:
            score += w_availability
        elif days_diff <= 180:
            score += w_availability / 2

    # 9. IR TIER
    w_tier = config.get_weight("tier")
    tier_scores = {"platinum": w_tier, "gold": w_tier * 0.75, "silver": w_tier * 0.5, "bronze": w_tier * 0.25}
    score += tier_scores.get(opp.ir.tier, w_tier * 0.25)

    # 10. OPEN SLOTS
    w_open_slots = config.get_weight("open_slots")
    open_count = opp.ir.open_opportunities_count
    score += w_open_slots if open_count > 1 else (w_open_slots / 4)

    # 11. TAX DE REJET (Rejection rate)
    w_rejection = config.get_weight("rejection_rate")
    score += w_rejection * opp.ir.rejection_rate

    # 12. TEMPS DE RÉPONSE (Response time)
    w_response = config.get_weight("response_time")
    rt = opp.ir.response_time_days
    if rt is not None:
        if rt < 7:
            score += w_response
        elif rt < 14:
            score += w_response / 2

    return max(int(score), 0)


def matching(request):
    """Main matching hub — shows EP list + IR partners for the selected track."""
    track = request.GET.get("track", "GT")
    ep_id = request.GET.get("ep_id", "")

    member = request.current_member

    # EPs waiting to be matched (open stage, no matched opportunity)
    unmatched_eps = (
        member.get_visible_eps()
        .filter(track=track, is_archived=False)
        .filter(
            dj_models.Q(matched_opportunity__isnull=True)
            | dj_models.Q(current_stage="open")
        )
        .select_related("assigned_to", "matched_opportunity__ir")
        .order_by("-last_activity_at")
    )

    # All open opportunities for the quick match dropdown
    all_open_opps = Opportunity.objects.filter(
        is_open=True,
        ir__status__in=["active", "priority"],
    ).select_related("ir").order_by("ir__entity_name")

    # IR overview: partners with open opps
    ir_with_opps = (
        IR.objects.filter(
            status__in=["active", "priority"],
            opportunities__is_open=True,
        )
        .distinct()
        .prefetch_related("opportunities")
        .order_by("-status", "entity_name")
    )
    ir_data = []
    for ir in ir_with_opps:
        open_opps = ir.opportunities.filter(is_open=True)
        ir_data.append({"ir": ir, "open_opps": open_opps, "opp_count": open_opps.count()})

    # Scored recommendations if an EP is selected
    focused_ep = None
    scored_opps = []
    if ep_id:
        try:
            focused_ep = member.get_visible_eps().get(pk=ep_id)
            opp_pool = Opportunity.objects.filter(
                is_open=True,
                ir__status__in=["active", "priority"],
            ).select_related("ir")
            for opp in opp_pool:
                score = _score_ep_opp_match(focused_ep, opp)
                if score > 0:
                    scored_opps.append({"opp": opp, "ir": opp.ir, "score": score})
            scored_opps.sort(key=lambda x: x["score"], reverse=True)
            scored_opps = scored_opps[:20]  # top 20
        except EP.DoesNotExist:
            focused_ep = None

    context = {
        "current_track": track,
        "tracks": EP.Track.choices,
        "unmatched_eps": unmatched_eps,
        "ep_count": unmatched_eps.count(),
        "ir_data": ir_data,
        "ir_count": len(ir_data),
        "all_open_opps": all_open_opps,
        "focused_ep": focused_ep,
        "scored_opps": scored_opps,
        "ep_id": ep_id,
    }
    return render(request, "ops/matching.html", context)


def intelligent_match(request, ep_id):
    """
    Intelligent matching: EPs waiting for a match, scored against open IR opportunities.
    Group by Country, sort Country -> Partner -> Opportunity.
    """
    ep = get_object_or_404(EP, pk=ep_id)
    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)

    # Get all active open opportunities
    open_opps = Opportunity.objects.filter(
        is_open=True,
        track=ep.track,
        ir__status__in=["active", "priority"]
    ).select_related("ir")

    scored_list = []
    for opp in open_opps:
        score = _score_ep_opp_match(ep, opp)
        if score > 0:
            scored_list.append({
                "opp": opp,
                "score": score,
                "ir": opp.ir,
                "country": opp.ir.country
            })

    # Group by country
    country_groups = {}
    for item in scored_list:
        c = item["country"]
        if c not in country_groups:
            country_groups[c] = []
        country_groups[c].append(item)

    # Calculate country-level score: average * log(count + 1)
    scored_countries = []
    for country, items in country_groups.items():
        avg_score = sum(x["score"] for x in items) / len(items)
        country_score = avg_score * math.log(len(items) + 1)
        
        # Sort items inside country: by score descending
        items.sort(key=lambda x: x["score"], reverse=True)
        
        # Group by partner inside the country
        partner_groups = {}
        for x in items:
            p = x["ir"]
            if p not in partner_groups:
                partner_groups[p] = {"ir": p, "max_score": 0, "opps": []}
            partner_groups[p]["opps"].append(x)
            if x["score"] > partner_groups[p]["max_score"]:
                partner_groups[p]["max_score"] = x["score"]

        # Sort partners by max_score descending
        sorted_partners = list(partner_groups.values())
        sorted_partners.sort(key=lambda x: x["max_score"], reverse=True)

        scored_countries.append({
            "country": country,
            "score": round(country_score, 1),
            "partners": sorted_partners,
            "count": len(items)
        })

    # Sort countries by country score descending
    scored_countries.sort(key=lambda x: x["score"], reverse=True)

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("format") == "json":
        # Return JSON
        data = []
        for sc in scored_countries:
            c_data = {"country": sc["country"], "score": sc["score"], "partners": []}
            for p in sc["partners"]:
                p_data = {"partner_name": p["ir"].entity_name, "opps": []}
                for o in p["opps"]:
                    p_data["opps"].append({
                        "id": o["opp"].pk,
                        "title": o["opp"].title,
                        "score": o["score"]
                    })
                c_data["partners"].append(p_data)
            data.append(c_data)
        return JsonResponse({"ep": ep.full_name, "matches": data})

    context = {
        "ep": ep,
        "scored_countries": scored_countries,
        "tracks": EP.Track.choices,
    }
    return render(request, "ops/matching.html", context)



def matching_match(request):
    """POST: link an EP to an IR opportunity directly from the matching page."""
    if request.method != "POST":
        return redirect("matching")

    ep_id = request.POST.get("ep_id", "")
    opp_id = request.POST.get("opp_id", "")

    ep = get_object_or_404(EP, pk=ep_id)
    opp = get_object_or_404(Opportunity, pk=opp_id)

    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)

    ep.matched_opportunity = opp
    ep.last_activity_at = timezone.now()
    ep.save(update_fields=["matched_opportunity", "last_activity_at"])

    # Log as interaction
    Interaction.objects.create(
        ep=ep,
        author=request.current_member,
        note=f"Matched to {opp.ir.entity_name} — {opp.get_type_display()} ({opp.title or 'untitled'})",
    )

    return redirect(f"/matching/?track={ep.track}")


# ── Saved Filters ────────────────────────────────────────────────────

def save_filter(request):
    """Save current filter params as a named preset."""
    if request.method != "POST":
        return redirect("ep_list")

    name = request.POST.get("name", "").strip()
    if not name:
        from django.contrib import messages
        messages.error(request, "Please provide a name for the filter.")
        return redirect("ep_list")

    # Capture current filter params
    params = {}
    for key in ["track", "stage", "assigned", "problem", "q", "archived"]:
        val = request.POST.get(key, "")
        if val:
            params[key] = val

    from .models import SavedFilter
    SavedFilter.objects.update_or_create(
        member=request.current_member,
        name=name,
        defaults={"query_params": params},
    )

    from django.contrib import messages
    messages.success(request, f"🔖 Filter '{name}' saved.")
    return redirect("ep_list")


def delete_filter(request, filter_id):
    """Delete a saved filter."""
    from .models import SavedFilter
    f = get_object_or_404(SavedFilter, pk=filter_id, member=request.current_member)
    name = f.name
    f.delete()
    from django.contrib import messages
    messages.info(request, f"🗑️ Filter '{name}' deleted.")
    return redirect("ep_list")


# ── Tasks ────────────────────────────────────────────────────────────

def task_list(request):
    """Show all tasks visible to the current member."""
    member = request.current_member
    is_vp = member.is_vp()
    is_tl = member.is_tl()

    if is_vp or is_tl:
        tasks = Task.objects.select_related("assigned_to", "created_by", "related_ep", "related_partner").order_by("-created_at")
    else:
        tasks = Task.objects.filter(assigned_to=member).select_related("assigned_to", "created_by", "related_ep", "related_partner").order_by("-created_at")

    # Filters
    status_f = request.GET.get("status", "")
    priority_f = request.GET.get("priority", "")
    if status_f:
        tasks = tasks.filter(status=status_f)
    if priority_f:
        tasks = tasks.filter(priority=priority_f)

    context = {
        "tasks": tasks,
        "status_choices": Task.STATUS_CHOICES,
        "priority_choices": Task.PRIORITY_CHOICES,
        "current_status": status_f,
        "current_priority": priority_f,
        "form": TaskForm(),
        "members": Member.objects.filter(is_active=True),
        "eps": EP.objects.filter(is_archived=False).order_by("full_name")[:100],
    }
    return render(request, "ops/task_list.html", context)


def task_create(request):
    """Create a new task."""
    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.current_member
            task.save()
            messages.success(request, f"✅ Task '{task.title}' created.")
            return redirect("task_list")
    return redirect("task_list")


def task_update(request, task_id):
    """Update task status or other fields."""
    task = get_object_or_404(Task, pk=task_id)
    member = request.current_member

    # Only assigned member, TL or VP can update
    if task.assigned_to != member and not member.is_vp() and not member.is_tl():
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(request, f"✅ Task '{task.title}' updated.")
    return redirect("task_list")


def task_delete(request, task_id):
    """Delete a task (VP/TL only)."""
    task = get_object_or_404(Task, pk=task_id)
    member = request.current_member
    if not member.is_vp() and not member.is_tl():
        return render(request, "403.html", status=403)
    if request.method == "POST":
        name = task.title
        task.delete()
        messages.info(request, f"🗑️ Task '{name}' deleted.")
    return redirect("task_list")


def task_quick_status(request, task_id):
    """HTMX/AJAX quick status toggle."""
    task = get_object_or_404(Task, pk=task_id)
    member = request.current_member
    if task.assigned_to != member and not member.is_vp() and not member.is_tl():
        return JsonResponse({"error": "Forbidden"}, status=403)
    new_status = request.POST.get("status", task.status)
    task.status = new_status
    task.save(update_fields=["status", "completed_at"])
    return JsonResponse({"status": task.status, "completed_at": str(task.completed_at or "")})


# ── Notifications ──────────────────────────────────────────────────────

def notifications_list(request):
    """JSON or HTML list of notifications for the current user."""
    user = request.user
    base_notifs = Notification.objects.filter(user=user).order_by("-created_at")
    unread_count = base_notifs.filter(is_read=False).count()
    notifs = base_notifs[:30]

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("format") == "json":
        data = [{"id": n.pk, "title": n.title, "message": n.message, "link": n.link, "is_read": n.is_read, "created_at": n.created_at.isoformat()} for n in notifs]
        return JsonResponse({"notifications": data, "unread_count": unread_count})

    context = {"notifications": notifs, "unread_count": unread_count}
    return render(request, "ops/notifications.html", context)


def notification_mark_read(request, notif_id):
    """Mark one notification as read and redirect to its link."""
    notif = get_object_or_404(Notification, pk=notif_id, user=request.user)
    notif.is_read = True
    notif.save(update_fields=["is_read"])
    return redirect(notif.link or "/")


def notification_mark_all_read(request):
    """Mark all notifications as read."""
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect(request.META.get("HTTP_REFERER", "/"))


# ── Audit Log ─────────────────────────────────────────────────────────

def audit_log_view(request):
    """Audit log viewer for VP/TL."""
    member = request.current_member
    if not member.is_vp() and not member.is_tl():
        return render(request, "403.html", status=403)

    logs = AuditLog.objects.select_related("user").order_by("-timestamp")[:200]
    context = {"logs": logs}
    return render(request, "ops/audit_log.html", context)


# ── CSV/Excel Import ───────────────────────────────────────────────────

# ── EXPA Sync ─────────────────────────────────────────────────────────

def ep_expa_import(request):
    """Import EPs from an EXPA CSV export."""
    import csv
    import io

    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        if not csv_file:
            from django.contrib import messages
            messages.error(request, "Please upload an EXPA CSV file.")
            return redirect("ep_bulk_import")

        data = csv_file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(data))

        created = 0
        skipped = 0

        for row in reader:
            # EXPA column names (typical export)
            first_name = (row.get("First Name") or row.get("first_name") or "").strip()
            last_name = (row.get("Last Name") or row.get("last_name") or "").strip()
            full_name = f"{first_name} {last_name}".strip()

            if not full_name:
                continue

            email = (row.get("Email") or row.get("email") or "").strip()
            phone = (row.get("Phone") or row.get("phone") or "").strip()

            # Check duplicate
            dup_q = dj_models.Q()
            if email:
                dup_q |= dj_models.Q(email=email)
            if dup_q and EP.objects.filter(dup_q).exists():
                skipped += 1
                continue

            # Derive track from EXPA product column
            product = (row.get("Product") or row.get("product") or row.get("Programme") or "").lower()
            track = "GT"
            if "teacher" in product or "gte" in product or "teaching" in product:
                track = "GTe"

            EP.objects.create(
                full_name=full_name,
                email=email,
                phone=phone,
                track=track,
                current_stage="open",
                term="2026-S1",
                source="expa_sync",
                last_edited_by=request.current_member,
            )
            created += 1

        from django.contrib import messages
        messages.success(request, f"✅ {created} EPs imported from EXPA. {skipped} skipped (duplicates).")
        return redirect("ep_list")

    return redirect("ep_bulk_import")
