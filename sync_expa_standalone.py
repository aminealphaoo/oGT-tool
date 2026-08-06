"""
Standalone EXPA sync script — bypasses Celery to avoid psycopg2 hang on Python 3.14 Windows.
"""
import os, sys, json, traceback
from urllib.request import Request, urlopen

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aiesec_tool.settings')
import django
django.setup()

from django.db import connections
from django.utils import timezone
from core.models import SiteConfig, SyncLog
from ops.models import EP


def _expa_status_to_stage(expa_status, meta, has_opportunity=False):
    """
    Map EXPA application status to EP stage.

    Priority:
    1. meta.date_realized → realized
    2. meta.date_approved → approved
    3. meta.date_matched OR has_opportunity (application already linked to an opp) → matched_with_opp
    4. Fallback: map EXPA status text
    """
    if meta.get("date_realized"):
        return "realized"
    if meta.get("date_approved"):
        return "approved"
    if meta.get("date_matched") or has_opportunity:
        return "matched_with_opp"

    status_map = {
        "open": "open", "applied": "applied", "in_progress": "applied",
        "accepted": "accepted", "approved": "approved",
        "realized": "realized", "finished": "realized", "completed": "realized",
        "withdrawn": "open", "rejected": "open", "pending": "open",
        "matched": "matched_with_opp",
    }
    return status_map.get(expa_status, "open")


def sync_expa():
    config = SiteConfig.get()
    token = config.expa_access_token or "5zPLES-3w6pq82iPrXgojR3JoV99Qnx6kogE-yJE0EY"
    api_url = f"https://api.aiesec.org/graphql?access_token={token}"

    sync_log = SyncLog.objects.create(status="running")
    created = 0
    skipped = 0
    page = 1
    per_page = 50

    try:
        while True:
            query = """
            query($page: Int, $perPage: Int) {
              allOpportunityApplication(page: $page, per_page: $perPage, sort: "-created_at") {
                data {
                  id created_at updated_at status
                  person {
                    id full_name email phone
                    home_lc { id name }
                    home_mc { id name }
                  }
                  opportunity {
                    id title
                    programme { short_name_display }
                    host_lc { id name }
                  }
                  meta { date_matched date_approved date_realized }
                }
                paging { total_pages current_page total_items }
              }
            }
            """
            payload = json.dumps({"query": query, "variables": {"page": page, "perPage": per_page}}).encode()
            req = Request(api_url, data=payload, headers={"Content-Type": "application/json"})
            resp = urlopen(req, timeout=30)
            result = json.loads(resp.read())

            if not result or not isinstance(result, dict) or "errors" in result:
                print(f"Error or invalid response: {result}")
                break

            data_dict = result.get("data")
            if not data_dict or not isinstance(data_dict, dict):
                print(f"No data dictionary in response: {result}")
                break

            applications = data_dict.get("allOpportunityApplication")
            if not applications or not isinstance(applications, dict):
                print(f"No allOpportunityApplication in response or null: {result}")
                break

            data = applications.get("data", [])
            paging = applications.get("paging", {})

            if not data:
                break

            total_pages = paging.get("total_pages", "?")
            print(f"Page {page}/{total_pages} — {len(data)} apps — created: {created}, skipped: {skipped}")

            # CRITICAL: close connection after HTTP call, before DB queries
            connections['default'].close()

            for app in data:
                try:
                    person = app.get("person") or {}
                    email = (person.get("email") or "").strip()
                    full_name = (person.get("full_name") or "").strip()
                    phone = (person.get("phone") or "").strip()

                    if not full_name and not email:
                        skipped += 1
                        continue

                    programme_name = ""
                    if app.get("opportunity") and app["opportunity"].get("programme"):
                        programme_name = app["opportunity"]["programme"].get("short_name_display", "")

                    track = "GT"
                    if "teacher" in programme_name.lower() or "gte" in programme_name.lower():
                        track = "GTe"

                    expa_status = (app.get("status") or "").lower()
                    has_opp = bool(app.get("opportunity") and app["opportunity"].get("id"))
                    stage = _expa_status_to_stage(expa_status, app.get("meta", {}), has_opportunity=has_opp)

                    existing = None
                    if email:
                        existing = EP.objects.filter(email=email).first()

                    if existing:
                        if existing.source == "expa_sync":
                            existing.track = track
                            existing.current_stage = stage
                            existing.last_activity_at = timezone.now()
                            existing.save(update_fields=["track", "current_stage", "last_activity_at"])
                            skipped += 1
                        else:
                            skipped += 1
                    else:
                        home_lc_name = ""
                        if person.get("home_lc"):
                            home_lc_name = person["home_lc"].get("name", "")

                        EP.objects.create(
                            full_name=full_name or "Unknown EP",
                            email=email,
                            phone=phone,
                            track=track,
                            current_stage=stage,
                            term=config.current_term,
                            source="expa_sync",
                            university=home_lc_name,
                            last_edited_by=None,
                        )
                        created += 1

                except Exception:
                    skipped += 1

            page += 1
            if paging.get("total_pages") and page > paging["total_pages"]:
                break

        sync_log.status = "success"
        sync_log.created_count = created
        sync_log.skipped_count = skipped
        sync_log.finished_at = timezone.now()
        sync_log.save()

        print(f"\nDONE: created={created}, skipped={skipped}, pages={page-1}")
        return {"status": "success", "created": created, "skipped": skipped}

    except Exception as exc:
        sync_log.status = "failed"
        sync_log.error_message = str(exc)[:500]
        sync_log.finished_at = timezone.now()
        sync_log.save()
        traceback.print_exc()
        return {"status": "failed", "error": str(exc)}


if __name__ == "__main__":
    sync_expa()
