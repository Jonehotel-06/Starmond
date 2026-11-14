"""CustomerService — customer-facing account helpers (records access is
always scoped to the requesting customer in the API layer)."""
from apps.customers.models import Address, CustomerProfile
from apps.orders.models import Order


class CustomerService:
    @staticmethod
    def get_or_create_profile(user):
        profile, _ = CustomerProfile.objects.get_or_create(user=user)
        return profile

    @staticmethod
    def order_history(user, limit=100):
        return Order.objects.filter(customer=user).prefetch_related("items")[:limit]

    @staticmethod
    def default_address(user, kind=Address.Kind.SHIPPING):
        return Address.objects.filter(customer=user, kind=kind).order_by("-is_default", "-created_at").first()

    @staticmethod
    def lifetime_value(user):
        from django.db.models import Sum
        total = Order.objects.filter(customer=user, payment_status__in=["paid", "partially_refunded", "refunded"]) \
            .aggregate(t=Sum("total_amount"))["t"]
        return total or 0
