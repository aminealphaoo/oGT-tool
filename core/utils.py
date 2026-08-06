"""
core/utils.py — Date range utilities for the oGT Tool dashboard.
Centralises date parsing logic used across dashboard, leaderboard, workload & compare views.
"""
from datetime import date, timedelta

from django.utils import timezone


PRESETS = {
    "week": 7,
    "month": 30,
    "quarter": 90,
    "term": 180,
    "year": 365,
}


def parse_date_range(request):
    """
    Parse date_from / date_to from request.GET.

    Supports:
      - ?preset=week|month|quarter|term|year  → rolling window from today
      - ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD  → explicit range
      - no params → all-time (returns None, None)

    Returns:
      (date_from: date | None, date_to: date | None, preset: str)
    """
    preset = request.GET.get("preset", "all")
    now = timezone.now().date()

    if preset in PRESETS:
        return now - timedelta(days=PRESETS[preset]), now, preset

    if preset == "all":
        raw_from = request.GET.get("date_from", "")
        raw_to = request.GET.get("date_to", "")
        try:
            date_from = date.fromisoformat(raw_from) if raw_from else None
        except ValueError:
            date_from = None
        try:
            date_to = date.fromisoformat(raw_to) if raw_to else None
        except ValueError:
            date_to = None
        return date_from, date_to, "custom" if (date_from or date_to) else "all"

    return None, None, "all"


def apply_date_filter(queryset, date_from, date_to, field="last_activity_at"):
    """
    Apply an optional date range filter to a queryset on a DateTimeField.
    """
    if date_from:
        queryset = queryset.filter(**{f"{field}__date__gte": date_from})
    if date_to:
        queryset = queryset.filter(**{f"{field}__date__lte": date_to})
    return queryset


def date_context(date_from, date_to, preset):
    """Return context variables for date-filter state."""
    return {
        "preset": preset,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "preset_options": [
            ("all", "All Time"),
            ("week", "Last 7 Days"),
            ("month", "Last 30 Days"),
            ("quarter", "Last 90 Days"),
            ("term", "This Term (180d)"),
            ("year", "Last Year"),
        ],
    }
