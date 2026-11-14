from django.urls import path

from .views import (
    CategorySEOStaffView,
    ProductSEOStaffView,
    SEOPreviewSnippetView,
    SEOSettingsStaffView,
    StructuredDataView,
)

app_name = "seo"

urlpatterns = [
    path("structured-data/<str:kind>/", StructuredDataView.as_view(), name="structured-data"),
    path("structured-data/<str:kind>/<slug:slug>/", StructuredDataView.as_view(), name="structured-data-slug"),
    path("settings/", SEOSettingsStaffView.as_view(), name="seo-settings"),
    path("preview-snippet/", SEOPreviewSnippetView.as_view(), name="seo-preview"),
    path("products/<slug:slug>/", ProductSEOStaffView.as_view(), name="product-seo"),
    path("categories/<slug:slug>/", CategorySEOStaffView.as_view(), name="category-seo"),
]
