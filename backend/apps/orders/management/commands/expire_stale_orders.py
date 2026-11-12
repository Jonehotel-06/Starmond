"""Lapses unpaid orders past their payment window and returns their stock."""
from django.core.management.base import BaseCommand

from apps.orders.services import OrderService


class Command(BaseCommand):
    help = "Expire unpaid orders whose payment window has passed."

    def handle(self, *args, **options):
        result = OrderService.expire_stale_orders()
        self.stdout.write(self.style.SUCCESS(f"Expired orders: {result['expired_orders']}"))
