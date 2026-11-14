from django.core.cache import cache

CACHE_KEY = "cms:business_settings"
CACHE_TTL = 300


class BusinessSettingsService:
    """Cached accessor for editable business settings with safe defaults."""

    @classmethod
    def _row(cls):
        from .models import BusinessSetting
        row, _ = BusinessSetting.objects.get_or_create(pk=1)
        return row

    @classmethod
    def all_values(cls, use_cache=True):
        from .models import DEFAULT_BUSINESS_SETTINGS
        if use_cache:
            cached = cache.get(CACHE_KEY)
            if cached is not None:
                return cached
        row = cls._row()
        merged = {**DEFAULT_BUSINESS_SETTINGS, **(row.values or {})}
        if use_cache:
            cache.set(CACHE_KEY, merged, CACHE_TTL)
        return merged

    @classmethod
    def get(cls, key, default=None, use_cache=True):
        return cls.all_values(use_cache=use_cache).get(key, default)

    @classmethod
    def update(cls, patch, user=None):
        row = cls._row()
        values = {**(row.values or {}), **patch}
        row.values = values
        row.updated_by = user
        row.save(update_fields=["values", "updated_by", "updated_at"])
        cache.delete(CACHE_KEY)
        return cls.all_values(use_cache=False)
