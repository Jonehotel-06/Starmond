from celery import shared_task


@shared_task(name="apps.orders.tasks.expire_stale_pending_orders")
def expire_stale_pending_orders():
    from .services import OrderService
    return OrderService.expire_stale_pending_orders()
