from django.contrib import admin
from .models import Address, CustomerProfile, Wishlist, WishlistItem
admin.site.register(CustomerProfile)
admin.site.register(Address)
admin.site.register(Wishlist)
admin.site.register(WishlistItem)
