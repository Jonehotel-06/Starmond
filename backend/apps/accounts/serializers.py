from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers

from apps.core.constants import ALL_PERMISSIONS
from .models import Permission, Role, StaffProfile, User

EMAIL_VERIFY_SALT = "starmond-email-verify"


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        user = User(email=attrs["email"], full_name=attrs["full_name"], phone=attrs.get("phone", ""))
        validate_password(attrs["password"], user)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data["full_name"],
            phone=validated_data.get("phone", ""),
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context["request"],
            username=attrs["email"].lower(),
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account is disabled.")
        attrs["user"] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    is_staff_user = serializers.SerializerMethodField()
    is_superuser = serializers.BooleanField(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "is_email_verified", "date_joined", "role",
                  "is_staff_user", "is_superuser", "permissions"]
        read_only_fields = ["id", "email", "is_email_verified", "date_joined"]

    def get_permissions(self, obj):
        """Permission codenames for UI gating only — every staff endpoint
        re-checks permissions server-side."""
        if obj.is_superuser:
            return list(ALL_PERMISSIONS)
        profile = getattr(obj, "staff_profile", None)
        if not profile or not profile.is_active or not profile.role:
            return []
        return sorted(profile.role.permissions.values_list("codename", flat=True))

    def get_role(self, obj):
        profile = getattr(obj, "staff_profile", None)
        return profile.role.name if profile and profile.role else None

    def get_is_staff_user(self, obj):
        profile = getattr(obj, "staff_profile", None)
        return obj.is_superuser or bool(profile and profile.is_active and profile.role)


class EmailVerifySerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate_token(self, value):
        try:
            email = signing.loads(value, salt=EMAIL_VERIFY_SALT, max_age=60 * 60 * 24 * 3)
        except signing.BadSignature:
            raise serializers.ValidationError("Invalid or expired verification token.")
        try:
            self.user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Account not found.")
        return value


def make_email_verify_token(user):
    return signing.dumps(user.email, salt=EMAIL_VERIFY_SALT)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        try:
            email = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(email=email)
        except (User.DoesNotExist, ValueError, TypeError, UnicodeDecodeError):
            raise serializers.ValidationError("Invalid reset link.")
        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError("Invalid or expired reset token.")
        validate_password(attrs["new_password"], user)
        attrs["user"] = user
        return attrs

    @staticmethod
    def make_uid(user):
        return urlsafe_base64_encode(force_bytes(user.email))


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        validate_password(attrs["new_password"], self.context["request"].user)
        return attrs


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "codename", "name", "group", "description"]


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(
        slug_field="codename", queryset=Permission.objects.all(), many=True, required=False
    )
    staff_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "name", "description", "permissions", "is_system", "staff_count", "created_at"]
        read_only_fields = ["id", "is_system", "created_at"]

    def get_staff_count(self, obj):
        return obj.staff_profiles.count()

    def validate_permissions(self, value):
        for perm in value or []:
            if perm.codename not in ALL_PERMISSIONS:
                raise serializers.ValidationError(f"Unknown permission codename: {perm.codename}")
        return value

    def create(self, validated_data):
        perms = validated_data.pop("permissions", [])
        role = Role.objects.create(**validated_data)
        if perms:
            role.permissions.set(perms)
        return role

    def update(self, instance, validated_data):
        perms = validated_data.pop("permissions", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if perms is not None:
            instance.permissions.set(perms)
        return instance


class StaffProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = StaffProfile
        fields = ["id", "email", "full_name", "role", "role_name", "is_active", "notes", "created_at"]
        read_only_fields = ["id", "created_at"]


class StaffCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())
    temporary_password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        validate_password(attrs["temporary_password"])
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["temporary_password"],
            full_name=validated_data["full_name"],
            phone=validated_data.get("phone", ""),
        )
        profile = StaffProfile.objects.create(user=user, role=validated_data["role"], is_active=True)
        return profile
