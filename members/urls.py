from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="members/login.html", redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("directory/", views.member_list, name="member_list"),
    path("directory/create/", views.member_create, name="member_create"),
    path("directory/edit/<int:pk>/", views.member_edit, name="member_edit"),
]
