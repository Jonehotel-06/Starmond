"""
AccountService — registration, verification, password lifecycle, roles.

Tokens are stored only as SHA-256 hashes and are single-use with a hard expiry,
so a leaked database dump cannot be used to hijack accounts.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Role, StaffProfile
from apps.audit.services import AuditService
from apps.core.exceptions import (
    AuthenticationRequired,
    ConflictError,
    NotFound,
    PermissionDeniedError,
    ValidationError,
)
from apps.customers.models import CustomerProfile, OneTimeToken

logger = logging.getLogger("apps.accounts")
User = get_user_model()

EMAIL_VERIFICATION_HOURS = 24
PASSWORD_RESET_HOURS = 2


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AccountService:
    # ------------------------------------------------------------------
    # Tokens
    # ------------------------------------------------------------------
    @staticmethod
    def issue_token(*, purpose: str, user=None, guest_email: str = "",
                    target_reference: str = "", hours: int = 24, **metadata) -> str:
        """Creates a single-use token and returns the raw value exactly once."""
        raw = secrets.token_urlsafe(32)
        OneTimeToken.objects.create(
            user=user if getattr(user, "pk", None) else None,
            guest_email=guest_email.lower()[:254],
            purpose=purpose,
            token_hash=_hash(raw),
            target_reference=target_reference[:64],
            expires_at=timezone.now() + timedelta(hours=hours),
            metadata=metadata or None,
        )
        return raw

    @staticmethod
    def consume_token(raw: str, *, purpose: str) -> OneTimeToken:
        token = OneTimeToken.objects.filter(
            token_hash=_hash(raw or ""), purpose=purpose
        ).first()
        if token is None:
            raise ValidationError("This link is invalid.")
        if not token.is_valid:
            raise ValidationError("This link has expired or has already been used.")
        if not token.consume():
            raise ValidationError("This link has already been used.")
        return token

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def register(*, email: str, password: str, first_name: str = "", last_name: str = "",
                 phone: str = "", marketing_opt_in: bool = False, request=None) -> tuple[User, str]:
        email = (email or "").strip().lower()
        if not email:
            raise ValidationError({"email": ["An email address is required."]})
        if User.objects.filter(email__iexact=email).exists():
            raise ConflictError("An account with this email address already exists.")

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise ValidationError({"password": list(exc.messages)})

        try:
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=(first_name or "").strip()[:80],
                last_name=(last_name or "").strip()[:80],
                phone=(phone or "").strip()[:16],
                marketing_opt_in=marketing_opt_in,
            )
        except IntegrityError:
            raise ConflictError("An account with this email address already exists.")

        CustomerProfile.objects.create(user=user)
        raw_token = AccountService.issue_token(
            purpose=OneTimeToken.Purpose.EMAIL_VERIFICATION,
            user=user, hours=EMAIL_VERIFICATION_HOURS,
        )
        verify_url = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"
        try:
            from apps.notifications.services import NotificationService

            NotificationService.welcome(user, verify_url)
        except Exception:  # pragma: no cover
            logger.exception("Welcome email failed for %s", user.pk)

        AuditService.record(
            action="create", entity_type="user", entity_id=user.pk, actor=user,
            summary=f"Customer account created: {email}",
        )
        return user, raw_token

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    @staticmethod
    def authenticate(*, email: str, password: str, ip: str | None = None) -> User:
        email = (email or "").strip().lower()
        user = User.objects.filter(email__iexact=email).first()

        if user is None:
            # Constant-ish work factor so response time does not reveal existence.
            check_password(password or "", "pbkdf2_sha256$600000$abcdefghijklmnop$" + "0" * 64)
            AuditService.record(
                action="login_failed", entity_type="user", entity_id="",
                summary=f"Login attempt for unknown email {email[:100]}",
                metadata={"ip": ip},
            )
            raise AuthenticationRequired("Invalid email address or password.")

        if user.is_locked:
            raise PermissionDeniedError(
                "This account is temporarily locked after too many failed attempts. "
                "Please try again later or reset your password."
            )
        if not user.check_password(password or ""):
            user.register_failed_login()
            AuditService.record(
                action="login_failed", entity_type="user", entity_id=user.pk, actor=user,
                summary="Incorrect password", metadata={"ip": ip},
            )
            raise AuthenticationRequired("Invalid email address or password.")
        if not user.is_active:
            raise PermissionDeniedError("This account has been deactivated. Please contact support.")

        user.register_successful_login(ip=ip)
        AuditService.record(
            action="login", entity_type="user", entity_id=user.pk, actor=user,
            summary="Signed in", metadata={"ip": ip},
        )
        return user

    @staticmethod
    def change_password(*, user, current_password: str, new_password: str) -> None:
        if not user.check_password(current_password or ""):
            raise ValidationError({"current_password": ["Your current password is incorrect."]})
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            raise ValidationError({"new_password": list(exc.messages)})
        if current_password == new_password:
            raise ValidationError({"new_password": ["Choose a password you have not used before."]})
        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])
        AuditService.record(
            action="update", entity_type="user", entity_id=user.pk, actor=user,
            summary="Password changed",
        )

    # ------------------------------------------------------------------
    # Email verification
    # ------------------------------------------------------------------
    @staticmethod
    def verify_email(raw_token: str) -> User:
        token = AccountService.consume_token(
            raw_token, purpose=OneTimeToken.Purpose.EMAIL_VERIFICATION
        )
        if token.user is None:
            raise ValidationError("This verification link is not valid.")
        token.user.mark_email_verified()
        AuditService.record(
            action="update", entity_type="user", entity_id=token.user_id,
            actor=token.user, summary="Email verified",
        )
        return token.user

    @staticmethod
    def resend_verification(user) -> None:
        if user.is_email_verified:
            raise ConflictError("This email address is already verified.")
        raw = AccountService.issue_token(
            purpose=OneTimeToken.Purpose.EMAIL_VERIFICATION,
            user=user, hours=EMAIL_VERIFICATION_HOURS,
        )
        from apps.notifications.services import NotificationService

        NotificationService.email_verification(
            user, f"{settings.FRONTEND_URL}/verify-email?token={raw}",
            expires_hours=EMAIL_VERIFICATION_HOURS,
        )

    # ------------------------------------------------------------------
    # Password reset
    # ------------------------------------------------------------------
    @staticmethod
    def request_password_reset(email: str) -> None:
        """
        Always behaves identically whether or not the account exists, so the
        endpoint cannot be used to enumerate customers.
        """
        user = User.objects.filter(email__iexact=(email or "").strip().lower()).first()
        if user is None or not user.is_active:
            logger.info("Password reset requested for unknown/inactive email")
            return
        raw = AccountService.issue_token(
            purpose=OneTimeToken.Purpose.PASSWORD_RESET, user=user, hours=PASSWORD_RESET_HOURS
        )
        from apps.notifications.services import NotificationService

        NotificationService.password_reset(
            user, f"{settings.FRONTEND_URL}/reset-password?token={raw}",
            expires_hours=PASSWORD_RESET_HOURS,
        )

    @staticmethod
    @transaction.atomic
    def reset_password(*, raw_token: str, new_password: str) -> User:
        token = AccountService.consume_token(raw_token, purpose=OneTimeToken.Purpose.PASSWORD_RESET)
        user = token.user
        if user is None:
            raise ValidationError("This reset link is not valid.")
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            raise ValidationError({"new_password": list(exc.messages)})
        user.set_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=[
            "password", "failed_login_attempts", "locked_until", "updated_at",
        ])
        # Invalidate any other outstanding reset tokens.
        OneTimeToken.objects.filter(
            user=user, purpose=OneTimeToken.Purpose.PASSWORD_RESET, used_at__isnull=True
        ).exclude(pk=token.pk).update(used_at=timezone.now())
        AuditService.record(
            action="update", entity_type="user", entity_id=user.pk, actor=user,
            summary="Password reset completed",
        )
        return user

    # ------------------------------------------------------------------
    # Roles (Section 21)
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def create_role(*, name: str, slug: str, permissions: list[str] | None = None,
                    description: str = "", actor=None) -> Role:
        from django.contrib.auth.models import Permission

        if not (actor and (actor.is_superuser or actor.has_perm("accounts.add_role"))):
            raise PermissionDeniedError("You do not have permission to manage roles.")
        if Role.objects.filter(name__iexact=name).exists():
            raise ConflictError("A role with this name already exists.")

        role = Role.objects.create(
            name=name[:120], slug=slug[:80], description=description[:1000]
        )
        if permissions:
            perms = Permission.objects.filter(
                content_type__app_label__in=[p.split(".")[0] for p in permissions if "." in p],
                codename__in=[p.split(".")[1] for p in permissions if "." in p],
            )
            role.permissions.set(perms)
        AuditService.record(
            action="permission_changed", entity_type="role", entity_id=role.pk, actor=actor,
            summary=f"Role created: {role.name}", after={"permissions": permissions or []},
        )
        return role

    @staticmethod
    def assign_role(*, user, role: Role, actor=None, designation: str = "") -> StaffProfile:
        if not (actor and (actor.is_superuser or actor.has_perm("accounts.change_staffprofile"))):
            raise PermissionDeniedError("You do not have permission to assign roles.")
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        profile.role = role
        if designation:
            profile.designation = designation[:120]
        profile.save()
        user.is_staff = True
        user.save(update_fields=["is_staff", "updated_at"])
        AuditService.record(
            action="permission_changed", entity_type="staff_profile", entity_id=profile.pk,
            actor=actor, summary=f"Role {role.name} assigned to {user.email}",
        )
        return profile

    @staticmethod
    def user_permissions(user) -> list[str]:
        if user.is_superuser:
            return ["*"]
        return sorted(user.get_all_permissions())

    @staticmethod
    def profile_payload(user) -> dict:
        profile = getattr(user, "customer_profile", None)
        staff = getattr(user, "staff_profile", None)
        return {
            "id": str(user.pk),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone": user.phone,
            "gender": user.gender,
            "is_email_verified": user.is_email_verified,
            "is_staff": user.is_staff,
            "marketing_opt_in": user.marketing_opt_in,
            "date_joined": user.date_joined.isoformat(),
            "role": user.role_slug,
            "permissions": AccountService.user_permissions(user),
            "staff": (
                {
                    "role": staff.role.name if staff and staff.role else None,
                    "designation": staff.designation if staff else "",
                    "department": staff.department if staff else "",
                    "can_process_refunds": bool(staff and staff.can_process_refunds),
                }
                if user.is_staff else None
            ),
            "preferences": (
                {
                    "notify_order_updates": profile.notify_order_updates,
                    "notify_promotions": profile.notify_promotions,
                    "notify_newsletter": profile.notify_newsletter,
                    "notify_sms": profile.notify_sms,
                }
                if profile else None
            ),
            "stats": (
                {"order_count": profile.order_count, "lifetime_value": str(profile.lifetime_value)}
                if profile else None
            ),
        }
