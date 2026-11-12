"""Housekeeping: removes expired idempotency reservations."""
from django.core.management.base import BaseCommand

from apps.core.idempotency import purge_expired


class Command(BaseCommand):
    help = "Delete expired idempotency keys."

    def handle(self, *args, **options):
        count = purge_expired()
        self.stdout.write(self.style.SUCCESS(f"Purged {count} expired idempotency key(s)."))
