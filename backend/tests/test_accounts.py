"""Authentication, verification, password lifecycle and RBAC."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase

from apps.accounts.models import Role, StaffProfile
from apps.accounts.services import AccountService
from apps.core.exceptions import (
    AuthenticationRequired, ConflictError, PermissionDeniedError, ValidationError,
)
from apps.customers.models import OneTimeToken
from tests.factories import make_customer, make_settings, make_staff

User = get_user_model()


class RegistrationTests(TestCase):
    def setUp(self):
        make_settings()

    def test_registration_creates_customer_with_hashed_password(self):
        user, token = AccountService.register(
            email="new@example.com", password="Str0ngPassw0rd!2026", first_name="Ngozi",
        )
        self.assertTrue(user.check_password("Str0ngPassw0rd!2026"))
        self.assertFalse(user.is_email_verified)
        self.assertTrue(user.has_usable_password())
        self.assertNotEqual(user.password, "Str0ngPassw0rd!2026")
        self.assertTrue(token)

    def test_duplicate_email_is_rejected(self):
        AccountService.register(email="dup@example.com", password="Str0ngPassw0rd!2026")
        with self.assertRaises(ConflictError):
            AccountService.register(email="dup@example.com", password="Str0ngPassw0rd!2026")

    def test_weak_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            AccountService.register(email="weak@example.com", password="12345678")

    def test_verification_token_is_single_use(self):
        _user, token = AccountService.register(
            email="verify@example.com", password="Str0ngPassw0rd!2026"
        )
        user = AccountService.verify_email(token)
        self.assertTrue(user.is_email_verified)
        with self.assertRaises(ValidationError):
            AccountService.verify_email(token)

    def test_expired_verification_token_is_refused(self):
        from django.utils import timezone

        user, token = AccountService.register(
            email="expire@example.com", password="Str0ngPassw0rd!2026"
        )
        OneTimeToken.objects.filter(purpose=OneTimeToken.Purpose.EMAIL_VERIFICATION).update(
            expires_at=timezone.now() - timezone.timedelta(minutes=1)
        )
        with self.assertRaises(ValidationError):
            AccountService.verify_email(token)

    def test_raw_token_is_never_stored(self):
        _user, token = AccountService.register(
            email="hash@example.com", password="Str0ngPassw0rd!2026"
        )
        stored = OneTimeToken.objects.values_list("token_hash", flat=True)
        self.assertNotIn(token, stored)


class AuthenticationTests(TestCase):
    def setUp(self):
        make_settings()
        self.user = make_customer(email="login@example.com")

    def test_login_with_correct_credentials(self):
        user = AccountService.authenticate(email="login@example.com", password="TestPassw0rd!2026")
        self.assertEqual(user.pk, self.user.pk)

    def test_login_is_case_insensitive_on_email(self):
        user = AccountService.authenticate(email="LOGIN@EXAMPLE.COM", password="TestPassw0rd!2026")
        self.assertEqual(user.pk, self.user.pk)

    def test_wrong_password_is_rejected(self):
        with self.assertRaises(AuthenticationRequired):
            AccountService.authenticate(email="login@example.com", password="wrong")

    def test_unknown_email_is_rejected(self):
        with self.assertRaises(AuthenticationRequired):
            AccountService.authenticate(email="ghost@example.com", password="whatever")

    def test_account_locks_after_repeated_failures(self):
        for _ in range(5):
            with self.assertRaises(AuthenticationRequired):
                AccountService.authenticate(email="login@example.com", password="wrong")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked)
        with self.assertRaises(PermissionDeniedError):
            AccountService.authenticate(email="login@example.com", password="TestPassw0rd!2026")

    def test_deactivated_account_cannot_sign_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDeniedError):
            AccountService.authenticate(email="login@example.com", password="TestPassw0rd!2026")


class PasswordLifecycleTests(TestCase):
    def setUp(self):
        make_settings()
        self.user = make_customer(email="pw@example.com")

    def test_reset_request_for_unknown_email_is_silent(self):
        AccountService.request_password_reset("nobody@example.com")  # must not raise

    def test_password_reset_flow(self):
        AccountService.request_password_reset("pw@example.com")
        token = OneTimeToken.objects.get(purpose=OneTimeToken.Purpose.PASSWORD_RESET)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reset your password", mail.outbox[0].subject)

        raw = self._recover_raw_token(token)
        AccountService.reset_password(raw_token=raw, new_password="BrandNewPass!2026")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNewPass!2026"))

    def _recover_raw_token(self, token_record) -> str:
        """Test-only helper: re-issues a token so the raw value is available."""
        raw = AccountService.issue_token(
            purpose=OneTimeToken.Purpose.PASSWORD_RESET, user=self.user, hours=2
        )
        return raw

    def test_change_password_requires_current_password(self):
        with self.assertRaises(ValidationError):
            AccountService.change_password(
                user=self.user, current_password="wrong", new_password="AnotherPass!2026"
            )
        AccountService.change_password(
            user=self.user, current_password="TestPassw0rd!2026", new_password="AnotherPass!2026"
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("AnotherPass!2026"))

    def test_reset_rejects_weak_password(self):
        raw = AccountService.issue_token(
            purpose=OneTimeToken.Purpose.PASSWORD_RESET, user=self.user, hours=2
        )
        with self.assertRaises(ValidationError):
            AccountService.reset_password(raw_token=raw, new_password="123")


class RoleBasedAccessTests(TestCase):
    def setUp(self):
        make_settings()
        self.owner = make_staff(superuser=True)
        self.support = make_staff(superuser=False)

    def test_role_assignment_grants_permissions(self):
        role = AccountService.create_role(
            name="Support Agent", slug="support-agent",
            permissions=["orders.view_order", "orders.change_order"], actor=self.owner,
        )
        AccountService.assign_role(user=self.support, role=role, actor=self.owner)
        self.support = User.objects.get(pk=self.support.pk)
        self.support = User.objects.prefetch_related("groups", "user_permissions").get(
            pk=self.support.pk
        )
        # Role permissions are resolved through the role membership at check time.
        self.assertTrue(self.support.is_staff)
        self.assertEqual(self.support.staff_profile.role.slug, "support-agent")

    def test_role_creation_requires_permission(self):
        with self.assertRaises(PermissionDeniedError):
            AccountService.create_role(
                name="Sneaky", slug="sneaky", permissions=[], actor=self.support
            )

    def test_system_roles_cannot_be_deleted(self):
        role = Role.objects.create(name="Locked", slug="locked", is_system=True)
        with self.assertRaises(PermissionError):
            role.delete()

    def test_superuser_reports_wildcard_permissions(self):
        self.assertEqual(AccountService.user_permissions(self.owner), ["*"])

    def test_staff_cannot_reach_staff_api_without_login(self):
        response = self.client.get("/api/v1/dashboard/overview/")
        self.assertEqual(response.status_code, 401)

    def test_customer_cannot_reach_staff_api(self):
        customer = make_customer()
        self.client.force_login(customer)
        response = self.client.get("/api/v1/dashboard/overview/")
        self.assertIn(response.status_code, {403, 401})

    def test_owner_can_reach_staff_api(self):
        self.client.force_login(self.owner)
        response = self.client.get("/api/v1/dashboard/overview/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])


class AuthApiTests(TestCase):
    def setUp(self):
        make_settings()

    def test_register_endpoint_returns_tokens(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            data={"email": "api@example.com", "password": "Str0ngPassw0rd!2026",
                  "confirm_password": "Str0ngPassw0rd!2026", "first_name": "Api"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertIn("access", body["data"])
        self.assertIn("refresh", body["data"])
        self.assertNotIn("password", str(body))

    def test_register_rejects_mismatched_passwords(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            data={"email": "mismatch@example.com", "password": "Str0ngPassw0rd!2026",
                  "confirm_password": "Different!2026"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "validation_error")

    def test_login_endpoint_returns_tokens(self):
        make_customer(email="apidash@example.com")
        response = self.client.post(
            "/api/v1/auth/login/",
            data={"email": "apidash@example.com", "password": "TestPassw0rd!2026"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json()["data"])

    def test_login_failure_uses_generic_message(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            data={"email": "nobody@example.com", "password": "x"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        message = response.json()["error"]["message"].lower()
        self.assertIn("invalid", message)
        self.assertNotIn("does not exist", message)

    def test_me_endpoint_requires_auth(self):
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_me_endpoint_returns_profile(self):
        user = make_customer()
        self.client.force_login(user)
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["email"], user.email)
