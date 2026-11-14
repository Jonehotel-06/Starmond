"""Root URL configuration — API-first. Public storefront data, customer APIs,
staff/admin APIs, payment webhooks, SEO endpoints and OpenAPI docs."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import HealthView
from apps.seo.prerender import shop_path_view
from apps.seo.views import robots_txt_view, sitemap_xml_view

api_v1 = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.accounts.urls")),
    path("customers/", include("apps.customers.urls")),
    path("categories/", include("apps.categories.urls")),
    path("products/", include("apps.products.urls")),
    path("cart/", include("apps.cart.urls")),
    path("checkout/", include("apps.orders.urls_checkout")),
    path("orders/", include("apps.orders.urls")),
    path("payments/", include("apps.payments.urls")),
    path("refunds/", include("apps.refunds.urls")),
    path("shipping/", include("apps.shipping.urls")),
    path("promotions/", include("apps.promotions.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("cms/", include("apps.cms.urls")),
    path("media/", include("apps.media.urls")),
    path("seo/", include("apps.seo.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("reports/", include("apps.reports.urls")),
    path("admin-panel/", include("apps.accounts.urls_staff")),
    path("admin-panel/customers/", include("apps.customers.urls_staff")),
    path("audit/", include("apps.audit.urls")),
    path("emails/", include("apps.emails.urls")),
    path("inventory/", include("apps.inventory.urls")),
]

urlpatterns = [
    path("api/", include((api_v1, "api"), namespace="v1")),
    path("django-admin/", admin.site.urls),
    # Crawlable server-rendered catalogue pages (SEO pre-render strategy)
    path("shop/", shop_path_view, name="shop-root"),
    path("shop/<path:path>/", shop_path_view, name="shop-path"),
    # SEO crawlability endpoints (public, non-API)
    path("robots.txt", robots_txt_view, name="robots_txt"),
    path("sitemap.xml", sitemap_xml_view, name="sitemap_xml"),
    # API documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
