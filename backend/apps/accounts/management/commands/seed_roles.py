"""Create the permission catalog and default roles (idempotent)."""
from django.core.management.base import BaseCommand

from apps.accounts.models import Permission, Role
from apps.core.constants import ALL_PERMISSIONS, DEFAULT_ROLES


class Command(BaseCommand):
    help = "Seed business permissions and default staff roles."

    def handle(self, *args, **options):
        for codename in ALL_PERMISSIONS:
            group, _, _ = codename.partition(".")
            Permission.objects.get_or_create(codename=codename, defaults={"name": codename.replace(".", " ").title(), "group": group})
        created = 0
        for name, codenames in DEFAULT_ROLES.items():
            role, was_created = Role.objects.get_or_create(name=name, defaults={"is_system": True})
            if was_created:
                created += 1
            role.permissions.set(Permission.objects.filter(codename__in=codenames))
        self.stdout.write(self.style.SUCCESS(f"Permissions: {Permission.objects.count()}, roles created: {created}, total roles: {Role.objects.count()}"))
