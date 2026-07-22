from django.urls import path

from . import management_views

app_name = "management"

urlpatterns = [
    path("reports/", management_views.reports, name="reports"),
    path("audit/", management_views.audit, name="audit"),
    path("sanctions/apply/", management_views.sanctions_apply, name="sanctions-apply"),
    path("sanctions/<int:sanction_id>/release/", management_views.sanctions_release, name="sanctions-release"),
    path("scopes/grant/", management_views.scopes_grant, name="scopes-grant"),
    path("scopes/<int:grant_id>/revoke/", management_views.scopes_revoke, name="scopes-revoke"),
    path("reviews/<int:review_id>/visibility/", management_views.review_visibility, name="review-visibility"),
]
