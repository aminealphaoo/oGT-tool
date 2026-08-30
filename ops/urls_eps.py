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
    path("<int:ep_id>/match/", views.intelligent_match, name="intelligent_match"),
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

# Tasks
tasks_patterns = [
    path("", views.task_list, name="task_list"),
    path("new/", views.task_create, name="task_create"),
    path("<int:task_id>/update/", views.task_update, name="task_update"),
    path("<int:task_id>/delete/", views.task_delete, name="task_delete"),
    path("<int:task_id>/status/", views.task_quick_status, name="task_quick_status"),
]

# Notifications
notifications_patterns = [
    path("", views.notifications_list, name="notifications_list"),
    path("<int:notif_id>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("read-all/", views.notification_mark_all_read, name="notification_mark_all_read"),
]

# Audit log
audit_patterns = [
    path("", views.audit_log_view, name="audit_log"),
]

# Match Lab
match_lab_patterns = [
    path("", views.match_lab, name="match_lab"),
    path("propose/<int:ep_pk>/<int:opp_pk>/", views.match_propose, name="match_propose"),
    path("approve/<int:record_pk>/", views.match_tl_approve, name="match_tl_approve"),
]

# CXP Delivery
cxp_patterns = [
    path("delivery/", views.cxp_delivery, name="cxp_delivery"),
    path("delivery/<int:ep_pk>/toggle/", views.cxp_checklist_toggle, name="cxp_checklist_toggle"),
    path("delivery/<int:ep_pk>/handoff/", views.handoff_create, name="handoff_create"),
    path("delivery/handoff/<int:record_pk>/accept/", views.handoff_accept, name="handoff_accept"),
]

# Brand Content
brand_patterns = [
    path("content/", views.brand_content, name="brand_content"),
    path("content/new/", views.content_item_create, name="content_item_create"),
    path("content/<int:item_pk>/move/", views.content_item_move, name="content_item_move"),
    path("content/testimonial/new/", views.testimonial_create, name="testimonial_create"),
]
