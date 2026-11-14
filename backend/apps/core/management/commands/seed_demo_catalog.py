"""DEV/STAGING convenience: seed the documented example catalogue, shipping
zones for Nigerian states, policy pages and business settings so the frontend
team can integrate immediately. NOT for production — real data is entered by
the business owner through the admin APIs.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

CATALOGUE = {
    "electrical": ("Electrical & Electrical Accessories", {
        "cables": ("Electrical Cables", [("Copper Cable 2.5mm (30m roll)", "CBL-2530", "28500.00"),
                                          ("Copper Cable 4mm (30m roll)", "CBL-4030", "41000.00")]),
        "switches-sockets": ("Switches & Sockets", [("13A Single Socket", "SCK-13A", "2500.00"),
                                                     ("Double Switch 10A", "SWT-2G", "3200.00")]),
        "breakers": ("Circuit Breakers", [("MCB 32A Single Pole", "MCB-32", "6500.00")]),
        "lighting": ("Lighting & Bulbs", [("LED Bulb 9W", "BLB-9W", "1500.00", "1200.00")]),
    }),
    "fashion": ("Fashion Design & Clothing", {
        "mens-wear": ("Men's Clothing", [("Men's Senator Wear (Custom)", "FSH-SEN", "85000.00")]),
        "womens-wear": ("Women's Clothing", [("Ladies Gown — Ankara", "FSH-ANK", "45000.00")]),
        "fabrics": ("Fabrics", [("Premium Cotton Fabric (5 yards)", "FAB-CTN", "18000.00")]),
    }),
    "electronics": ("Electronics & Gadgets", {
        "phones": ("Phones", [("Smartphone X100 — 128GB", "PHN-X100", "185000.00", "169999.00")]),
        "laptops": ("Laptops", [("Laptop Pro 14 — 16GB/512GB", "LPT-PRO14", "650000.00")]),
        "accessories": ("Chargers & Accessories", [("Fast Charger 65W", "CHG-65W", "12500.00")]),
    }),
    "fashion-accessories": ("Fashion Accessories", {
        "shoes": ("Shoes", [("Men's Leather Shoes", "SHO-LTR", "35000.00")]),
        "watches": ("Wristwatches", [("Classic Wristwatch", "WCH-CLS", "27500.00")]),
    }),
    "home": ("Home & Household Products", {
        "appliances": ("Home Appliances", [("Standing Fan 18\"", "FAN-18", "52000.00")]),
        "kitchen": ("Kitchen Accessories", [("Non-stick Pot Set (5 pcs)", "POT-SET5", "38000.00")]),
    }),
}

NG_STATES = ["Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
             "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "Gombe", "Imo", "Jigawa",
             "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger",
             "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe",
             "Zamfara", "Abuja FCT"]


class Command(BaseCommand):
    help = "Seed a demo catalogue for development/staging integration."

    def handle(self, *args, **options):
        from apps.categories.models import Category
        from apps.cms.models import Page
        from apps.cms.services import BusinessSettingsService
        from apps.inventory.services import InventoryService
        from apps.products.models import Product
        from apps.shipping.models import ShippingMethod, ShippingZone

        products_created = 0
        for root_slug, (root_name, subs) in CATALOGUE.items():
            root, _ = Category.objects.get_or_create(slug=root_slug, defaults={"name": root_name, "is_active": True})
            for sub_slug, (sub_name, items) in subs.items():
                sub, _ = Category.objects.get_or_create(slug=sub_slug, defaults={"name": sub_name, "parent": root, "is_active": True})
                for item in items:
                    name, sku, price = item[0], item[1], item[2]
                    sale = item[3] if len(item) > 3 else None
                    product, created = Product.objects.get_or_create(sku=sku, defaults={
                        "name": name, "slug": sku.lower().replace(".", "-").replace("_", "-"),
                        "category": sub, "regular_price": Decimal(price),
                        "sale_price": Decimal(sale) if sale else None,
                        "short_description": f"{name} — genuine product from STARMOND TECHNOLOGY LIMITED.",
                        "description": f"{name}. Quality guaranteed. Nationwide delivery.",
                        "status": Product.Status.ACTIVE, "is_new_arrival": True,
                        "low_stock_threshold": 5,
                    })
                    if created:
                        products_created += 1
                    InventoryService.ensure_inventory(product, None, opening=25)

        # Shipping: Lagos zone (standard/express) + nationwide standard + pickup
        lagos, _ = ShippingZone.objects.get_or_create(name="Lagos & Ogun", defaults={"states": ["Lagos", "Ogun"]})
        south, _ = ShippingZone.objects.get_or_create(name="South & East", defaults={"states": [s for s in NG_STATES if s not in ("Lagos", "Ogun")] + ["Abuja FCT"]})
        ShippingMethod.objects.get_or_create(name="Standard — Lagos/Ogun", defaults={
            "kind": ShippingMethod.Kind.STANDARD, "zone": lagos, "fee": Decimal("2500.00"),
            "free_above_amount": Decimal("150000.00"), "min_days": 1, "max_days": 3})
        ShippingMethod.objects.get_or_create(name="Express — Lagos/Ogun", defaults={
            "kind": ShippingMethod.Kind.EXPRESS, "zone": lagos, "fee": Decimal("5000.00"),
            "min_days": 1, "max_days": 1})
        ShippingMethod.objects.get_or_create(name="Standard — Nationwide", defaults={
            "kind": ShippingMethod.Kind.STANDARD, "zone": south, "fee": Decimal("4500.00"),
            "free_above_amount": Decimal("250000.00"), "min_days": 3, "max_days": 7})
        ShippingMethod.objects.get_or_create(name="Pickup — Store collection", defaults={
            "kind": ShippingMethod.Kind.PICKUP, "zone": None, "fee": Decimal("0.00"),
            "min_days": 0, "max_days": 0, "pickup_address": "Contact support for pickup address after confirmation."})

        # Policy pages
        pages = [("About Us", "about-us", "STARMOND TECHNOLOGY LIMITED is a Nigerian multi-category online retail business."),
                 ("Contact Us", "contact-us", "Reach us through the contact details published on this site."),
                 ("Privacy Policy", "privacy-policy", "We process personal data only to fulfil orders and improve service."),
                 ("Terms & Conditions", "terms-conditions", "By purchasing you agree to our published terms."),
                 ("Shipping Policy", "shipping-policy", "Delivery times vary by zone and are quoted at checkout."),
                 ("Returns & Refund Policy", "returns-refund-policy", "Refund requests are reviewed per this policy and processed via the original payment provider.")]
        for title, slug, body in pages:
            Page.objects.get_or_create(slug=slug, defaults={"title": title, "body": f"<p>{body}</p>", "excerpt": body, "is_published": True})

        BusinessSettingsService.update({
            "business_name": "STARMOND TECHNOLOGY LIMITED",
            "homepage_hero": {"title": "Everything you need, delivered nationwide",
                              "subtitle": "Electrical, fashion, electronics and home products.",
                              "cta_label": "Shop now", "cta_url": "/shop/", "image_key": ""},
        })
        self.stdout.write(self.style.SUCCESS(
            f"Demo catalogue seeded: {Category.objects.count()} categories, {products_created} new products, "
            f"{ShippingMethod.objects.count()} shipping methods, {Page.objects.count()} pages."))
