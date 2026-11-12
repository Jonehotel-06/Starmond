"""Media library uploads (staff only) with type and size validation."""
from __future__ import annotations

import hashlib

from PIL import Image
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import ValidationError
from apps.core.permissions import IsStaff
from apps.core.views import BaseAPIView
from apps.media_lib.models import MediaAsset

ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/avif",
    "application/pdf",
}


class MediaUploadView(BaseAPIView):
    permission_classes = [IsStaff]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError("A file is required.")
        from django.conf import settings

        if upload.size > settings.MAX_UPLOAD_SIZE_BYTES:
            raise ValidationError(
                f"Files must be smaller than "
                f"{settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB."
            )
        content_type = getattr(upload, "content_type", "") or ""
        if content_type and content_type not in ALLOWED_MIME:
            raise ValidationError(f"Unsupported file type: {content_type}.")

        width = height = None
        if content_type.startswith("image/"):
            try:
                with Image.open(upload) as image:
                    image.verify()
                upload.seek(0)
                with Image.open(upload) as image:
                    width, height = image.size
                upload.seek(0)
            except Exception:
                raise ValidationError("The uploaded image could not be read.")

        digest = hashlib.sha256()
        for chunk in upload.chunks():
            digest.update(chunk)
        upload.seek(0)

        asset = MediaAsset.objects.create(
            file=upload,
            original_name=upload.name[:255],
            kind=request.data.get("kind", MediaAsset.Kind.OTHER),
            mime_type=content_type[:120],
            size_bytes=upload.size,
            width=width,
            height=height,
            alt_text=request.data.get("alt_text", "")[:200],
            title=request.data.get("title", "")[:200],
            uploaded_by=request.user,
            checksum=digest.hexdigest(),
        )
        return self.created(
            {"id": str(asset.pk), "url": asset.url, "width": width, "height": height,
             "size_bytes": asset.size_bytes},
            message="File uploaded.",
        )
