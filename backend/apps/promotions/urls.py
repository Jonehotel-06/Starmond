from django.urls import path

from apps.promotions import views

app_name = "promotions"

urlpatterns = [
    path("validate/", views.PromotionValidateView.as_view(), name="validate"),
    path("", views.PublicPromotionListView.as_view(), name="public-list"),
    path("admin/", views.StaffPromotionView.as_view(), name="staff"),
]
