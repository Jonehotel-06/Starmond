"""
Identity, roles and staff authorisation.

The platform is single-owner but operated by a staff team, so roles are fully
configurable: a ``Role`` bundles Django permissions and staff members inherit
them through ``StaffProfile``.
"""
from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel, SoftDeleteModel, TimeStampedModel, UUIDModel

PHONE_VALIDATOR = RegexValidator(
    regex=r"^\+?[0-9]{7,15}$",
    message="Enter a valid phone number in international format, e.g. +2348012345678.",
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(str(email)).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, is_email_verified=True, is_active=True)
        user = self._create(email, password, **extra)
        super_role, _ = Role.objects.get_or_create(
            slug="super-admin",
            defaults={"name": "Super Administrator", "is_system": True,
                      "description": "Full unrestricted platform access."},
        )
        StaffProfile.objects.get_or_create(
            user=user, defaults={"role": super_role, "designation": "Platform Owner"}
        )
        return user

    def get_by_natural_key(self, username):
        return self.get(**{f"{self.model.USERNAME_FIELD}__iexact": username})


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """
    Single user table for customers and staff.

    Sequential ids are never exposed: ``id`` is a UUID.
    """

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        UNDISCLOSED = "undisclosed", "Prefer not to say"

    email = models.EmailField(unique=True, db_index=True)
    phone = models.CharField(max_length=16, blank=True, validators=[PHONE_VALIDATOR])
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Can access the admin dashboard.")
    is_email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    must_change_password = models.BooleanField(default=False)

    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    date_joined = models.DateTimeField(default=timezone.now)

    marketing_opt_in = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        db_table = "accounts_user"
        ordering = ["-date_joined"]
        indexes = [
            models.Index(fields=["is_active", "is_staff"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self) -> str:
        return self.email

    # -- naming ------------------------------------------------------------
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self) -> str:
        return self.full_name or self.email.split("@")[0]

    @property
    def initials(self) -> str:
        parts = [p for p in (self.first_name, self.last_name) if p]
        if parts:
            return "".join(p[0].upper() for p in parts[:2])
        return self.email[:2].upper()

    # -- security state ----------------------------------------------------
    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failed_login(self, threshold: int = 5, lock_minutes: int = 15) -> None:
        self.failed_login_attempts = models.F("failed_login_attempts") + 1
        self.save(update_fields=["failed_login_attempts"])
        self.refresh_from_db(fields=["failed_login_attempts"])
        if self.failed_login_attempts >= threshold:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=lock_minutes)
            self.save(update_fields=["locked_until"])

    def register_successful_login(self, ip: str | None = None) -> None:
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login_ip = ip
        self.last_login = timezone.now()
        self.save(update_fields=["failed_login_attempts", "locked_until", "last_login_ip", "last_login"])

    def mark_email_verified(self) -> None:
        if not self.is_email_verified:
            self.is_email_verified = True
            self.email_verified_at = timezone.now()
            self.save(update_fields=["is_email_verified", "email_verified_at"])

    # -- authorisation helpers --------------------------------------------
    @property
    def role(self):
        profile = getattr(self, "staff_profile", None)
        return profile.role if profile else None

    @property
    def role_slug(self) -> str:
        if self.is_superuser:
            return "super-admin"
        role = self.role
        return role.slug if role else ("customer" if not self.is_staff else "staff")


class Role(BaseModel):
    """
    A configurable bundle of Django permissions.

    New staff roles are created from the dashboard — no code change required.
    """

    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(
        "auth.Permission", blank=True, related_name="starmond_roles",
        help_text="Django permissions granted by this role.",
    )
    is_system = models.BooleanField(
        default=False, help_text="System roles cannot be deleted."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "accounts_role"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def permission_codenames(self) -> list[str]:
        return sorted(
            f"{p.content_type.app_label}.{p.codename}"
            for p in self.permissions.select_related("content_type")
        )

    def delete(self, *a, **kw):
        if self.is_system:
            raise PermissionError("System roles cannot be deleted. Deactivate it instead.")
        return super().delete(*a, **kw)


class StaffProfile(TimeStampedModel):
    """Extends a staff ``User`` with employment and role data."""

    class Department(models.TextChoices):
        MANAGEMENT = "management", "Management"
        OPERATIONS = "operations", "Operations"
        WAREHOUSE = "warehouse", "Warehouse"
        FINANCE = "finance", "Finance"
        SUPPORT = "support", "Customer Support"
        MARKETING = "marketing", "Marketing"
        IT = "it", "IT"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    role = models.ForeignKey(
        Role, null=True, blank=True, on_delete=models.PROTECT, related_name="members"
    )
    employee_code = models.CharField(max_length=32, unique=True, blank=True)
    designation = models.CharField(max_length=120, blank=True)
    department = models.CharField(max_length=30, choices=Department.choices, blank=True)
    can_process_refunds = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "accounts_staff_profile"

    def __str__(self) -> str:
        return f"{self.user.email} — {self.role.name if self.role else 'no role'}"

    def save(self, *a, **kw):
        if not self.employee_code:
            self.employee_code = f"STM-{uuid.uuid4().hex[:8].upper()}"
        return super().save(*a, **kw)
