"""Root HTTP routes for the architecture skeleton."""

from django.urls import include, path

from config.health import liveness, readiness
from apps.accounts.views import home

urlpatterns = [
    path("", home, name="home"),
    path("", include("apps.accounts.urls")),
    path("healthz/", liveness, name="healthz"),
    path("readyz/", readiness, name="readyz"),
]
