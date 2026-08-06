from datetime import timedelta

from django.core.paginator import Paginator
from django.db import models as dj_models
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import SiteConfig
from members.models import Member
from partners.models import IR, Opportunity

from .forms import AttachmentForm, EPForm, InteractionForm, ProblemFlagForm, StageAdvanceForm
from .models import EP, Attachment, Interaction, SavedFilter

# ── Stage Prerequisites ────────────────────────────────────────────────
# "hard" = blocks advance, "soft" = warns but allows
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

    # Stage prerequisites checklist
    prereq_status = _get_prereq_status_for_all_stages(ep)
    # Previous stage for revert button
    prev_history = ep.stage_history.exclude(stage=ep.current_stage).order_by("-changed_at").first()
    previous_stage = prev_history.stage if prev_history else None

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
    """Advance EP to next stage with prereq validation."""
    ep = get_object_or_404(EP, pk=pk)
    if request.method == "POST":
        form = StageAdvanceForm(request.POST)
        if form.is_valid():
            target = form.cleaned_data["new_stage"]

            # Check prerequisites
            ok, missing_hard, missing_soft = _check_prerequisites(ep, target)

            if not ok:
                from django.contrib import messages
                messages.error(
                    request,
                    f"❌ Cannot advance: {'; '.join(missing_hard)}. Fix these first."
                )
                return redirect("ep_detail", pk=ep.pk)

            if missing_soft:
                from django.contrib import messages
                messages.warning(
                    request,
                    f"⚠️ Advancing without: {'; '.join(missing_soft)}."
                )

            ep.advance_stage(
                new_stage=target,
                changed_by=request.current_member,
                note=form.cleaned_data.get("note", ""),
            )
    return redirect("ep_detail", pk=ep.pk)


def ep_revert_stage(request, pk):
    """Revert EP to the previous stage."""
    ep = get_object_or_404(EP, pk=pk)
    if not request.current_member.can_view_ep(ep):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        note = request.POST.get("note", "")
        ep.revert_stage(changed_by=request.current_member, note=note)

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


def _score_ep_opp_match(ep, opp):
    """
    Score an EP-opportunity match. Higher = better fit.

    Factors:
    - Track match: +50 (must match, otherwise 0 total)
    - IR Tier:     Platinum=40, Gold=30, Silver=20, Bronze=10
    - Open slots:  +20 if opp.ir has > 1 open opp (capacity), else +5
    - Rejection:   -1 per % rejection rate of the IR
    - Response:    +10 if response_time_days < 7, +5 if < 14, else 0
    """
    if opp.track != ep.track:
        return 0

    score = 50  # Base track match

    # IR Tier bonus
    tier_scores = {"platinum": 40, "gold": 30, "silver": 20, "bronze": 10}
    score += tier_scores.get(opp.ir.tier, 10)

    # Slot / capacity bonus
    open_count = opp.ir.open_opportunities_count
    score += 20 if open_count > 1 else 5

    # Penalize high rejection rate
    score -= int(opp.ir.rejection_rate)

    # Response time bonus
    rt = opp.ir.response_time_days
    if rt is not None:
        if rt < 7:
            score += 10
        elif rt < 14:
            score += 5

    return max(score, 0)


def matching(request):
    """Intelligent matching: EPs waiting for a match, scored against open IR opportunities."""
    member = request.current_member

    track = request.GET.get("track", "GT")
    ep_id = request.GET.get("ep_id", "")  # Optional: focus on a specific EP

    # EPs that need matching (open stage without an opportunity, or at matched_with_opp)
    matchable_stages = ["open", "matched_with_opp"]
    unmatched_eps = member.get_visible_eps().filter(
        current_stage__in=matchable_stages,
        track=track,
    ).select_related("assigned_to", "matched_opportunity__ir")

    # IRs with open opportunities matching the track
    irs_with_open = IR.objects.filter(
        opportunities__is_open=True,
        opportunities__track=track,
        status__in=["active", "priority"],
    ).prefetch_related("opportunities").distinct()

    # Build all open opps
    all_open_opps = []
    for ir in irs_with_open:
        for opp in ir.opportunities.filter(is_open=True, track=track):
            all_open_opps.append(opp)

    # If an EP is focused, compute scored suggestions for it
    focused_ep = None
    scored_opps = []
    if ep_id:
        try:
            focused_ep = unmatched_eps.get(pk=ep_id)
            for opp in all_open_opps:
                s = _score_ep_opp_match(focused_ep, opp)
                if s > 0:
                    scored_opps.append({"opp": opp, "score": s, "ir": opp.ir})
            scored_opps.sort(key=lambda x: x["score"], reverse=True)
        except EP.DoesNotExist:
            pass

    # Build IR data summary for left panel
    ir_data = []
    for ir in irs_with_open:
        open_opps = list(ir.opportunities.filter(is_open=True, track=track))
        ir_data.append({
            "ir": ir,
            "open_opps": open_opps,
            "opp_count": len(open_opps),
        })
    # Sort IRs: priority first, then by tier
    tier_order = {"platinum": 0, "gold": 1, "silver": 2, "bronze": 3}
    ir_data.sort(key=lambda x: (x["ir"].status != "priority", tier_order.get(x["ir"].tier, 9)))

    context = {
        "unmatched_eps": unmatched_eps,
        "ir_data": ir_data,
        "all_open_opps": all_open_opps,
        "tracks": EP.Track.choices,
        "current_track": track,
        "ep_count": unmatched_eps.count(),
        "ir_count": len(ir_data),
        "focused_ep": focused_ep,
        "scored_opps": scored_opps,
        "ep_id": ep_id,
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
