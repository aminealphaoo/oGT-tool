from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("workload/", views.workload, name="workload"),
    path("compare/", views.compare, name="compare"),
    path("expa-sync/", views.trigger_expa_sync, name="trigger_expa_sync"),
]
