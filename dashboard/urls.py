from django.urls import path

from . import views, api

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("leaderboard/export/", views.leaderboard_export_csv, name="leaderboard_export_csv"),
    path("workload/", views.workload, name="workload"),
    
    # API endpoints
    path("api/sd-ratio/", api.sd_ratio_api, name="api_sd_ratio"),
    path("api/ghost-opps/", api.ghost_opps_api, name="api_ghost_opps"),
    path("api/cold-eps/", api.cold_eps_api, name="api_cold_eps"),
]

