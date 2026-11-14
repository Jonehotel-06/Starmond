from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Single user model for customers AND staff (roles distinguish access)."""

    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "accounts_user"
        indexes = [models.Index(fields=["is_active", "date_joined"])]

    def __str__(self):
        return self.email


class Permission(models.Model):
    """Business permission (distinct from Django model permissions)."""
    codename = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    group = models.CharField(max_length=60, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "accounts_permission"
        ordering = ["group", "codename"]

    def __str__(self):
        return self.codename


class Role(models.Model):
    name = models.CharField(max_length=60, unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")
    is_system = models.BooleanField(default=False, help_text="System roles cannot be deleted.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_role"
        ordering = ["name"]

    def __str__(self):
        return self.name


class StaffProfile(TimeStampedModel):
    """Extended staff record: role binding, employment status, notes."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="staff_profiles", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "accounts_staffprofile"

    def __str__(self):
        return f"{self.user.email} :: {self.role}"
