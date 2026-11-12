"""
Safety net for missed or failed webhooks.

Re-verifies every still-pending payment against Paystack and settles the ones
that were genuinely paid. Never marks anything paid without provider proof.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.exceptions import PaymentError
from apps.payments.models import Payment
from apps.payments.services import PaymentService


class Command(BaseCommand):
    help = "Re-verify pending Paystack payments and settle confirmed ones."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=15,
                            help="Only look at payments created longer ago than this.")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=options["minutes"])
        pending = Payment.objects.filter(
            status__in=[Payment.Status.PENDING, Payment.Status.INITIALIZED],
            created_at__lte=cutoff,
        ).select_related("order")

        settled = failed = skipped = 0
        for payment in pending.iterator():
            if payment.order.is_paid:
                skipped += 1
                continue
            try:
                result = PaymentService.verify_payment(payment.reference, source="reconcile")
                settled += 1 if result.is_successful else 0
            except PaymentError:
                failed += 1
            except Exception:  # pragma: no cover
                failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Checked {pending.count()} pending payment(s): "
            f"{settled} settled, {failed} unresolved, {skipped} skipped."
        ))
