from django.urls import path

from . import views

urlpatterns = [
    path("picker/", views.identity_picker, name="identity_picker"),
    path("clear/", views.identity_clear, name="identity_clear"),
]
