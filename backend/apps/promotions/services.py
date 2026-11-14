"""PromotionService — ALL eligibility checks happen on the backend.
Only ONE promotion may be applied per order (no stacking)."""
from decimal import Decimal

from django.db import transaction

from apps.core.exceptions import ServiceError
from apps.core.money import ZERO, percent_of, to_decimal


class PromotionService:
    @staticmethod
    def _eligible_line_total(lines, promotion):
        """lines: [{"product": Product, "line_total": Decimal}]"""
        if promotion.scope == promotion.Scope.ALL:
            return sum((l["line_total"] for l in lines), ZERO)
        total = ZERO
        for line in lines:
            product = line["product"]
            if promotion.scope == promotion.Scope.PRODUCTS and product.pk in promotion.product_ids:
                total += line["line_total"]
            elif promotion.scope == promotion.Scope.CATEGORIES and product.category_id in promotion.category_ids:
                total += line["line_total"]
        return to_decimal(total)

    @classmethod
    def validate(cls, code, *, lines, subtotal, customer=None, check_usage=True):
        """Return (promotion, discount_amount) or raise ServiceError."""
        from .models import Promotion
        promotion = Promotion.objects.filter(code=(code or "").strip().upper()).first()
        if promotion is None:
            raise ServiceError("Invalid discount code.", code="invalid_promotion")
        if not promotion.is_active:
            raise ServiceError("This discount code is no longer active.", code="promotion_inactive")
        if not promotion.is_within_window:
            raise ServiceError("This discount code has expired or has not started.", code="promotion_window")
        if promotion.usage_limit is not None and check_usage and promotion.total_usages >= promotion.usage_limit:
            raise ServiceError("This discount code has reached its usage limit.", code="promotion_exhausted")
        if customer and check_usage:
            used = promotion.usages.filter(customer=customer).count()
            if used >= promotion.usage_limit_per_customer:
                raise ServiceError("You have already used this discount code.", code="promotion_customer_limit")
        if promotion.first_time_customers_only:
            if customer is None:
                raise ServiceError("This code requires an account.", code="promotion_account_required")
            from apps.orders.models import Order
            if Order.objects.filter(customer=customer).exclude(status="pending_payment").exists():
                raise ServiceError("This code is for first-time customers only.", code="promotion_first_time")
        if promotion.min_purchase_amount is not None and to_decimal(subtotal) < to_decimal(promotion.min_purchase_amount):
            raise ServiceError(
                f"Minimum purchase of ₦{promotion.min_purchase_amount} required for this code.",
                code="promotion_min_purchase")

        eligible_total = cls._eligible_line_total(lines, promotion)
        if eligible_total <= ZERO:
            raise ServiceError("No items in this order qualify for the discount code.", code="promotion_no_eligible_items")
        if not promotion.applies_to_sale_items:
            for line in lines:
                if line["product"].on_sale and promotion.scope == promotion.Scope.ALL:
                    raise ServiceError("This code cannot be combined with sale items.", code="promotion_sale_items")

        if promotion.kind == promotion.Kind.PERCENTAGE:
            discount = percent_of(eligible_total, promotion.value)
        else:
            discount = to_decimal(min(promotion.value, eligible_total))
        if promotion.max_discount_amount is not None:
            discount = min(discount, to_decimal(promotion.max_discount_amount))
        discount = min(to_decimal(discount), to_decimal(eligible_total))
        if discount <= ZERO:
            raise ServiceError("This code does not produce a discount for the current items.", code="promotion_zero_discount")
        return promotion, to_decimal(discount)

    @staticmethod
    @transaction.atomic
    def record_usage(promotion, order, discount_amount, customer=None):
        from .models import PromotionUsage
        if hasattr(order, "promotion_usage") and getattr(order, "promotion_usage", None):
            return None  # order already has a usage record (idempotency)
        return PromotionUsage.objects.create(
            promotion=promotion, order=order, customer=customer, discount_amount=to_decimal(discount_amount))
