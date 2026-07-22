"""Root HTTP routes for the Cycle 1 application."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from config.health import liveness, readiness
from apps.accounts.views import home

urlpatterns = [
    path("", home, name="home"),
    path("", include("apps.accounts.urls")),
    path("products/", include("apps.catalog.urls")),
    path("chat/", include("apps.chat.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("reports/", include("apps.moderation.urls")),
    path("transfers/", include("apps.transfers.urls")),
    path("trades/", include("apps.trades.urls")),
    path("management/", include("apps.moderation.management_urls")),
    path("healthz/", liveness, name="healthz"),
    path("readyz/", readiness, name="readyz"),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
