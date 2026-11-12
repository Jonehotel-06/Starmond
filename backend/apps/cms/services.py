"""SettingsService — cached, typed access to business settings."""
from __future__ import annotations

import logging

from django.core.cache import cache

from apps.cms.models import Banner, BusinessSetting, ContentPage, StoreLocation

logger = logging.getLogger("apps.cms")

CACHE_KEY = "cms:settings:v1"
CACHE_TTL = 300

DEFAULT_SETTINGS = {
    "business_name": ("STARMOND TECHNOLOGY LIMITED", BusinessSetting.ValueType.TEXT, BusinessSetting.Group.GENERAL),
    "business_tagline": ("Multi-category online retail, delivered across Nigeria.", BusinessSetting.ValueType.TEXT, BusinessSetting.Group.GENERAL),
    "support_email": ("support@starmond.com", BusinessSetting.ValueType.EMAIL, BusinessSetting.Group.CONTACT),
    "support_phone": ("", BusinessSetting.ValueType.TEXT, BusinessSetting.Group.CONTACT),
    "whatsapp_number": ("", BusinessSetting.ValueType.TEXT, BusinessSetting.Group.CONTACT),
    "business_address": ("", BusinessSetting.ValueType.TEXT, BusinessSetting.Group.CONTACT),
    "currency": ("NGN", BusinessSetting.ValueType.TEXT, BusinessSetting.Group.COMMERCE),
    "order_expiry_minutes": ("60", BusinessSetting.ValueType.NUMBER, BusinessSetting.Group.COMMERCE),
    "free_delivery_threshold": ("0", BusinessSetting.ValueType.MONEY, BusinessSetting.Group.SHIPPING),
    "returns_window_days": ("30", BusinessSetting.ValueType.NUMBER, BusinessSetting.Group.LEGAL),
    "announcement_bar": ("", BusinessSetting.ValueType.TEXT, BusinessSetting.Group.GENERAL),
    "instagram_url": ("", BusinessSetting.ValueType.URL, BusinessSetting.Group.SOCIAL),
    "facebook_url": ("", BusinessSetting.ValueType.URL, BusinessSetting.Group.SOCIAL),
    "twitter_url": ("", BusinessSetting.ValueType.URL, BusinessSetting.Group.SOCIAL),
    "meta_title_default": ("", BusinessSetting.ValueType.TEXT, BusinessSetting.Group.SEO),
    "meta_description_default": ("", BusinessSetting.ValueType.TEXT, BusinessSetting.Group.SEO),
}


class SettingsService:
    @classmethod
    def all(cls, *, public_only: bool = True, use_cache: bool = True) -> dict:
        """Returns settings as a flat ``{key: typed_value}`` dict."""
        cache_key = f"{CACHE_KEY}:{'public' if public_only else 'all'}"
        if use_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        qs = BusinessSetting.objects.all()
        if public_only:
            qs = qs.filter(is_public=True)
        data = {row.key: row.typed_value for row in qs}
        cache.set(cache_key, data, CACHE_TTL)
        return data

    @classmethod
    def get(cls, key: str, default=None):
        settings_map = cls.all(public_only=False)
        return settings_map.get(key, default)

    @classmethod
    def grouped(cls, *, public_only: bool = True) -> dict:
        """Settings grouped for the dashboard's settings screens."""
        buckets: dict[str, list[dict]] = {}
        qs = BusinessSetting.objects.all()
        if public_only:
            qs = qs.filter(is_public=True)
        for row in qs:
            buckets.setdefault(row.group, []).append(
                {
                    "key": row.key,
                    "label": row.label,
                    "value": row.typed_value,
                    "value_type": row.value_type,
                    "description": row.description,
                    "is_editable": row.is_editable,
                }
            )
        return buckets

    @classmethod
    def update_many(cls, values: dict, *, actor=None) -> dict:
        """Bulk-updates settings from the dashboard and clears the cache."""
        updated = {}
        from apps.audit.services import AuditService

        for key, value in values.items():
            setting = BusinessSetting.objects.filter(key=key).first()
            if setting is None or not setting.is_editable:
                continue
            before = setting.value
            setting.value = "" if value is None else str(value)
            setting.full_clean()
            setting.save(update_fields=["value", "updated_at"])
            updated[key] = {"from": before, "to": setting.value}
        cls.invalidate()
        if updated:
            AuditService.record(
                action="settings_changed",
                entity_type="business_setting",
                entity_id="bulk",
                actor=actor,
                summary=f"Updated {len(updated)} setting(s)",
                after=updated,
            )
        return updated

    @classmethod
    def invalidate(cls) -> None:
        cache.delete(f"{CACHE_KEY}:public")
        cache.delete(f"{CACHE_KEY}:all")

    @classmethod
    def seed_defaults(cls) -> int:
        """Idempotently creates any missing default settings."""
        created = 0
        for key, (value, value_type, group) in DEFAULT_SETTINGS.items():
            _, was_created = BusinessSetting.objects.get_or_create(
                key=key,
                defaults={
                    "label": key.replace("_", " ").title(),
                    "value": value,
                    "value_type": value_type,
                    "group": group,
                    "is_public": True,
                },
            )
            created += int(was_created)
        cls.invalidate()
        return created

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------
    @staticmethod
    def public_pages() -> list[dict]:
        from apps.core.models import PublishableModel

        return [
            {
                "slug": page.slug,
                "title": page.title,
                "excerpt": page.excerpt,
                "url": page.absolute_path,
                "show_in_footer": page.show_in_footer,
                "show_in_header": page.show_in_header,
                "meta_title": page.meta_title or page.title,
                "meta_description": page.meta_description or page.excerpt,
            }
            for page in ContentPage.objects.filter(
                status=PublishableModel.Status.PUBLISHED
            ).order_by("position", "title")
        ]

    @staticmethod
    def active_banners() -> list[dict]:
        from django.utils import timezone
        from django.db.models import Q

        now = timezone.now()
        return [
            {
                "title": b.title,
                "subtitle": b.subtitle,
                "image": b.image.url if b.image else None,
                "cta_label": b.cta_label,
                "cta_url": b.cta_url,
            }
            for b in Banner.objects.filter(is_active=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
            .order_by("position")
        ]

    @staticmethod
    def pickup_locations() -> list[dict]:
        return [
            {
                "name": loc.name,
                "address": loc.address,
                "city": loc.city,
                "state": loc.state,
                "phone": loc.phone,
                "opening_hours": loc.opening_hours,
            }
            for loc in StoreLocation.objects.filter(is_active=True, is_pickup_point=True)
        ]
