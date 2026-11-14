from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Product


@receiver([post_save, post_delete], sender=Product)
def invalidate_catalogue_caches(sender, instance, **kwargs):
    cache.delete("cms:homepage")
    try:
        from apps.seo.services import SEOService
        SEOService.touch()
    except Exception:
        pass
