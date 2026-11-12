"""Releases stock holds for unpaid orders whose reservation window has lapsed."""
from django.core.management.base import BaseCommand

from apps.inventory.services import InventoryService


class Command(BaseCommand):
    help = "Release expired inventory reservations."

    def handle(self, *args, **options):
        result = InventoryService.expire_stale_reservations()
        self.stdout.write(self.style.SUCCESS(f"Expired reservations: {result['expired_reservations']}"))
