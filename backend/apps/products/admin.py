from django.contrib import admin
from .models import Product, ProductAttribute, ProductAttributeValue, ProductImage, ProductVariation

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0

class ProductVariationInline(admin.TabularInline):
    model = ProductVariation
    extra = 0

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "sku", "category", "regular_price", "sale_price", "status", "is_featured"]
    list_filter = ["status", "is_featured", "category"]
    search_fields = ["name", "sku", "brand"]
    inlines = [ProductImageInline, ProductVariationInline]

admin.site.register(ProductAttribute)
admin.site.register(ProductAttributeValue)
admin.site.register(ProductImage)
admin.site.register(ProductVariation)
