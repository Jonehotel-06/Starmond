from django.urls import path

from apps.categories import admin_views, views

app_name = "categories"

urlpatterns = [
    path("", views.CategoryListView.as_view(), name="list"),
    path("tree/", views.CategoryTreeView.as_view(), name="tree"),
    path("admin/", admin_views.StaffCategoryView.as_view(), name="admin-list"),
    path("admin/<uuid:category_id>/", admin_views.StaffCategoryDetailView.as_view(), name="admin-detail"),
    path("<str:slug>/", views.CategoryDetailView.as_view(), name="detail"),
]
