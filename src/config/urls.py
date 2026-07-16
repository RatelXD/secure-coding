"""Root HTTP routes for the architecture skeleton."""

from django.urls import path

from config.health import liveness, readiness

urlpatterns = [
    path("healthz/", liveness, name="healthz"),
    path("readyz/", readiness, name="readyz"),
]
