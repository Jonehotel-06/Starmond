from django.urls import path

from apps.cms import views

app_name = "cms"

urlpatterns = [
    path("settings/", views.PublicSettingsView.as_view(), name="public-settings"),
    path("pages/<slug:slug>/", views.ContentPageDetailView.as_view(), name="page"),
    path("admin/settings/", views.StaffSettingsUpdateView.as_view(), name="staff-settings"),
]
