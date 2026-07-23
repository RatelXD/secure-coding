from django.urls import path

from . import views

app_name = "transfers"

urlpatterns = [
    path("", views.create_transfer, name="create"),
    path("rooms/<int:room_id>/", views.create_room_transfer, name="room-create"),
    path("account/close/", views.close_mock_account, name="account-close"),
]
