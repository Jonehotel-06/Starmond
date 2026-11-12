"""Polls Paystack for the true state of in-flight refunds."""
from django.core.management.base import BaseCommand

from apps.refunds.services import RefundService


class Command(BaseCommand):
    help = "Reconcile submitted refunds against Paystack's final state."

    def handle(self, *args, **options):
        result = RefundService.reconcile_pending()
        self.stdout.write(self.style.SUCCESS(
            f"Refunds checked: {result['checked']}, completed: {result['completed']}, "
            f"failed: {result['failed']}, unchanged: {result['unchanged']}"
        ))
