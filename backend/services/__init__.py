"""
Top-level service registry.

The authoritative implementations live beside their domain models; this package
re-exports them so callers can depend on a single, stable import surface:

    from services import OrderService, PaystackService
"""
from apps.accounts.services import AccountService
from apps.audit.services import AuditService
from apps.cart.services import CartService
from apps.categories.services import CategoryService
from apps.cms.services import SettingsService
from apps.dashboard.services import DashboardService
from apps.emails.services import EmailService
from apps.inventory.services import InventoryService
from apps.notifications.services import NotificationService
from apps.orders.checkout import CheckoutService
from apps.orders.pricing import PricingService
from apps.orders.services import OrderService
from apps.payments.paystack import PaystackService
from apps.payments.services import PaymentService
from apps.products.services import ProductService
from apps.promotions.services import PromotionService
from apps.refunds.services import RefundService
from apps.reports.services import ReportService
from apps.reviews.services import ReviewService
from apps.seo.services import SEOService
from apps.shipping.services import ShippingService

__all__ = [
    "AccountService",
    "AuditService",
    "CartService",
    "CategoryService",
    "CheckoutService",
    "CustomerService",
    "DashboardService",
    "EmailService",
    "InventoryService",
    "NotificationService",
    "OrderService",
    "PaymentService",
    "PaystackService",
    "PricingService",
    "ProductService",
    "PromotionService",
    "RefundService",
    "ReportService",
    "ReviewService",
    "SEOService",
    "SettingsService",
    "ShippingService",
]

# CustomerService is a thin façade over account/customer operations and is
# defined here to keep the documented service list complete.
from django.db import transaction


class CustomerService:
    """Customer-facing profile and account operations."""

    @staticmethod
    def get_profile(user):
        from apps.customers.models import CustomerProfile

        profile, _ = CustomerProfile.objects.get_or_create(user=user)
        return profile

    @staticmethod
    def default_address(user):
        from apps.customers.models import Address

        return (
            Address.objects.filter(user=user, is_default=True).first()
            or Address.objects.filter(user=user).first()
        )

    @staticmethod
    @transaction.atomic
    def set_default_address(*, user, address_id: str) -> "Address":  # noqa: F821
        from apps.core.exceptions import NotFound
        from apps.customers.models import Address

        address = Address.objects.filter(pk=address_id, user=user).first()
        if address is None:
            raise NotFound("Address not found.")
        address.is_default = True
        address.save(update_fields=["is_default", "updated_at"])
        return address

    @staticmethod
    def order_history(user):
        from apps.orders.models import Order

        return Order.objects.filter(customer=user).order_by("-created_at")

    @staticmethod
    def wishlist_count(user) -> int:
        from apps.customers.models import Wishlist

        wishlist = Wishlist.objects.filter(user=user).first()
        return wishlist.items.count() if wishlist else 0
