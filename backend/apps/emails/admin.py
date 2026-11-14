from django.contrib import admin
from .models import EmailLog
@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ["recipient", "template_key", "status", "attempts", "created_at"]
    list_filter = ["status", "template_key"]
