from django.urls import path

from . import views

app_name = "trades"

urlpatterns = [
    path("products/<int:product_id>/reserve/", views.reserve, name="reserve"),
    path("<int:trade_id>/cancel/", views.cancel, name="cancel"),
    path("<int:trade_id>/complete/", views.complete, name="complete"),
    path("<int:trade_id>/reviews/new/", views.review_create, name="review-create"),
]
