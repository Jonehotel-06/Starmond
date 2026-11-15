"""MediaService — upload validation, safe naming, thumbnails, signed URLs, cleanup.

Uploads are validated by CONTENT (decoded with Pillow), never by the
client-supplied filename or Content-Type alone. Object keys are generated
server-side (UUID based) so user input never reaches the storage path.
"""
import io
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.utils import timezone

logger = logging.getLogger("starmond.media")

FORMAT_TO_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "AVIF": "image/avif"}
MIME_TO_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/avif": "avif"}
THUMBNAIL_SIZE = (480, 480)
SIGNED_URL_TTL_SECONDS = 600


class MediaValidationError(Exception):
    """Raised when an upload is not an acceptable image."""


class MediaService:
    # ----------------------------------------------------------- validation
    @staticmethod
    def validate_image(file):
        """Validate size, real content type and dimensions.

        Returns {"mime_type", "width", "height", "size_bytes"}. The file
        pointer is rewound so the caller can store the upload afterwards.
        """
        from PIL import Image, UnidentifiedImageError

        if file is None:
            raise MediaValidationError("No file was provided.")
        size = getattr(file, "size", None)
        if size is None:
            file.seek(0, io.SEEK_END)
            size = file.tell()
        if not size:
            raise MediaValidationError("The uploaded file is empty.")
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if size > max_bytes:
            raise MediaValidationError(f"Images must be {settings.MAX_UPLOAD_SIZE_MB} MB or smaller.")
        try:
            file.seek(0)
            with Image.open(file) as probe:
                probe.verify()  # integrity check; the image is unusable afterwards
            file.seek(0)
            with Image.open(file) as image:
                image_format = (image.format or "").upper()
                width, height = image.size
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
            raise MediaValidationError("The file is not a valid image.")
        finally:
            try:
                file.seek(0)
            except Exception:  # pragma: no cover - defensive
                pass
        mime = FORMAT_TO_MIME.get(image_format)
        if mime not in settings.ALLOWED_IMAGE_MIME_TYPES:
            raise MediaValidationError("Only JPEG, PNG, WebP and AVIF images are allowed.")
        if width < 1 or height < 1 or max(width, height) > settings.MAX_IMAGE_DIMENSION:
            raise MediaValidationError(
                f"Image dimensions must not exceed {settings.MAX_IMAGE_DIMENSION}px on either side.")
        return {"mime_type": mime, "width": width, "height": height, "size_bytes": size}

    # ----------------------------------------------------------- storage helpers
    @staticmethod
    def _storage(visibility):
        return storages["private_media" if visibility == "private" else "default"]

    @staticmethod
    def public_url(key):
        if not key:
            return None
        return storages["default"].url(key)

    @staticmethod
    def _build_key(kind, visibility, mime, suffix=""):
        now = timezone.now()
        ext = MIME_TO_EXT.get(mime, "bin")
        prefix = "private" if visibility == "private" else "library"
        return f"{prefix}/{kind}/{now:%Y/%m}/{uuid.uuid4().hex}{suffix}.{ext}"

    @staticmethod
    def _make_thumbnail(file):
        from PIL import Image, ImageOps
        try:
            file.seek(0)
            with Image.open(file) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                image.thumbnail(THUMBNAIL_SIZE)
                buffer = io.BytesIO()
                image.save(buffer, format="WEBP", quality=80, method=4)
                return buffer.getvalue()
        except Exception:
            logger.warning("Thumbnail generation failed", exc_info=True)
            return None
        finally:
            file.seek(0)

    # ----------------------------------------------------------- operations
    @classmethod
    def upload(cls, file, *, kind, visibility, uploaded_by=None, alt_text="",
               related_object_type="", related_object_id=""):
        from .models import MediaAsset

        meta = cls.validate_image(file)
        storage = cls._storage(visibility)
        key = storage.save(cls._build_key(kind, visibility, meta["mime_type"]), file)
        thumb_key = ""
        thumb = cls._make_thumbnail(file)
        if thumb:
            try:
                thumb_key = storage.save(cls._build_key(kind, visibility, "image/webp", "_thumb"), ContentFile(thumb))
            except Exception:
                logger.warning("Thumbnail upload failed", exc_info=True)
        original_name = (getattr(file, "name", "") or "upload").replace("\\", "/").split("/")[-1][:255]
        return MediaAsset.objects.create(
            kind=kind, visibility=visibility, status=MediaAsset.Status.READY,
            object_key=key, thumbnail_key=thumb_key, original_name=original_name,
            mime_type=meta["mime_type"], size_bytes=meta["size_bytes"],
            width=meta["width"], height=meta["height"], alt_text=(alt_text or "")[:255],
            related_object_type=(related_object_type or "")[:80],
            related_object_id=str(related_object_id or "")[:64],
            uploaded_by=uploaded_by if getattr(uploaded_by, "is_authenticated", False) else None,
        )

    @classmethod
    def asset_url(cls, asset, thumbnail=False):
        """Public assets resolve to their CDN/public URL. Private assets never
        expose a permanent URL — use `signed_url` instead."""
        if asset.visibility == "private":
            return ""
        key = (asset.thumbnail_key or asset.object_key) if thumbnail else asset.object_key
        try:
            return cls.public_url(key) or ""
        except Exception:  # pragma: no cover - defensive
            return ""

    @classmethod
    def signed_url(cls, asset, thumbnail=False):
        """Short-lived URL. With B2 configured the private storage issues a
        presigned URL (querystring_auth, 10 minute expiry)."""
        key = (asset.thumbnail_key or asset.object_key) if thumbnail else asset.object_key
        return cls._storage(asset.visibility).url(key)

    @classmethod
    def delete(cls, asset):
        storage = cls._storage(asset.visibility)
        for key in (asset.object_key, asset.thumbnail_key):
            if not key:
                continue
            try:
                storage.delete(key)
            except Exception:
                logger.warning("Could not delete media object %s", key, exc_info=True)
        asset.delete()

    @classmethod
    def cleanup_orphans(cls, older_than_hours=24):
        from .models import MediaAsset
        cutoff = timezone.now() - timedelta(hours=older_than_hours)
        stale = MediaAsset.objects.filter(status=MediaAsset.Status.FAILED, created_at__lt=cutoff)
        count = 0
        for asset in stale:
            cls.delete(asset)
            count += 1
        return count
