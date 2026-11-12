from django.urls import path

from apps.products import admin_views, views

app_name = "products"

urlpatterns = [
    path("", views.ProductListView.as_view(), name="list"),
    path("search/", views.ProductSearchView.as_view(), name="search"),
    path("featured/", views.FeaturedProductsView.as_view(), name="featured"),
    path("facets/", views.ProductFacetsView.as_view(), name="facets"),
    path("admin/", admin_views.StaffProductView.as_view(), name="admin-list"),
    path("admin/<uuid:product_id>/", admin_views.StaffProductDetailView.as_view(), name="admin-detail"),
    path("admin/<uuid:product_id>/<str:action>/", admin_views.StaffProductPublishView.as_view(), name="admin-publish"),
    path("admin/<uuid:product_id>/variations/", admin_views.StaffVariationView.as_view(), name="admin-variations"),
    path("admin/<uuid:product_id>/variations/<uuid:variation_id>/", admin_views.StaffVariationView.as_view(), name="admin-variation-detail"),
    path("admin/<uuid:product_id>/images/", admin_views.StaffProductImageView.as_view(), name="admin-images"),
    path("<str:slug>/", views.ProductDetailView.as_view(), name="detail"),
]
