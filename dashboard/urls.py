from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("leaderboard/export/", views.leaderboard_export_csv, name="leaderboard_export_csv"),
    path("workload/", views.workload, name="workload"),
    path("compare/", views.compare, name="compare"),
    path("expa-sync/", views.automation, name="trigger_expa_sync"),
    path("update-stats/", views.update_stats, name="update_stats"),
]
