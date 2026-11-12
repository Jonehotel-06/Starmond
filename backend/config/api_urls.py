"""Versioned API routes. Each app owns its own urlconf."""
from django.urls import include, path

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("customers/", include("apps.customers.urls")),
    path("catalogue/", include("apps.categories.urls")),
    path("products/", include("apps.products.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("cart/", include("apps.cart.urls")),
    path("orders/", include("apps.orders.urls")),
    path("payments/", include("apps.payments.urls")),
    path("refunds/", include("apps.refunds.urls")),
    path("shipping/", include("apps.shipping.urls")),
    path("promotions/", include("apps.promotions.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("reports/", include("apps.reports.urls")),
    path("cms/", include("apps.cms.urls")),
    path("media/", include("apps.media_lib.urls")),
    path("seo/", include("apps.seo.urls")),
]
