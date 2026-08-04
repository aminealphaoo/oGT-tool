from django.urls import path

from . import views

urlpatterns = [
    path("", views.ir_list, name="ir_list"),
    path("export/", views.ir_export_csv, name="ir_export_csv"),
    path("new/", views.ir_create, name="ir_create"),
    path("<int:pk>/", views.ir_detail, name="ir_detail"),
    path("<int:pk>/edit/", views.ir_edit, name="ir_edit"),
    path("<int:pk>/add-opportunity/", views.ir_add_opportunity, name="ir_add_opportunity"),
    # Opportunity actions (global)
    path("opp/<int:pk>/edit/", views.opp_edit, name="opp_edit"),
    path("opp/<int:pk>/toggle/", views.opp_toggle, name="opp_toggle"),
    path("opp/<int:pk>/delete/", views.opp_delete, name="opp_delete"),
]
