from django.urls import path

from apps.seo import views

app_name = "seo"

urlpatterns = [
    path("metadata/", views.MetadataView.as_view(), name="metadata"),
    path("settings/", views.SEOSettingsListView.as_view(), name="settings"),
]
