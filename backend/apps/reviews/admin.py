from django.contrib import admin

from apps.reviews.models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "is_verified_purchase",
                    "moderation_status", "helpful_count", "created_at")
    list_filter = ("moderation_status", "is_verified_purchase", "rating")
    search_fields = ("product__name", "user__email", "comment")
    actions = ["approve_reviews", "reject_reviews"]

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        for review in queryset:
            from apps.reviews.services import ReviewService

            ReviewService.moderate(review, approved=True, moderator=request.user)

    @admin.action(description="Reject selected reviews")
    def reject_reviews(self, request, queryset):
        for review in queryset:
            from apps.reviews.services import ReviewService

            ReviewService.moderate(review, approved=False, moderator=request.user)
