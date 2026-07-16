from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.room_list, name="room-list"),
    path("rooms/<int:room_id>/", views.room_detail, name="room-detail"),
    path("rooms/<int:room_id>/history/", views.room_history, name="room-history"),
]
