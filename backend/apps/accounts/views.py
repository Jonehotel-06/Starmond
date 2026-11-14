from django.contrib.auth import login, logout
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import AuditService
from services.notification_service import NotificationService

from .models import User
from .serializers import (
    EMAIL_VERIFY_SALT,
    EmailVerifySerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
    make_email_verify_token,
)


def _auth_payload(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {
        "status": "success",
        "data": {"user": UserSerializer(user).data, "auth_token": token.key},
    }


from drf_spectacular.utils import OpenApiTypes, extend_schema

@extend_schema(request=RegisterSerializer, responses={201: OpenApiTypes.OBJECT}, tags=["auth"])
class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_action"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        NotificationService.send_email_verification(user, request)
        AuditService.log(None, "auth.register", "User", user.pk, {"email": user.email}, request=request)
        return Response(
            {"status": "success", "message": "Account created. Please verify your email.", "data": {"user_id": user.pk}},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(request=EmailVerifySerializer, responses=OpenApiTypes.OBJECT, tags=["auth"])
class EmailVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_action"

    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.user
        if not user.is_email_verified:
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])
        return Response({"status": "success", "message": "Email verified."})


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, tags=["auth"])
class ResendVerificationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_action"

    def post(self, request):
        email = (request.data.get("email") or "").lower()
        user = User.objects.filter(email=email).first()
        # Always return success to avoid account enumeration.
        if user and not user.is_email_verified:
            NotificationService.send_email_verification(user, request)
        return Response({"status": "success", "message": "If the account exists and is unverified, a new link was sent."})


@extend_schema(request=LoginSerializer, responses=OpenApiTypes.OBJECT, tags=["auth"])
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_action"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request, user)
        return Response(_auth_payload(user))


@extend_schema(request=None, responses=OpenApiTypes.OBJECT, tags=["auth"])
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        logout(request)
        return Response({"status": "success", "message": "Logged out."})


@extend_schema(request=PasswordResetRequestSerializer, responses=OpenApiTypes.OBJECT, tags=["auth"])
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_action"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email=serializer.validated_data["email"].lower()).first()
        if user and user.is_active:
            uid = PasswordResetConfirmSerializer.make_uid(user)
            token = default_token_generator.make_token(user)
            NotificationService.send_password_reset(user, uid, token, request)
        # Anti-enumeration: identical response either way.
        return Response({"status": "success", "message": "If an account exists for that email, a reset link has been sent."})


@extend_schema(request=PasswordResetConfirmSerializer, responses=OpenApiTypes.OBJECT, tags=["auth"])
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_action"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        Token.objects.filter(user=user).delete()  # revoke existing API tokens
        return Response({"status": "success", "message": "Password reset. Please log in again."})


@extend_schema(request=PasswordChangeSerializer, responses=OpenApiTypes.OBJECT, tags=["auth"])
class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        Token.objects.filter(user=user).exclude(key=Token.objects.get_or_create(user=user)[0].key).delete()
        return Response({"status": "success", "message": "Password changed."})


@extend_schema(tags=["auth"])
class MeView(RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        return Response({"status": "success", "data": self.get_serializer(self.get_object()).data})
