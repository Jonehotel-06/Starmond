"""CheckoutService — creates authoritative pending orders for BOTH
cart checkout and Buy Now. Inventory is reserved atomically; idempotency keys
prevent duplicate orders from double-submits or retries."""
import logging
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError
from apps.core.money import to_decimal
from apps.inventory.services import InventoryService
from apps.orders.models import Order, OrderItem
from apps.orders.services import OrderService
from apps.products.models import Product, ProductVariation

from .cart_service import CartService
from .pricing_service import PricingService

logger = logging.getLogger("starmond.checkout")

GUEST_TOKEN_SALT = "starmond-guest-order"

CUSTOMIZATION_LIMIT = 4000  # chars of serialized customization payload


class CheckoutService:
    # ------------------------------------------------------------------ entry
    @classmethod
    def create_order(cls, request, *, payload):
        idem_key = (request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or "")[:80] or None
        user = request.user if request.user.is_authenticated else None
        if idem_key:
            existing = Order.objects.filter(idempotency_key=idem_key).first()
            if existing:
                if user and existing.customer_id and existing.customer_id != user.pk:
                    raise ServiceError("Idempotency key belongs to another session.", code="idempotency_conflict", status_code=409)
                return existing, False

        contact = payload.get("contact") or {}
        delivery = payload.get("delivery") or {}
        cls._validate_contact(contact, user)
        cls._validate_delivery(delivery)

        source = payload.get("source") or {"type": "cart"}
        with transaction.atomic():
            order, lines = cls._build_order(user, contact, delivery, source, payload)
            cls._reserve_inventory(order, lines)
            order = cls._finalize_totals(order, lines, payload, user)
        return order, True

    # ------------------------------------------------------------------ steps
    @classmethod
    def _validate_contact(cls, contact, user):
        if user:
            return
        for field in ("full_name", "email", "phone"):
            if not str(contact.get(field, "")).strip():
                raise ServiceError(f"contact.{field} is required for guest checkout.",
                                   code="required_field", fields={f"contact.{field}": "This field is required."})

    @classmethod
    def _validate_delivery(cls, delivery):
        required = ["full_name", "phone", "state", "city", "street"]
        missing = [f for f in required if not str(delivery.get(f, "")).strip()]
        if missing:
            raise ServiceError("Delivery information is incomplete.", code="required_field",
                               fields={f"delivery.{f}": "This field is required." for f in missing})

    @classmethod
    def _build_order(cls, user, contact, delivery, source, payload):
        stype = source.get("type")
        lines = []
        if stype == "cart":
            if user is None and not (contact.get("email")):
                raise ServiceError("Guest checkout requires contact details.", code="required_field")
            cart = cls._resolve_cart(user, payload.get("cart_token"))
            items = CartService.validate_for_checkout(cart)
            for item in items:
                lines.append({
                    "product": item.product, "variation": item.variation,
                    "quantity": item.quantity,
                    "customization": item.customization if hasattr(item, "customization") else {},
                })
            source_cart = cart
        elif stype == "buy_now":
            product = Product.objects.filter(pk=source.get("product_id")).first()
            if not product or not product.is_public:
                raise ServiceError("The selected product is not available.", code="product_unavailable", status_code=409)
            variation = None
            if source.get("variation_id"):
                variation = ProductVariation.objects.filter(pk=source["variation_id"], product=product, is_available=True).first()
                if not variation:
                    raise ServiceError("The selected option is not available.", code="invalid_variation", status_code=409)
            quantity = int(source.get("quantity", 1))
            if quantity < 1 or quantity > settings.MAX_CART_ITEM_QUANTITY:
                raise ServiceError("Invalid quantity.", code="invalid_quantity")
            customization = cls._validate_customization(product, source.get("customization") or {})
            lines.append({"product": product, "variation": variation, "quantity": quantity, "customization": customization})
            source_cart = None
        else:
            raise ServiceError('source.type must be "cart" or "buy_now".', code="invalid_source")

        shipping_method_id = delivery.get("shipping_method_id")
        if not shipping_method_id:
            raise ServiceError("delivery.shipping_method_id is required.", code="required_field",
                               fields={"delivery.shipping_method_id": "Select a delivery method."})

        order = Order(
            reference=OrderService.make_reference(),
            customer=user,
            source=Order.Source.BUY_NOW if stype == "buy_now" else Order.Source.CART,
            status=Order.Status.PENDING_PAYMENT,
            payment_status=Order.PaymentStatus.PENDING,
            contact_full_name=(user.full_name if user else contact["full_name"])[:150],
            contact_email=((user.email if user else contact["email"]).lower())[:254],
            contact_phone=(user.phone if user and user.phone else str(contact.get("phone", "")))[:30] or delivery["phone"],
            delivery_full_name=delivery["full_name"][:150],
            delivery_phone=delivery["phone"][:30],
            delivery_state=delivery["state"][:80],
            delivery_city=delivery["city"][:80],
            delivery_street=delivery["street"][:255],
            delivery_details=str(delivery.get("details", ""))[:255],
            delivery_instructions=str(delivery.get("instructions", ""))[:2000],
            shipping_method_id=int(shipping_method_id),
            placed_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=settings.PENDING_ORDER_EXPIRY_MINUTES),
            idempotency_key=(payload.get("idempotency_key") or None),
        )
        order._checkout_lines = lines
        order._source_cart = source_cart
        return order, lines

    @classmethod
    def _resolve_cart(cls, user, cart_token):
        from apps.cart.models import Cart
        if user:
            cart = Cart.objects.filter(user=user, status=Cart.Status.ACTIVE).first()
            if cart and cart.items.exists():
                return cart
            # Authenticated user may still check out a linked guest cart token
        if cart_token:
            cart = Cart.objects.filter(token=cart_token, status=Cart.Status.ACTIVE).first()
            if cart:
                return cart
        raise ServiceError("No active cart with items was found.", code="empty_cart")

    @classmethod
    def _validate_customization(cls, product, customization):
        if not customization:
            if product.supports_customization and any(f.get("required") for f in product.customization_schema or []):
                missing = [f["field"] for f in product.customization_schema if f.get("required")]
                raise ServiceError("This made-to-order product requires customization details.",
                                   code="customization_required", fields={f"customization.{m}": "Required." for m in missing})
            return {}
        if not product.supports_customization:
            raise ServiceError("This product does not accept customization.", code="customization_not_supported")
        schema = {f["field"]: f for f in product.customization_schema or []}
        cleaned = {}
        for key, value in customization.items():
            if key not in schema:
                continue
            field = schema[key]
            value = value if not isinstance(value, str) else value.strip()[:1000]
            if field.get("type") == "select" and field.get("options") and value not in field["options"]:
                raise ServiceError(f"Invalid choice for {field.get('label', key)}.", code="invalid_customization",
                                   fields={f"customization.{key}": "Invalid option."})
            if field.get("required") and value in ("", None):
                raise ServiceError(f"{field.get('label', key)} is required.", code="customization_required",
                                   fields={f"customization.{key}": "Required."})
            cleaned[key] = value
        for key, field in schema.items():
            if field.get("required") and key not in cleaned:
                raise ServiceError(f"{field.get('label', key)} is required.", code="customization_required",
                                   fields={f"customization.{key}": "Required."})
        if len(str(cleaned)) > CUSTOMIZATION_LIMIT:
            raise ServiceError("Customization details are too long.", code="customization_too_long")
        return cleaned

    @classmethod
    def _reserve_inventory(cls, order, lines):
        order.save()  # obtain PK for movement references
        for line in lines:
            product, variation, quantity = line["product"], line.get("variation"), line["quantity"]
            inventory = InventoryService.resolve_inventory(product, variation)
            if inventory is None:
                inventory = InventoryService.ensure_inventory(product, variation)
            InventoryService.reserve(inventory, quantity, order=order, reason="Checkout reservation")

    @classmethod
    def _finalize_totals(cls, order, lines, payload, user):
        """Price everything from the DATABASE, apply promotion + shipping,
        then persist order items."""
        priced_lines = []
        for line in lines:
            unit = PricingService.unit_price(line["product"], line.get("variation"))
            priced_lines.append({
                "product": line["product"], "variation": line.get("variation"),
                "unit_price": unit,
                "line_total": to_decimal(unit * line["quantity"]),
            })
        subtotal = sum((l["line_total"] for l in priced_lines), to_decimal(0))
        discount, promotion = to_decimal(0), None
        code = (payload.get("promotion_code") or "").strip()
        if code:
            from apps.promotions.services import PromotionService
            promotion, discount = PromotionService.validate(
                code, lines=priced_lines, subtotal=subtotal, customer=user)
        from apps.shipping.services import ShippingService
        method, shipping_fee = ShippingService.quote(order.shipping_method_id, order.delivery_state, subtotal - discount)
        order.shipping_method_name = method.name[:120]
        order.shipping_method_kind = method.kind
        order.shipping_estimate = method.estimated_delivery[:120]
        order.subtotal_amount = to_decimal(subtotal)
        order.discount_amount = to_decimal(discount)
        order.shipping_fee = to_decimal(shipping_fee)
        order.total_amount = to_decimal(subtotal - discount + shipping_fee)
        order.promotion = promotion
        order.promotion_code_snapshot = (promotion.code if promotion else "")
        if not order.customer:
            order.guest_access_token = signing.dumps(
                {"ref": order.reference, "email": order.contact_email}, salt=GUEST_TOKEN_SALT)
        order.save()

        for line, priced in zip(lines, priced_lines):
            product, variation = line["product"], line.get("variation")
            customization = dict(line.get("customization") or {})
            reference_image_id = customization.pop("_reference_image_id", None)
            if reference_image_id:
                reference_image_id = cls._validate_reference_image(reference_image_id, user)
            OrderItem.objects.create(
                order=order, product=product, variation=variation,
                product_name=product.name[:200],
                sku=(variation.sku if variation else product.sku)[:64],
                variation_label=(variation.display_name[:160] if variation else ""),
                unit_price=priced["unit_price"],
                quantity=line["quantity"],
                line_total=priced["line_total"],
                customization=customization,
                reference_image_id=reference_image_id,
            )
        if promotion:
            from apps.promotions.services import PromotionService
            PromotionService.record_usage(promotion, order, discount, customer=user)
        source_cart = getattr(order, "_source_cart", None)
        if source_cart is not None and order.source == Order.Source.CART:
            from apps.cart.models import Cart
            Cart.objects.filter(pk=source_cart.pk).update(status=Cart.Status.CONVERTED)
            source_cart.items.all().delete()
        return order

    @staticmethod
    def _validate_reference_image(asset_id, user):
        """Reference images must be private assets uploaded by the ordering
        customer (or by staff on their behalf)."""
        from apps.media.models import MediaAsset
        asset = MediaAsset.objects.filter(pk=asset_id, kind=MediaAsset.Kind.REFERENCE_IMAGE,
                                          visibility=MediaAsset.Visibility.PRIVATE).first()
        if not asset:
            return None
        if user and asset.uploaded_by_id not in (None, user.pk):
            return None
        return asset.pk

    # ------------------------------------------------------------- guest access
    @staticmethod
    def verify_guest_token(order, token):
        try:
            data = signing.loads(token, salt=GUEST_TOKEN_SALT,
                               max_age=60 * 60 * 24 * settings.GUEST_ORDER_LINK_EXPIRY_DAYS)
        except signing.BadSignature:
            return False
        return data.get("ref") == order.reference and data.get("email") == order.contact_email
