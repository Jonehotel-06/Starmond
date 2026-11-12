"""Integrity check: cached reservation counters vs. actual active reservations."""
from django.core.management.base import BaseCommand

from apps.inventory.models import Inventory
from apps.inventory.services import InventoryService


class Command(BaseCommand):
    help = "Verify inventory integrity and report any drift."

    def handle(self, *args, **options):
        problems = []
        for inventory in Inventory.objects.select_related("product", "variation").iterator():
            report = InventoryService.reconcile(inventory)
            if not report["consistent"]:
                problems.append(report)

        if not problems:
            self.stdout.write(self.style.SUCCESS("Inventory is consistent."))
            return
        self.stdout.write(self.style.ERROR(f"{len(problems)} inventory record(s) drifted:"))
        for problem in problems:
            self.stdout.write(
                f"  {problem['inventory_id']}: counter={problem['counter_reserved']} "
                f"active={problem['active_reservations']} drift={problem['drift']}"
            )
