from rest_framework import serializers

from apps.categories.models import Category


class CategoryListSerializer(serializers.ModelSerializer):
    url = serializers.CharField(source="absolute_path", read_only=True)
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "path", "depth", "url", "image",
                  "short_description", "is_featured", "product_count"]


class CategoryDetailSerializer(serializers.ModelSerializer):
    url = serializers.CharField(source="absolute_path", read_only=True)
    breadcrumb = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    product_count = serializers.IntegerField(read_only=True)
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "path", "depth", "url", "description",
                  "short_description", "image", "icon", "breadcrumb", "children",
                  "product_count", "meta_title", "meta_description", "updated_at"]

    def get_breadcrumb(self, obj):
        return obj.breadcrumb()

    def get_children(self, obj):
        return CategoryListSerializer(
            obj.children.filter(is_active=True, status="published").order_by("position", "name"),
            many=True, context=self.context,
        ).data

    def get_meta_title(self, obj):
        return obj.meta_title or obj.name

    def get_meta_description(self, obj):
        return obj.meta_description or obj.short_description or obj.description[:300]
