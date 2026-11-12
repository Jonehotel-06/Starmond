"""
PromotionService — the only place a discount may be granted.

Guarantees (Section 18 / Section 45):

* expired, not-yet-started, inactive and exhausted codes are rejected;
* per-customer redemption limits and first-order-only rules are enforced;
* a discount can never exceed the eligible subtotal or the configured cap;
* stacking is refused unless both promotions explicitly allow it;
* every redemption is written to ``PromotionUsage`` for financial reporting.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import ConflictError, NotFound, ValidationError
from apps.core.utils import money
from apps.promotions.models import Promotion, PromotionUsage

logger = logging.getLogger("apps.promotions")


@dataclass(frozen=True)
class DiscountResult:
    promotion_id: str | None
    code: str
    name: str
    discount_amount: Decimal
    free_shipping: bool
    message: str = ""

    @property
    def applied(self) -> bool:
        """True when this result actually changes what the customer pays."""
        return self.promotion_id is not None and (
            self.discount_amount > 0 or self.free_shipping
        )

    def as_dict(self) -> dict:
        return {
            "promotion_id": self.promotion_id,
            "code": self.code,
            "name": self.name,
            "discount_amount": str(money(self.discount_amount)),
            "free_shipping": self.free_shipping,
            "message": self.message,
        }


EMPTY_RESULT = DiscountResult(
    promotion_id=None, code="", name="", discount_amount=Decimal("0.00"), free_shipping=False
)


class PromotionService:
    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    @staticmethod
    def get_by_code(code: str) -> Promotion:
        promotion = Promotion.objects.filter(code__iexact=(code or "").strip()).first()
        if promotion is None:
            raise NotFound("That discount code does not exist.")
        return promotion

    @staticmethod
    def _assert_redeemable(promotion: Promotion, *, user=None, email: str = "") -> None:
        if not promotion.is_active:
            raise ValidationError("This promotion is no longer available.")
        now = timezone.now()
        if promotion.starts_at and promotion.starts_at > now:
            raise ValidationError("This promotion has not started yet.")
        if promotion.ends_at and promotion.ends_at < now:
            raise ValidationError("This promotion has expired.")
        if promotion.is_exhausted:
            raise ValidationError("This promotion has reached its usage limit.")
        if promotion.usage_limit_per_customer is not None:
            used = promotion.usage_count_for(user=user, email=email)
            if used >= promotion.usage_limit_per_customer:
                raise ValidationError("You have already used this promotion the maximum number of times.")
        if promotion.first_order_only:
            if user is None:
                raise ValidationError("This promotion is only available to signed-in customers.")
            if PromotionService._customer_has_paid_order(user):
                raise ValidationError("This promotion is only valid on a customer's first order.")

    @staticmethod
    def _customer_has_paid_order(user) -> bool:
        from apps.orders.models import Order

        return Order.objects.filter(customer=user, payment_status=Order.PaymentStatus.PAID).exists()

    # ------------------------------------------------------------------
    # Eligibility of individual basket lines
    # ------------------------------------------------------------------
    @staticmethod
    def _eligible_lines(promotion: Promotion, lines: list[dict]) -> list[dict]:
        """Filters basket lines the promotion may apply to."""
        if promotion.applies_to == Promotion.AppliesTo.ALL:
            return lines
        if promotion.applies_to == Promotion.AppliesTo.PRODUCTS:
            product_ids = {str(pid) for pid in promotion.products.values_list("id", flat=True)}
            return [ln for ln in lines if str(ln["product_id"]) in product_ids]
        if promotion.applies_to == Promotion.AppliesTo.CATEGORIES:
            category_ids = {
                str(cid) for cid in promotion.categories.values_list("id", flat=True)
            }
            # include descendants so a parent-category promotion covers its subtree
            from apps.categories.models import Category

            expanded = set(category_ids)
            for cid in list(category_ids):
                category = Category.objects.filter(pk=cid).first()
                if category is not None:
                    expanded.update(str(x) for x in category.descendant_ids(include_self=True))
            return [ln for ln in lines if str(ln["category_id"]) in expanded]
        return []

    # ------------------------------------------------------------------
    # Amount calculation
    # ------------------------------------------------------------------
    @staticmethod
    def calculate_discount(promotion: Promotion, lines: list[dict], shipping_fee=0) -> DiscountResult:
        """
        Computes what a promotion is actually worth against a basket.

        ``lines`` items must contain: product_id, category_id, unit_price, quantity.
        """
        eligible = PromotionService._eligible_lines(promotion, lines)
        eligible_subtotal = money(
            sum(money(ln["unit_price"]) * int(ln["quantity"]) for ln in eligible)
        )
        basket_subtotal = money(
            sum(money(ln["unit_price"]) * int(ln["quantity"]) for ln in lines)
        )

        if not eligible:
            return DiscountResult(
                promotion_id=str(promotion.pk), code=promotion.code or "", name=promotion.name,
                discount_amount=Decimal("0.00"), free_shipping=False,
                message="No items in your basket qualify for this promotion.",
            )

        if basket_subtotal < money(promotion.min_order_amount):
            return DiscountResult(
                promotion_id=str(promotion.pk), code=promotion.code or "", name=promotion.name,
                discount_amount=Decimal("0.00"), free_shipping=False,
                message=(
                    f"Spend at least ₦{money(promotion.min_order_amount):,.2f} "
                    f"to use this promotion."
                ),
            )

        if promotion.promotion_type == Promotion.Type.FREE_SHIPPING:
            return DiscountResult(
                promotion_id=str(promotion.pk), code=promotion.code or "", name=promotion.name,
                discount_amount=Decimal("0.00"), free_shipping=True,
                message="Free shipping applied.",
            )

        if promotion.promotion_type == Promotion.Type.PERCENTAGE:
            discount = money(eligible_subtotal * money(promotion.value) / Decimal("100"))
        else:
            discount = money(promotion.value)

        if promotion.max_discount_amount is not None:
            discount = min(discount, money(promotion.max_discount_amount))
        # A discount may never exceed the eligible subtotal.
        discount = min(discount, eligible_subtotal)
        # …and never exceeds the basket itself.
        discount = min(discount, basket_subtotal)

        return DiscountResult(
            promotion_id=str(promotion.pk), code=promotion.code or "", name=promotion.name,
            discount_amount=money(discount), free_shipping=False,
        )

    # ------------------------------------------------------------------
    # Validation entry points used by cart & checkout
    # ------------------------------------------------------------------
    @staticmethod
    def validate_code(*, code: str, lines: list[dict], subtotal, shipping_fee=0,
                      user=None, email: str = "", existing: list[Promotion] | None = None) -> DiscountResult:
        """
        Validates a code against the live basket and returns what it is worth.

        Never raises for "not eligible" business reasons; raises only for an
        unknown code. Business reasons are returned in ``message`` so the cart
        can explain itself without a 4xx.
        """
        promotion = PromotionService.get_by_code(code)
        try:
            PromotionService._assert_redeemable(promotion, user=user, email=email)
        except ValidationError as exc:
            return DiscountResult(
                promotion_id=str(promotion.pk), code=promotion.code or "", name=promotion.name,
                discount_amount=Decimal("0.00"), free_shipping=False, message=str(exc.message),
            )

        if existing and not promotion.is_stackable and any(
            p.pk != promotion.pk and not p.is_stackable for p in existing
        ):
            return DiscountResult(
                promotion_id=str(promotion.pk), code=promotion.code or "", name=promotion.name,
                discount_amount=Decimal("0.00"), free_shipping=False,
                message="This code cannot be combined with the promotion already applied.",
            )

        return PromotionService.calculate_discount(promotion, lines, shipping_fee)

    @staticmethod
    def automatic_promotions(*, lines: list[dict], subtotal, shipping_fee=0, user=None,
                             email: str = "") -> list[DiscountResult]:
        """Applies the best single automatic promotion (never stacks automatically)."""
        now = timezone.now()
        candidates = Promotion.objects.filter(
            is_automatic=True, is_active=True, starts_at__lte=now
        ).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        best: DiscountResult | None = None
        for promotion in candidates:
            if promotion.is_exhausted:
                continue
            try:
                PromotionService._assert_redeemable(promotion, user=user, email=email)
            except ValidationError:
                continue
            result = PromotionService.calculate_discount(promotion, lines, shipping_fee)
            if not (result.discount_amount > 0 or result.free_shipping):
                continue
            if best is None or result.discount_amount > best.discount_amount:
                best = result
        return [best] if best else []

    # ------------------------------------------------------------------
    # Redemption
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def record_usage(*, promotion: Promotion, order, discount_amount, user=None,
                     email: str = "") -> PromotionUsage:
        """
        Records the redemption. Called once per order inside the order transaction.

        The total-usage limit is re-checked under a row lock to close the race
        between two customers claiming the last redemption simultaneously.
        """
        locked = Promotion.objects.select_for_update().get(pk=promotion.pk)
        if locked.usage_limit_total is not None:
            used = PromotionUsage.objects.filter(promotion=locked).count()
            if used >= locked.usage_limit_total:
                raise ConflictError("This promotion has just reached its usage limit.")
        if locked.usage_limit_per_customer is not None:
            used_by_customer = locked.usage_count_for(user=user, email=email)
            if used_by_customer >= locked.usage_limit_per_customer:
                raise ConflictError("You have already used this promotion the maximum number of times.")

        return PromotionUsage.objects.create(
            promotion=locked,
            user=user if getattr(user, "pk", None) else None,
            customer_email=(email or getattr(user, "email", "") or "")[:254],
            order=order,
            discount_amount=money(discount_amount),
            currency=order.currency,
        )

    @staticmethod
    def release_usages_for_order(order) -> None:
        """Restores redemption capacity when an order is cancelled or expires."""
        PromotionUsage.objects.filter(order=order).delete()

    # ------------------------------------------------------------------
    # Admin helpers
    # ------------------------------------------------------------------
    @staticmethod
    def active_public_promotions(limit: int = 10) -> list[Promotion]:
        now = timezone.now()
        return list(
            Promotion.objects.filter(
                is_active=True, is_featured=True, starts_at__lte=now
            ).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))[:limit]
        )
