from decimal import Decimal

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order
from apps.products.models import ProductVariation

from .base import StarmondAPITestCase


class CartTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product(name="Socket Outlet", sku="SCK-1", price="2500.00", stock=5)

    def test_guest_cart_add_update_remove_with_token(self):
        response = self.client.post("/api/cart/", {"product": self.product.pk, "quantity": 2}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        token = response.data["data"]["token"]
        self.assertEqual(response.data["data"]["item_count"], 2)
        self.assertEqual(response.data["data"]["subtotal"], "5000.00")

        self.client.credentials(HTTP_X_CART_TOKEN=token)
        response = self.client.get("/api/cart/")
        item_id = response.data["data"]["items"][0]["id"]

        response = self.client.patch(f"/api/cart/items/{item_id}/", {"quantity": 4}, format="json")
        self.assertEqual(response.data["data"]["subtotal"], "10000.00")

        response = self.client.patch(f"/api/cart/items/{item_id}/", {"quantity": 99}, format="json")
        self.assertEqual(response.status_code, 409)  # stock unavailable

        response = self.client.delete(f"/api/cart/items/{item_id}/")
        self.assertEqual(response.data["data"]["item_count"], 0)

    def test_cart_never_trusts_client_price(self):
        response = self.client.post("/api/cart/", {
            "product": self.product.pk, "quantity": 1, "unit_price": "1.00"}, format="json")
        self.assertEqual(response.data["data"]["subtotal"], "2500.00")  # server price wins

    def test_duplicate_lines_merge_not_duplicate(self):
        self.client.post("/api/cart/", {"product": self.product.pk, "quantity": 1}, format="json")
        token = Cart.objects.first().token
        self.client.credentials(HTTP_X_CART_TOKEN=token)
        self.client.post("/api/cart/", {"product": self.product.pk, "quantity": 2}, format="json")
        self.assertEqual(CartItem.objects.filter(cart__token=token).count(), 1)
        self.assertEqual(CartItem.objects.get(cart__token=token).quantity, 3)

    def test_guest_cart_merge_on_login(self):
        # guest adds items
        self.client.post("/api/cart/", {"product": self.product.pk, "quantity": 2}, format="json")
        guest_token = Cart.objects.get(user__isnull=True).token
        # customer already has a cart with 1 unit
        customer = self.make_customer()
        user_cart = Cart.objects.create(user=customer)
        CartItem.objects.create(cart=user_cart, product=self.product, quantity=1)
        self.client.force_authenticate(customer)
        response = self.client.post("/api/cart/merge/", {"token": guest_token}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        user_cart.refresh_from_db()
        merged_item = CartItem.objects.get(cart=user_cart, product=self.product)
        self.assertEqual(merged_item.quantity, 3)
        guest_cart = Cart.objects.get(token=guest_token)
        self.assertEqual(guest_cart.status, Cart.Status.MERGED)

    def test_variation_cart_line(self):
        variation = ProductVariation.objects.create(
            product=self.product, sku="SCK-1-WHITE", name="White",
            options={"Colour": "White"}, price_adjustment=Decimal("200"))
        from apps.inventory.services import InventoryService
        InventoryService.ensure_inventory(self.product, variation, opening=3)
        response = self.client.post("/api/cart/", {
            "product": self.product.pk, "variation": variation.pk, "quantity": 2}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["data"]["subtotal"], "5400.00")  # (2500+200)*2
        response = self.client.post("/api/cart/", {
            "product": self.product.pk, "variation": variation.pk, "quantity": 5}, format="json")
        self.assertEqual(response.status_code, 409)  # only 3 in stock; 2 already in cart


class BuyNowCheckoutTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product(name="Extension Box", sku="EXT-1", price="8000.00", stock=4)
        self.zone, self.method = self.make_shipping("Lagos", fee="2500.00")

    def test_buy_now_creates_order_without_touching_cart(self):
        # existing cart with a different product
        other = self.make_product(name="Bulb", sku="BLB-1", price="1500.00", stock=9)
        self.client.post("/api/cart/", {"product": other.pk, "quantity": 3}, format="json")
        cart = Cart.objects.get(user__isnull=True)
        self.assertEqual(cart.items.count(), 1)

        payload = self.checkout_payload(self.product, quantity=2, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data["data"]
        self.assertEqual(data["source"], "buy_now")
        self.assertEqual(data["totals"]["subtotal"], "16000.00")
        self.assertEqual(data["totals"]["shipping_fee"], "2500.00")
        self.assertEqual(data["totals"]["total"], "18500.00")
        self.assertEqual(len(data["items"]), 1)
        # existing cart untouched
        cart.refresh_from_db()
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(cart.items.first().quantity, 3)
        self.assertEqual(cart.status, Cart.Status.ACTIVE)

    def test_buy_now_reserves_stock(self):
        payload = self.checkout_payload(self.product, quantity=3, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        from apps.inventory.services import InventoryService
        inventory = InventoryService.resolve_inventory(self.product, None)
        self.assertEqual(inventory.reserved, 3)
        self.assertEqual(inventory.available, 1)

    def test_buy_now_exceeding_stock_rejected(self):
        payload = self.checkout_payload(self.product, quantity=9, shipping_method=self.method)
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "stock_unavailable")
        self.assertFalse(Order.objects.exists())

    def test_idempotency_key_prevents_duplicate_orders(self):
        payload = self.checkout_payload(self.product, quantity=1, shipping_method=self.method)
        headers = {"HTTP_IDEMPOTENCY_KEY": "unique-key-abc-123"}
        r1 = self.client.post("/api/checkout/", payload, format="json", **headers)
        r2 = self.client.post("/api/checkout/", payload, format="json", **headers)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.data["data"]["reference"], r2.data["data"]["reference"])
        self.assertEqual(Order.objects.count(), 1)

    def test_guest_checkout_requires_delivery_details(self):
        payload = self.checkout_payload(self.product, shipping_method=self.method)
        payload["delivery"].pop("street")
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "required_field")

    def test_shipping_fee_authoritative_per_state(self):
        zone2, method2 = self.make_shipping("Abuja FCT", fee="4000.00")
        payload = self.checkout_payload(self.product, shipping_method=method2, state="Abuja FCT")
        payload["delivery"]["state"] = "Abuja FCT"
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["data"]["totals"]["shipping_fee"], "4000.00")

        # Lagos method cannot ship to Abuja
        payload = self.checkout_payload(self.product, shipping_method=self.method, state="Abuja FCT")
        payload["delivery"]["state"] = "Abuja FCT"
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "shipping_zone_mismatch")

    def test_cart_checkout_converts_cart_and_uses_server_totals(self):
        self.client.post("/api/cart/", {"product": self.product.pk, "quantity": 2}, format="json")
        cart = Cart.objects.get(user__isnull=True)
        payload = self.checkout_payload(self.product, source="cart", shipping_method=self.method)
        payload["cart_token"] = cart.token
        payload["delivery"]["shipping_method_id"] = self.method.pk
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["data"]["totals"]["total"], "18500.00")
        cart.refresh_from_db()
        self.assertEqual(cart.status, Cart.Status.CONVERTED)
        self.assertEqual(cart.items.count(), 0)


class PromotionTests(StarmondAPITestCase):
    def setUp(self):
        super().setUp()
        from django.utils import timezone
        from datetime import timedelta
        from apps.promotions.models import Promotion
        self.product = self.make_product(name="Kettle", sku="KTL-1", price="10000.00", stock=10)
        self.zone, self.method = self.make_shipping("Lagos", fee="2000.00")
        self.promo = Promotion.objects.create(
            code="SAVE10", name="10% off", kind=Promotion.Kind.PERCENTAGE, value=Decimal("10"),
            min_purchase_amount=Decimal("5000"), max_discount_amount=Decimal("800"),
            starts_at=timezone.now() - timedelta(days=1), ends_at=timezone.now() + timedelta(days=1))
        self.expired = Promotion.objects.create(
            code="OLD5", name="Expired", kind=Promotion.Kind.FIXED, value=Decimal("500"),
            starts_at=timezone.now() - timedelta(days=10), ends_at=timezone.now() - timedelta(days=5))

    def _buy(self, code=None, quantity=1):
        payload = self.checkout_payload(self.product, quantity=quantity, shipping_method=self.method, promo=code)
        return self.client.post("/api/checkout/", payload, format="json")

    def test_percentage_discount_with_cap(self):
        response = self._buy("SAVE10", quantity=2)  # subtotal 20000 -> 10% = 2000 capped at 800
        self.assertEqual(response.status_code, 201, response.data)
        totals = response.data["data"]["totals"]
        self.assertEqual(totals["discount"], "800.00")
        self.assertEqual(totals["total"], "21200.00")  # 20000 - 800 + 2000 shipping

    def test_expired_code_rejected(self):
        response = self._buy("OLD5")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "promotion_window")

    def test_min_purchase_enforced(self):
        cheap = self.make_product(name="Match", sku="MTH-1", price="500.00", stock=10)
        payload = self.checkout_payload(cheap, quantity=1, shipping_method=self.method, promo="SAVE10")
        response = self.client.post("/api/checkout/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "promotion_min_purchase")

    def test_invalid_code_rejected(self):
        response = self._buy("NOPE")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "invalid_promotion")

    def test_customer_usage_limit(self):
        customer = self.make_customer()
        self.client.force_authenticate(customer)
        r1 = self._buy("SAVE10")
        self.assertEqual(r1.status_code, 201)
        r2 = self._buy("SAVE10")
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r2.data["error"]["code"], "promotion_customer_limit")

    def test_validate_endpoint_previews_discount(self):
        response = self.client.post("/api/promotions/validate/", {
            "code": "SAVE10", "items": [{"product_id": self.product.pk, "quantity": 1}]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["discount"], "800.00")  # 10% of 10000 = 1000 capped 800
