import logging

from celery import shared_task

logger = logging.getLogger("starmond.inventory")


@shared_task(name="apps.inventory.tasks.release_expired_reservations")
def release_expired_reservations():
    """Cancel orders stuck in PENDING_PAYMENT beyond the configured expiry and
    release their inventory reservations. Runs from Celery beat."""
    from apps.orders.services import OrderService
    count = OrderService.expire_stale_pending_orders()
    if count:
        logger.info("Expired %s stale pending order(s); reservations released.", count)
    return count


@shared_task(name="apps.inventory.tasks.check_low_stock")
def check_low_stock():
    """Flag low-stock products and notify staff (best-effort)."""
    from .models import Inventory
    low = Inventory.objects.select_related("product", "variation").all()
    results = [i.pk for i in low if i.is_low_stock]
    logger.info("Low-stock inventory records: %s", len(results))
    return len(results)
