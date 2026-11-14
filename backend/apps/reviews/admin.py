from django.contrib import admin
from .models import Review
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["product", "customer", "rating", "moderation_status", "is_verified_purchase", "created_at"]
    list_filter = ["moderation_status"]
