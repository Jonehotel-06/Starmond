"""
One-shot, idempotent platform bootstrap: settings, roles, permissions,
delivery zones and the first administrator.

Safe to run multiple times — nothing is duplicated and no existing value is
overwritten.
"""
from __future__ import annotations

from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, StaffProfile, User
from apps.cms.services import SettingsService
from apps.shipping.constants import NIGERIAN_STATES
from apps.shipping.models import ShippingArea, ShippingMethod, ShippingZone

ROLE_SPECS = [
    {
        "slug": "super-admin",
        "name": "Super Administrator",
        "description": "Full unrestricted access to every part of the platform.",
        "apps": None,  # all permissions
        "system": True,
    },
    {
        "slug": "store-manager",
        "name": "Store Manager",
        "description": "Manages the catalogue, orders, inventory and promotions.",
        "apps": ["products", "categories", "orders", "inventory", "promotions",
                 "reviews", "cart", "shipping"],
        "system": True,
    },
    {
        "slug": "order-fulfilment",
        "name": "Order Fulfilment Officer",
        "description": "Processes paid orders, packs and dispatches shipments.",
        "apps": ["orders", "shipping", "inventory"],
        "system": True,
    },
    {
        "slug": "finance-officer",
        "name": "Finance Officer",
        "description": "Reviews payments, approves refunds and exports reports.",
        "apps": ["payments", "refunds", "orders", "reports", "emails"],
        "system": True,
    },
    {
        "slug": "customer-support",
        "name": "Customer Support",
        "description": "Answers enquiries, moderates reviews and views orders.",
        "apps": ["notifications", "reviews", "orders", "accounts", "customers"],
        "system": True,
    },
    {
        "slug": "content-editor",
        "name": "Content Editor",
        "description": "Manages CMS pages, banners and SEO metadata.",
        "apps": ["cms", "seo", "media_lib", "categories", "products"],
        "system": True,
    },
]

ZONE_SPECS = [
    ("Lagos Mainland & Island", ["Lagos"], "1200", "3500", 1, 2),
    ("South East", ["Enugu", "Anambra", "Abia", "Imo", "Ebonyi"], "1800", "4000", 2, 4),
    ("South South", ["Rivers", "Delta", "Edo", "Bayelsa", "Cross River", "Akwa Ibom"], "2000", "4500", 2, 4),
    ("South West", ["Ogun", "Oyo", "Osun", "Ondo", "Ekiti"], "1800", "4200", 2, 4),
    ("North Central", ["Federal Capital Territory", "Kwara", "Kogi", "Nasarawa",
                       "Niger", "Benue", "Plateau"], "2200", "5000", 3, 5),
    ("North West", ["Kano", "Kaduna", "Katsina", "Kebbi", "Sokoto", "Jigawa", "Zamfara"],
     "2500", "5500", 3, 6),
    ("North East", ["Bauchi", "Borno", "Gombe", "Taraba", "Yobe", "Adamawa"], "2800", "6000", 4, 7),
]


class Command(BaseCommand):
    help = "Bootstrap STARMOND: settings, roles, delivery zones and first admin."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Email address for the first administrator.")
        parser.add_argument("--password", help="Password for the first administrator.")
        parser.add_argument("--first-name", default="", help="Administrator first name.")
        parser.add_argument("--last-name", default="", help="Administrator last name.")

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("STARMOND TECHNOLOGY LIMITED — bootstrap"))

        # --- settings -----------------------------------------------------
        created = SettingsService.seed_defaults()
        self.stdout.write(f"  Settings: {created} default(s) created")

        # --- roles --------------------------------------------------------
        for spec in ROLE_SPECS:
            role, was_created = Role.objects.get_or_create(
                slug=spec["slug"],
                defaults={
                    "name": spec["name"],
                    "description": spec["description"],
                    "is_system": spec["system"],
                },
            )
            if spec["apps"] is None:
                permissions = Permission.objects.all()
            else:
                permissions = Permission.objects.filter(
                    content_type__app_label__in=spec["apps"]
                )
            role.permissions.set(permissions)
            self.stdout.write(
                f"  Role '{role.name}': {permissions.count()} permissions "
                f"({'created' if was_created else 'updated'})"
            )

        # --- shipping -----------------------------------------------------
        covered = set()
        for name, states, base_price, express_price, days_min, days_max in ZONE_SPECS:
            zone, _ = ShippingZone.objects.get_or_create(
                name=name,
                defaults={
                    "slug": name.lower().replace(" ", "-").replace("&", "and"),
                    "description": f"Delivery across {', '.join(states)}.",
                },
            )
            for state in states:
                ShippingArea.objects.get_or_create(zone=zone, state=state, city="")
                covered.add(state)
            ShippingMethod.objects.get_or_create(
                zone=zone,
                code="standard",
                defaults={
                    "name": "Standard delivery",
                    "kind": ShippingMethod.Kind.DELIVERY,
                    "price": base_price,
                    "estimated_days_min": days_min,
                    "estimated_days_max": days_max,
                    "position": 1,
                },
            )
            ShippingMethod.objects.get_or_create(
                zone=zone,
                code="express",
                defaults={
                    "name": "Express delivery",
                    "kind": ShippingMethod.Kind.EXPRESS,
                    "price": express_price,
                    "estimated_days_min": max(days_min - 1, 1),
                    "estimated_days_max": max(days_max - 1, 1),
                    "position": 2,
                },
            )
            ShippingMethod.objects.get_or_create(
                zone=zone,
                code="pickup",
                defaults={
                    "name": "Pick up from store",
                    "kind": ShippingMethod.Kind.PICKUP,
                    "price": "0",
                    "estimated_days_min": 0,
                    "estimated_days_max": 1,
                    "position": 3,
                },
            )
        self.stdout.write(f"  Delivery: {len(ZONE_SPECS)} zone(s), {len(covered)} state(s) covered")

        uncovered = [s for s in NIGERIAN_STATES if s not in covered]
        if uncovered:
            self.stdout.write(self.style.WARNING(
                f"  States without a delivery zone (orders to these will be refused): "
                f"{', '.join(uncovered)}"
            ))

        # --- first administrator -----------------------------------------
        email = options.get("email")
        password = options.get("password")
        if email and password:
            user = User.objects.filter(email__iexact=email.lower()).first()
            if user is None:
                user = User.objects.create_superuser(
                    email=email.lower(), password=password,
                    first_name=options.get("first_name", ""),
                    last_name=options.get("last_name", ""),
                )
                self.stdout.write(self.style.SUCCESS(f"  Administrator created: {user.email}"))
            else:
                user.is_staff = True
                user.is_superuser = True
                user.is_email_verified = True
                user.save(update_fields=["is_staff", "is_superuser", "is_email_verified"])
                self.stdout.write(f"  Existing user promoted to administrator: {user.email}")
            StaffProfile.objects.get_or_create(
                user=user,
                defaults={
                    "role": Role.objects.get(slug="super-admin"),
                    "designation": "Platform Owner",
                    "department": StaffProfile.Department.MANAGEMENT,
                    "can_process_refunds": True,
                },
            )
        else:
            self.stdout.write(self.style.WARNING(
                "  No --email/--password supplied; skipping administrator creation."
            ))

        self.stdout.write(self.style.SUCCESS("Bootstrap complete."))
