from django.urls import path
from . import views_public

urlpatterns = [
    path('', views_public.public_intake, name='public_intake'),
    path('success/', views_public.public_intake_success, name='public_intake_success'),
]
