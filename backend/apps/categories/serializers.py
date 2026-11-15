from rest_framework import serializers

from .models import Category
from .services import CategoryService


class CategoryPublicSerializer(serializers.ModelSerializer):
    url_path = serializers.CharField(read_only=True)
    image_url = serializers.CharField(read_only=True)
    banner_image_url = serializers.CharField(read_only=True)
    children = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "image_url", "banner_image_url", "url_path",
                  "display_order", "children", "product_count"]

    def get_children(self, obj):
        if getattr(self, "_depth", 0) >= 2:
            return []
        children = [c for c in obj.children.all() if c.is_active]
        child_serializer = CategoryPublicSerializer(children, many=True, context=self.context)
        child_serializer._depth = getattr(self, "_depth", 0) + 1
        return child_serializer.data

    def get_product_count(self, obj):
        """Uses the annotated value when present (list/detail views annotate);
        nested children return None to avoid per-node COUNT queries."""
        annotated = getattr(obj, "annotated_product_count", None)
        return annotated


class CategoryStaffSerializer(serializers.ModelSerializer):
    url_path = serializers.CharField(read_only=True)
    seo = serializers.SerializerMethodField()

    slug = serializers.SlugField(required=False, allow_blank=True, max_length=140)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "image", "banner_image", "parent", "parent_name",
                  "display_order", "seo_title", "seo_description", "seo_keywords", "og_image", "canonical_url",
                  "is_active", "product_count", "url_path", "seo", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at", "url_path"]

    def get_seo(self, obj):
        return obj.effective_seo()

    def get_product_count(self, obj):
        # Annotated by the staff viewset; falls back to a query for single objects.
        count = getattr(obj, "direct_product_count", None)
        return obj.products.count() if count is None else count

    def validate(self, attrs):
        instance = self.instance or Category()
        name = attrs.get("name", getattr(instance, "name", ""))
        parent = attrs.get("parent", getattr(instance, "parent", None))
        if self.instance and parent and self.instance.pk:
            if parent.pk == self.instance.pk:
                raise serializers.ValidationError({"parent": "A category cannot be its own parent."})
        attrs["_name"] = name
        attrs["_parent"] = parent
        return attrs

    def create(self, validated_data):
        name = validated_data.pop("_name")
        parent = validated_data.pop("_parent")
        validated_data.pop("name", None)
        validated_data.pop("parent", None)
        slug = validated_data.pop("slug", None) or None
        images = {k: validated_data.pop(k) for k in ("image", "banner_image", "og_image") if k in validated_data}
        category = CategoryService.create_or_update(Category(), name=name, slug=slug, parent=parent, **validated_data)
        for k, v in images.items():
            setattr(category, k, v)
        category.save()
        return category

    def update(self, instance, validated_data):
        name = validated_data.pop("_name", instance.name)
        parent = validated_data.pop("_parent", instance.parent)
        validated_data.pop("name", None)
        validated_data.pop("parent", None)
        slug = validated_data.pop("slug", None) or None
        images = {k: validated_data.pop(k) for k in ("image", "banner_image", "og_image") if k in validated_data}
        category = CategoryService.create_or_update(instance, name=name, slug=slug, parent=parent, **validated_data)
        for k, v in images.items():
            setattr(category, k, v)
        category.save()
        return category
