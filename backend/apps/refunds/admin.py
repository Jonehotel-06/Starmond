from django.contrib import admin
from .models import Refund
@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["reference", "order", "requested_amount", "approved_amount", "status", "created_at"]
    list_filter = ["status"]
