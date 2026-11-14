"""Central catalog of permission codenames and shared constants."""


class Perm:
    # Products & catalogue
    PRODUCTS_MANAGE = "products.manage"
    PRODUCTS_VIEW = "products.view"
    CATEGORIES_MANAGE = "categories.manage"
    MEDIA_MANAGE = "media.manage"
    # Inventory
    INVENTORY_MANAGE = "inventory.manage"
    INVENTORY_VIEW = "inventory.view"
    # Orders & fulfilment
    ORDERS_VIEW = "orders.view"
    ORDERS_MANAGE = "orders.manage"
    ORDERS_FULFIL = "orders.fulfil"
    REFUNDS_MANAGE = "refunds.manage"
    # Customers & engagement
    CUSTOMERS_VIEW = "customers.view"
    CUSTOMERS_MANAGE = "customers.manage"
    REVIEWS_MODERATE = "reviews.moderate"
    NOTIFICATIONS_MANAGE = "notifications.manage"
    # Commerce configuration
    PROMOTIONS_MANAGE = "promotions.manage"
    SHIPPING_MANAGE = "shipping.manage"
    CMS_MANAGE = "cms.manage"
    SEO_MANAGE = "seo.manage"
    # Finance
    FINANCE_VIEW = "finance.view"
    FINANCE_MANAGE = "finance.manage"
    REPORTS_VIEW = "reports.view"
    DASHBOARD_VIEW = "dashboard.view"
    # System
    STAFF_MANAGE = "staff.manage"
    SETTINGS_MANAGE = "settings.manage"
    AUDIT_VIEW = "audit.view"


ALL_PERMISSIONS = [v for k, v in vars(Perm).items() if not k.startswith("_")]

CURRENCY_NGN = "NGN"

DEFAULT_ROLES = {
    "Super Administrator": ALL_PERMISSIONS,
    "Manager": [
        Perm.PRODUCTS_VIEW, Perm.PRODUCTS_MANAGE, Perm.CATEGORIES_MANAGE,
        Perm.INVENTORY_VIEW, Perm.INVENTORY_MANAGE, Perm.ORDERS_VIEW,
        Perm.ORDERS_MANAGE, Perm.ORDERS_FULFIL, Perm.CUSTOMERS_VIEW,
        Perm.REVIEWS_MODERATE, Perm.PROMOTIONS_MANAGE, Perm.SHIPPING_MANAGE,
        Perm.DASHBOARD_VIEW, Perm.REPORTS_VIEW, Perm.FINANCE_VIEW,
        Perm.MEDIA_MANAGE, Perm.CMS_MANAGE, Perm.SEO_MANAGE,
        Perm.NOTIFICATIONS_MANAGE, Perm.REFUNDS_MANAGE,
    ],
    "Product Manager": [
        Perm.PRODUCTS_VIEW, Perm.PRODUCTS_MANAGE, Perm.CATEGORIES_MANAGE,
        Perm.MEDIA_MANAGE, Perm.INVENTORY_VIEW, Perm.DASHBOARD_VIEW,
    ],
    "Inventory Manager": [
        Perm.INVENTORY_VIEW, Perm.INVENTORY_MANAGE, Perm.PRODUCTS_VIEW,
        Perm.DASHBOARD_VIEW,
    ],
    "Order Manager": [
        Perm.ORDERS_VIEW, Perm.ORDERS_MANAGE, Perm.ORDERS_FULFIL,
        Perm.CUSTOMERS_VIEW, Perm.SHIPPING_MANAGE, Perm.DASHBOARD_VIEW,
    ],
    "Customer Support": [
        Perm.CUSTOMERS_VIEW, Perm.ORDERS_VIEW, Perm.NOTIFICATIONS_MANAGE,
        Perm.REVIEWS_MODERATE, Perm.DASHBOARD_VIEW,
    ],
    "Accountant": [
        Perm.FINANCE_VIEW, Perm.FINANCE_MANAGE, Perm.REPORTS_VIEW,
        Perm.ORDERS_VIEW, Perm.REFUNDS_MANAGE, Perm.DASHBOARD_VIEW,
    ],
}
