"""Shared test base: factories, auth helpers, throttling disabled, Paystack mock."""
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Permission, Role, StaffProfile, User
from apps.categories.models import Category
from apps.core.constants import ALL_PERMISSIONS, Perm
from apps.inventory.services import InventoryService
from apps.products.models import Product
from apps.shipping.models import ShippingMethod, ShippingZone


def _rest_framework_no_throttle():
    conf = dict(settings.REST_FRAMEWORK)
    conf["DEFAULT_THROTTLE_CLASSES"] = []
    return conf


class StarmondAPITestCase(APITestCase):
    @classmethod
    def setUpClass(cls):
        cls._ctx = override_settings(REST_FRAMEWORK=_rest_framework_no_throttle(),
                                       CELERY_TASK_ALWAYS_EAGER=True)
        cls._ctx.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._ctx.disable()

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    # ------------------------------------------------------------ factories
    def make_customer(self, email="customer@example.com", password="Passw0rd!234", verified=True):
        user = User.objects.create_user(email=email, password=password, full_name="Test Customer", phone="08012345678")
        if verified:
            user.is_email_verified = True
            user.save()
        return user

    def make_staff(self, email="staff@example.com", perms=None, password="Passw0rd!234", role_name="Test Role"):
        user = User.objects.create_user(email=email, password=password, full_name="Staff User")
        perms = ALL_PERMISSIONS if perms is None else perms
        for codename in perms:
            Permission.objects.get_or_create(
                codename=codename, defaults={"name": codename, "group": codename.split(".")[0]})
        role, _ = Role.objects.get_or_create(name=role_name)
        role.permissions.set(Permission.objects.filter(codename__in=perms))
        StaffProfile.objects.create(user=user, role=role, is_active=True)
        return user

    def make_owner(self, email="owner@example.com", password="Passw0rd!234"):
        return User.objects.create_superuser(email=email, password=password, full_name="Business Owner")

    def make_category(self, name="Electrical", slug=None, parent=None):
        slug = slug or name.lower().replace(" ", "-")
        if Category.objects.filter(slug=slug).exists():
            n = 2
            while Category.objects.filter(slug=f"{slug}-{n}").exists():
                n += 1
            slug = f"{slug}-{n}"
        return Category.objects.create(name=name, slug=slug, parent=parent)

    def make_product(self, category=None, name="Copper Cable 2.5mm", sku=None, price="15000.00",
                     sale=None, stock=10, status=Product.Status.ACTIVE, **kwargs):
        category = category or self.make_category()
        sku = sku or f"SKU-{Product.objects.count() + 1}-{Category.objects.count()}"
        slug = sku.lower().replace(" ", "-").replace(".", "-")
        if Product.objects.filter(slug=slug).exists():
            slug = f"{slug}-{Product.objects.count() + 1}"
        product = Product.objects.create(
            name=name, sku=sku, slug=slug,
            category=category, regular_price=Decimal(price),
            sale_price=Decimal(sale) if sale else None,
            short_description="Quality product", description="Full description here.",
            status=status, **kwargs)
        InventoryService.ensure_inventory(product, None, opening=stock)
        return product

    def make_shipping(self, state="Lagos", fee="2500.00", free_above=None):
        zone, _ = ShippingZone.objects.get_or_create(name=f"{state} Zone", defaults={"states": [state]})
        if not zone.is_active or state not in zone.states:
            zone.states = list(dict.fromkeys(zone.states + [state]))
            zone.is_active = True
            zone.save()
        method = ShippingMethod.objects.create(
            name=f"Standard to {state}", kind=ShippingMethod.Kind.STANDARD, zone=zone,
            fee=Decimal(fee), free_above_amount=Decimal(free_above) if free_above else None,
            min_days=2, max_days=4)
        return zone, method

    # -------------------------------------------------------------- paystack
    def mock_paystack(self, *, initialize=None, verify=None, refund=None, request_side_effect=None):
        """Patch PaystackService._request with provider-like responses."""
        def fake_request(method, path, **kwargs):
            if request_side_effect:
                return request_side_effect(method, path, **kwargs)
            if path.startswith("/transaction/initialize"):
                return initialize or {"status": True, "data": {
                    "authorization_url": "https://checkout.paystack.test/pay",
                    "access_code": "ACC123", "reference": kwargs.get("json", {}).get("reference")}}
            if path.startswith("/transaction/verify"):
                reference = path.rsplit("/", 1)[-1]
                return verify or {"status": True, "data": {
                    "status": "success", "reference": reference, "amount": 1000,
                    "currency": "NGN", "channel": "card", "id": 987654,
                    "gateway_response": "Successful"}}
            if path.startswith("/refund"):
                return refund or {"status": True, "data": {"id": 555, "status": "processed"}}
            return {"status": True, "data": {}}
        return mock.patch("apps.payments.paystack.PaystackService._request", side_effect=fake_request)

    # ---------------------------------------------------------------- helpers
    def checkout_payload(self, product, *, quantity=1, variation=None, shipping_method=None,
                         state="Lagos", promo=None, source="buy_now", contact=None, delivery=None):
        delivery = delivery or {
            "full_name": "Ada Obi", "phone": "08098765432", "state": state,
            "city": "Ikeja", "street": "12 Test Road", "details": "Near plaza",
            "instructions": "Call on arrival", "shipping_method_id": shipping_method.pk if shipping_method else None,
        }
        payload = {
            "contact": contact or {"full_name": "Ada Obi", "email": "ada@example.com", "phone": "08098765432"},
            "delivery": delivery,
        }
        if source == "buy_now":
            payload["source"] = {"type": "buy_now", "product_id": product.pk,
                                 "variation_id": variation.pk if variation else None, "quantity": quantity}
        else:
            payload["source"] = {"type": "cart"}
        if promo:
            payload["promotion_code"] = promo
        return payload
