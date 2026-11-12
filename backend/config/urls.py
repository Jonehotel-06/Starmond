"""Root URL configuration. Public API is versioned under ``/api/v1/``."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.seo import pages
from apps.seo.views import RobotsTxtView, SitemapXmlView


def health(request):
    """Liveness probe — intentionally free of database access."""
    return JsonResponse({"status": "ok", "service": settings.BUSINESS_NAME})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("api/v1/", include("config.api_urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    # SEO surfaces are served by the backend so crawlers never need JavaScript.
    path("sitemap.xml", SitemapXmlView.as_view(), name="sitemap-xml"),
    path("robots.txt", RobotsTxtView.as_view(), name="robots-txt"),
    # Server-rendered public storefront — crawlable without JavaScript (Section 25).
    path("", pages.HomePageView.as_view(), name="home"),
    path("shop", pages.ShopPageView.as_view(), name="shop"),
    path("shop/", pages.ShopPageView.as_view()),
    path("category/<path:path>", pages.CategoryPageView.as_view(), name="category"),
    path("category/<path:path>/", pages.CategoryPageView.as_view()),
    path("product/<slug:slug>", pages.ProductPageView.as_view(), name="product-page"),
    path("product/<slug:slug>/", pages.ProductPageView.as_view()),
    path("page/<slug:slug>", pages.ContentPageView.as_view(), name="content-page"),
    path("page/<slug:slug>/", pages.ContentPageView.as_view()),
    # Admin-managed redirects, then a real 404.
    path("<path:path>", pages.RedirectFallbackView.as_view(), name="fallback"),
]

def handler404(request, exception=None):
    """Render the storefront 404 page instead of Django's bare default."""
    return pages.not_found_response(request)


def handler500(request):
    return pages.server_error_response(request)


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
