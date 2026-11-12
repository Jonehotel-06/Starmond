from django.urls import path

from apps.media_lib import views

app_name = "media"

urlpatterns = [
    path("upload/", views.MediaUploadView.as_view(), name="upload"),
]
