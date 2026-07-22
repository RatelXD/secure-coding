from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("accounts/signup/", views.signup, name="signup"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("users/", views.user_list, name="user_list"),
    path("users/<str:username>/", views.user_detail, name="user_detail"),
    path("account/", views.profile, name="profile"),
    path("account/bio/", views.bio_edit, name="bio_edit"),
    path("account/password/", views.password_change, name="password_change"),
    path("account/withdraw/", views.withdraw, name="withdraw"),
]
