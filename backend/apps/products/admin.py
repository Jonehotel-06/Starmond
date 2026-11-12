from django.contrib import admin

from apps.products.models import (
    Brand, Product, ProductAttribute, ProductAttributeValue, ProductImage, ProductVariation,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariationInline(admin.TabularInline):
    model = ProductVariation
    extra = 0
    filter_horizontal = ("attribute_values",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "price", "status", "is_featured", "sold_count")
    list_filter = ("status", "is_featured", "is_new_arrival", "product_type", "category")
    search_fields = ("name", "sku", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline, ProductVariationInline]
    readonly_fields = ("sold_count", "view_count", "rating_average", "rating_count", "published_at")


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    prepopulated_fields = {"slug": ("name",)}


class AttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 1


@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "input_type", "is_variation_axis")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [AttributeValueInline]
