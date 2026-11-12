"""Authentication and account management endpoints."""
from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.services import AccountService
from apps.core.views import BaseAPIView, client_ip
from apps.customers.models import OneTimeToken


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=10, max_length=128)
    confirm_password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=16, required=False, allow_blank=True)
    marketing_opt_in = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": ["Passwords do not match."]})
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=10, max_length=128)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": ["Passwords do not match."]})
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=10, max_length=128)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": ["Passwords do not match."]})
        return attrs


class ProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=16, required=False, allow_blank=True)
    gender = serializers.CharField(max_length=20, required=False, allow_blank=True)
    marketing_opt_in = serializers.BooleanField(required=False)
    notify_order_updates = serializers.BooleanField(required=False)
    notify_promotions = serializers.BooleanField(required=False)
    notify_newsletter = serializers.BooleanField(required=False)
    notify_sms = serializers.BooleanField(required=False)


def issue_tokens(user) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["email"] = user.email
    refresh["is_staff"] = user.is_staff
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class RegisterView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user, _token = AccountService.register(
            email=data["email"],
            password=data["password"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            phone=data.get("phone", ""),
            marketing_opt_in=data.get("marketing_opt_in", False),
            request=request,
        )
        payload = issue_tokens(user)
        payload["user"] = AccountService.profile_payload(user)
        return self.created(
            payload,
            message=(
                "Account created. Please check your email to verify your address."
            ),
        )


class LoginView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = AccountService.authenticate(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
            ip=client_ip(request),
        )
        request.session["_auth_user_id"] = str(user.pk)
        payload = issue_tokens(user)
        payload["user"] = AccountService.profile_payload(user)

        # Merge any guest cart the visitor built before signing in.
        merge_info = {}
        try:
            from apps.cart.services import CartService

            _cart, merge_info = CartService.merge_guest_cart(request, user)
        except Exception:  # pragma: no cover - never block a login on cart merge
            merge_info = {}

        return self.ok(payload, message="Signed in.", cart_merged=merge_info)


class LogoutView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except Exception:
                pass
        from apps.audit.services import AuditService

        AuditService.record(
            action="logout", entity_type="user", entity_id=request.user.pk, actor=request.user,
            summary="Signed out",
        )
        try:
            from django.contrib.auth import logout

            logout(request)
        except Exception:
            pass
        return self.ok(message="Signed out.")


class MeView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return self.ok(AccountService.profile_payload(request.user))

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user

        for field in ("first_name", "last_name", "phone", "gender", "marketing_opt_in"):
            if field in data:
                setattr(user, field, data[field])
        user.save()

        profile = getattr(user, "customer_profile", None)
        if profile is not None:
            for field in ("notify_order_updates", "notify_promotions",
                          "notify_newsletter", "notify_sms"):
                if field in data:
                    setattr(profile, field, data[field])
            profile.save()

        return self.ok(AccountService.profile_payload(user), message="Profile updated.")


class VerifyEmailView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = AccountService.verify_email(serializer.validated_data["token"])
        return self.ok({"email": user.email}, message="Your email address is verified.")


class ResendVerificationView(BaseAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        AccountService.resend_verification(request.user)
        return self.ok(message="If your address is unverified, a new link is on its way.")


class PasswordResetRequestView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AccountService.request_password_reset(serializer.validated_data["email"])
        return self.ok(
            message="If an account exists for that address, a reset link has been sent."
        )


class PasswordResetConfirmView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AccountService.reset_password(
            raw_token=serializer.validated_data["token"],
            new_password=serializer.validated_data["new_password"],
        )
        return self.ok(message="Your password has been reset. You can now sign in.")


class PasswordChangeView(BaseAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AccountService.change_password(
            user=request.user,
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["new_password"],
        )
        return self.ok(message="Password changed successfully.")
