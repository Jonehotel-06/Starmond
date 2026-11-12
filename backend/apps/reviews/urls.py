from django.urls import path

from apps.reviews import views

app_name = "reviews"

urlpatterns = [
    path("product/<str:slug>/", views.ProductReviewsView.as_view(), name="product-reviews"),
    path("", views.ReviewCreateView.as_view(), name="create"),
    path("mine/", views.MyReviewsView.as_view(), name="mine"),
    path("<uuid:review_id>/", views.ReviewUpdateView.as_view(), name="update"),
    path("<uuid:review_id>/helpful/", views.ReviewHelpfulView.as_view(), name="helpful"),
    path("admin/", views.StaffReviewModerationView.as_view(), name="staff-list"),
    path("admin/<uuid:review_id>/", views.StaffReviewModerationView.as_view(), name="staff-moderate"),
]
