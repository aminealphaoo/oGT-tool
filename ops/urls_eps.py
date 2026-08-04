from django.urls import path

from . import views

urlpatterns = [
    path("", views.ep_list, name="ep_list"),
    path("export/", views.ep_export_csv, name="ep_export_csv"),
    path("new/", views.ep_create, name="ep_create"),
    path("import/", views.ep_bulk_import, name="ep_bulk_import"),
    path("expa-import/", views.ep_expa_import, name="ep_expa_import"),
    path("bulk-reassign/", views.ep_bulk_reassign, name="ep_bulk_reassign"),
    path("save-filter/", views.save_filter, name="save_filter"),
    path("delete-filter/<int:filter_id>/", views.delete_filter, name="delete_filter"),
    path("<int:pk>/", views.ep_detail, name="ep_detail"),
    path("<int:pk>/edit/", views.ep_edit, name="ep_edit"),
    path("<int:pk>/advance/", views.ep_advance_stage, name="ep_advance_stage"),
    path("<int:pk>/revert/", views.ep_revert_stage, name="ep_revert_stage"),
    path("<int:pk>/archive/", views.ep_archive, name="ep_archive"),
    path("<int:pk>/unarchive/", views.ep_unarchive, name="ep_unarchive"),
    path("<int:pk>/problem/", views.ep_set_problem, name="ep_set_problem"),
    path("<int:pk>/interaction/", views.ep_add_interaction, name="ep_add_interaction"),
    path("<int:pk>/quick-interaction/", views.ep_quick_interaction, name="ep_quick_interaction"),
    path("<int:pk>/tl-notes/", views.ep_update_tl_notes, name="ep_update_tl_notes"),
    path("<int:pk>/upload/", views.ep_upload_attachment, name="ep_upload_attachment"),
]

# Separate URLconf for root-level views
problems_patterns = [
    path("", views.problem_list, name="problem_list"),
]

matching_patterns = [
    path("", views.matching, name="matching"),
    path("match/", views.matching_match, name="matching_match"),
]
