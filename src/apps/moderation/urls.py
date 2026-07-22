from django.urls import path

from . import views

app_name = "moderation"

urlpatterns = [
    path("users/<int:target_id>/", views.report_user, name="report-user"),
    path("products/<int:target_id>/", views.report_product, name="report-product"),
    path("reviews/<int:target_id>/", views.report_review, name="report-review"),
]
