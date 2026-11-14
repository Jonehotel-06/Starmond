from django.core import mail

from apps.accounts.models import User

from .base import StarmondAPITestCase


class AuthFlowTests(StarmondAPITestCase):
    def test_register_login_verify_flow(self):
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response = self.client.post("/api/auth/register/", {
                "email": "new@example.com", "full_name": "New User",
                "password": "Str0ngPass!234", "phone": "08000000000"}, format="json")
            self.assertEqual(response.status_code, 201)
            user = User.objects.get(email="new@example.com")
            self.assertFalse(user.is_email_verified)
            self.assertEqual(len(mail.outbox), 1)  # verification email
            token = mail.outbox[0].body.split("token=")[-1].split()[0].strip()
            response = self.client.post("/api/auth/verify-email/", {"token": token}, format="json")
            self.assertEqual(response.status_code, 200)
            user.refresh_from_db()
            self.assertTrue(user.is_email_verified)

        response = self.client.post("/api/auth/login/", {"email": "new@example.com", "password": "Str0ngPass!234"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("auth_token", response.data["data"])

    def test_login_wrong_password_rejected(self):
        self.make_customer(email="c@example.com", password="RightPass!123")
        response = self.client.post("/api/auth/login/", {"email": "c@example.com", "password": "WrongPass!123"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_duplicate_registration_rejected(self):
        self.make_customer(email="dup@example.com")
        response = self.client.post("/api/auth/register/", {
            "email": "dup@example.com", "full_name": "Dup", "password": "Str0ngPass!234"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_weak_password_rejected(self):
        response = self.client.post("/api/auth/register/", {
            "email": "weak@example.com", "full_name": "Weak", "password": "123"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_password_reset_flow(self):
        user = self.make_customer(email="reset@example.com", password="OldPass!1234")
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response = self.client.post("/api/auth/password/reset/request/", {"email": user.email}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(mail.outbox), 1)
            body = mail.outbox[0].body
            uid = body.split("uid=")[-1].split("&")[0].strip()
            token = body.split("token=")[-1].split()[0].strip()
        response = self.client.post("/api/auth/password/reset/confirm/", {
            "uid": uid, "token": token, "new_password": "NewPass!5678"}, format="json")
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPass!5678"))

    def test_me_endpoint_scoped_to_self(self):
        customer = self.make_customer(email="me@example.com")
        self.client.force_authenticate(customer)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.data["data"]["email"], "me@example.com")

    def test_password_change_requires_current(self):
        customer = self.make_customer(email="ch@example.com", password="OldPass!1234")
        self.client.force_authenticate(customer)
        response = self.client.post("/api/auth/password/change/", {
            "current_password": "WrongOld!1", "new_password": "NewPass!5678"}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/auth/password/change/", {
            "current_password": "OldPass!1234", "new_password": "NewPass!5678"}, format="json")
        self.assertEqual(response.status_code, 200)
