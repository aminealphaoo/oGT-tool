from django.core.paginator import Paginator
from django.db import models as dj_models
from django.shortcuts import get_object_or_404, redirect, render

from members.models import Member

from .forms import IRForm, OpportunityForm
from .models import IR, Opportunity


def ir_list(request):
    """Filterable IR table with pagination."""
    member = request.current_member
    irs = member.get_visible_irs().prefetch_related("opportunities")

    # ── Filters ──────────────────────────────────────────────────────
    country = request.GET.get("country", "")
    opp_type = request.GET.get("opp_type", "")
    has_open = request.GET.get("has_open", "")
    assigned = request.GET.get("assigned", "")
    search = request.GET.get("q", "")

    if country:
        irs = irs.filter(country__icontains=country)
    if has_open == "yes":
        irs = irs.filter(opportunities__is_open=True).distinct()
    if assigned:
        irs = irs.filter(assigned_to_id=assigned)
    if search:
        irs = irs.filter(
            dj_models.Q(entity_name__icontains=search)
            | dj_models.Q(country__icontains=search)
            | dj_models.Q(vp_contact__icontains=search)
        )

    # Paginate
    page = int(request.GET.get("page", 1))
    per_page = int(request.GET.get("per_page", 50))
    per_page = min(max(per_page, 10), 200)
    paginator = Paginator(irs, per_page)
    page_obj = paginator.get_page(page)

    context = {
        "irs": page_obj,
        "page_obj": page_obj,
        "per_page": per_page,
        "total_count": paginator.count,
        "countries": IR.objects.values_list("country", flat=True).distinct().order_by("country"),
        "opp_types": Opportunity.OppType.choices,
        "ir_members": Member.objects.filter(role="IR", is_active=True),
        "current_country": country,
        "current_has_open": has_open,
        "current_assigned": assigned,
        "search": search,
    }
    return render(request, "partners/ir_list.html", context)


def ir_detail(request, pk):
    """IR profile: opportunities, links, performance stats."""
    ir = get_object_or_404(
        IR.objects.prefetch_related("opportunities"),
        pk=pk,
    )

    if not request.current_member.can_view_ir(ir):
        return render(request, "403.html", status=403)

    opportunities = ir.opportunities.all()
    matched_eps = (
        ir.opportunities.filter(matched_eps__isnull=False)
        .values_list("matched_eps", flat=True)
    )

    from ops.models import EP

    eps_linked = EP.objects.filter(
        matched_opportunity__ir=ir
    ).select_related("assigned_to", "matched_opportunity")

    opp_form = OpportunityForm(initial={"ir": ir})

    context = {
        "ir": ir,
        "opportunities": opportunities,
        "eps_linked": eps_linked,
        "opp_form": opp_form,
        "approved_count": ir.approved_count,
        "realized_count": ir.realized_count,
        "rejection_rate": ir.rejection_rate,
        "total_matched": ir.total_matched,
        "response_time_days": ir.response_time_days,
    }
    return render(request, "partners/ir_detail.html", context)


def ir_create(request):
    """IR entry form."""
    if request.method == "POST":
        form = IRForm(request.POST)
        if form.is_valid():
            ir = form.save(commit=False)
            ir.last_edited_by = request.current_member
            ir.save()
            return redirect("ir_detail", pk=ir.pk)
    else:
        form = IRForm()

    return render(request, "partners/ir_form.html", {"form": form, "is_create": True})


def ir_edit(request, pk):
    """Edit IR fields."""
    ir = get_object_or_404(IR, pk=pk)

    if not request.current_member.can_view_ir(ir):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = IRForm(request.POST, instance=ir)
        if form.is_valid():
            ir = form.save(commit=False)
            ir.last_edited_by = request.current_member
            ir.save()
            return redirect("ir_detail", pk=ir.pk)
    else:
        form = IRForm(instance=ir)

    return render(request, "partners/ir_form.html", {"form": form, "ir": ir, "is_create": False})


def ir_add_opportunity(request, pk):
    """Add an opportunity to an IR."""
    ir = get_object_or_404(IR, pk=pk)
    if request.method == "POST":
        form = OpportunityForm(request.POST)
        if form.is_valid():
            opp = form.save(commit=False)
            opp.ir = ir
            opp.save()
    return redirect("ir_detail", pk=ir.pk)


def ir_export_csv(request):
    """Export filtered IR list as CSV."""
    import csv
    from django.http import HttpResponse

    member = request.current_member
    irs = member.get_visible_irs().prefetch_related("opportunities")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="irs_export.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Entity Name", "Country", "VP Contact", "Assigned To",
        "Open Opps", "Total Matched", "Realized", "Approved+",
        "Rejection %", "Response Time (days)"
    ])
    for ir in irs:
        writer.writerow([
            ir.entity_name, ir.country, ir.vp_contact,
            ir.assigned_to.name if ir.assigned_to else "",
            ir.open_opportunities_count, ir.total_matched,
            ir.realized_count, ir.approved_count,
            ir.rejection_rate,
            ir.response_time_days if ir.response_time_days else "",
        ])
    return response


# ── Opportunity CRUD (from IR detail UI) ────────────────────────────

def opp_edit(request, pk):
    """Edit an opportunity inline."""
    opp = get_object_or_404(Opportunity, pk=pk)
    if request.method == "POST":
        form = OpportunityForm(request.POST, instance=opp)
        if form.is_valid():
            form.save()
    return redirect("ir_detail", pk=opp.ir.pk)


def opp_toggle(request, pk):
    """Toggle an opportunity open/closed."""
    opp = get_object_or_404(Opportunity, pk=pk)
    opp.is_open = not opp.is_open
    opp.save(update_fields=["is_open"])
    return redirect("ir_detail", pk=opp.ir.pk)


def opp_delete(request, pk):
    """Delete an opportunity (with POST for safety)."""
    opp = get_object_or_404(Opportunity, pk=pk)
    ir_pk = opp.ir.pk
    if request.method == "POST":
        opp.delete()
    return redirect("ir_detail", pk=ir_pk)
