from django.contrib import admin
from .models import ShippingMethod, ShippingZone
admin.site.register(ShippingZone)
admin.site.register(ShippingMethod)
