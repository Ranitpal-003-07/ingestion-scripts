from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health),
    path("roll", views.roll),
    path("work", views.work),
]
