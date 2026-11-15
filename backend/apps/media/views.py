import django_filters as filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.exceptions import ServiceError
from apps.core.permissions import IsStaffWithPermission, user_has_permission

from .models import MediaAsset
from .serializers import MediaAssetSerializer
from .services import SIGNED_URL_TTL_SECONDS, MediaService, MediaValidationError


class MediaAssetFilter(filters.FilterSet):
    date_from = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")

    class Meta:
        model = MediaAsset
        fields = ["kind", "visibility"]


class MediaUploadView(APIView):
    """POST /api/media/uploads/ — multipart image upload.

    Staff with media.manage may upload any kind (public bucket).
    Authenticated customers may upload private reference images only.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get("file") or request.FILES.get("image")
        if file is None:
            raise ServiceError("No image file provided (field: file).", code="missing_files")
        is_staff = user_has_permission(request.user, Perm.MEDIA_MANAGE)
        kind = request.data.get("kind") or (MediaAsset.Kind.OTHER if is_staff else MediaAsset.Kind.REFERENCE_IMAGE)
        if kind not in MediaAsset.Kind.values:
            raise ServiceError("Unknown media kind.", code="invalid_media", fields={"kind": ["Unknown media kind."]})
        if not is_staff and kind != MediaAsset.Kind.REFERENCE_IMAGE:
            raise ServiceError("You may only upload reference images.", code="permission_denied",
                               status_code=status.HTTP_403_FORBIDDEN)
        visibility = (MediaAsset.Visibility.PRIVATE if kind == MediaAsset.Kind.REFERENCE_IMAGE
                      else MediaAsset.Visibility.PUBLIC)
        try:
            asset = MediaService.upload(
                file, kind=kind, visibility=visibility, uploaded_by=request.user,
                alt_text=request.data.get("alt_text", ""),
                related_object_type=request.data.get("related_object_type", ""),
                related_object_id=request.data.get("related_object_id", ""),
            )
        except MediaValidationError as exc:
            raise ServiceError(str(exc), code="invalid_media", fields={"file": [str(exc)]})
        if is_staff:
            AuditService.log(request.user, "media.upload", "MediaAsset", asset.pk,
                             {"kind": kind, "name": asset.original_name}, request=request)
        return Response(MediaAssetSerializer(asset, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)


class MediaAssetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                        viewsets.GenericViewSet):
    """Staff media library (list, inspect, edit alt text, signed URL, remove)."""
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.MEDIA_MANAGE
    serializer_class = MediaAssetSerializer
    queryset = MediaAsset.objects.select_related("uploaded_by").all()
    filterset_class = MediaAssetFilter
    search_fields = ["original_name", "alt_text"]
    ordering_fields = ["created_at", "size_bytes", "original_name"]
    ordering = ["-created_at"]
    http_method_names = ["get", "patch", "post", "delete", "head", "options"]

    def perform_update(self, serializer):
        asset = serializer.save()
        AuditService.log(self.request.user, "media.update", "MediaAsset", asset.pk, request=self.request)

    @action(detail=True, methods=["post"], url_path="signed-url")
    def signed_url(self, request, pk=None):
        asset = self.get_object()
        data = MediaAssetSerializer(asset, context={"request": request}).data
        url = MediaService.signed_url(asset)
        data["signed_url"] = request.build_absolute_uri(url) if url.startswith("/") else url
        data["expires_in"] = SIGNED_URL_TTL_SECONDS
        return Response(data)

    @action(detail=True, methods=["delete"], url_path="remove")
    def remove(self, request, pk=None):
        asset = self.get_object()
        if asset.order_items.exists():
            raise ServiceError("This image is attached to an order and cannot be removed.",
                               code="media_in_use", status_code=status.HTTP_409_CONFLICT)
        AuditService.log(request.user, "media.delete", "MediaAsset", asset.pk,
                         {"name": asset.original_name}, request=request)
        MediaService.delete(asset)
        return Response(status=status.HTTP_204_NO_CONTENT)
