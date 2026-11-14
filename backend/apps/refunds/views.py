from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.exceptions import ServiceError
from apps.core.permissions import IsStaffWithPermission
from apps.orders.models import Order

from .models import Refund
from .serializers import RefundDecisionSerializer, RefundRequestSerializer, RefundSerializer
from .services import RefundService


class CustomerRefundViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Customers request refunds per the published policy and see only their own."""
    permission_classes = [IsAuthenticated]
    serializer_class = RefundSerializer

    def get_queryset(self):
        return Refund.objects.filter(order__customer=self.request.user).select_related("order", "payment")

    def create(self, request, *args, **kwargs):
        serializer = RefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = Order.objects.filter(reference=serializer.validated_data["order_reference"].upper(),
                                     customer=request.user).first()
        if not order:
            raise ServiceError("Order not found for your account.", code="order_not_found", status_code=404)
        refund = RefundService.request_refund(
            order, requester=request.user, reason=serializer.validated_data["reason"],
            amount=serializer.validated_data.get("amount"), restock=serializer.validated_data.get("restock", False))
        AuditService.log(request.user, "refund.request", "Refund", refund.pk,
                         {"order": order.reference, "amount": str(refund.requested_amount)}, request=request)
        return Response({"status": "success", "data": RefundSerializer(refund).data}, status=status.HTTP_201_CREATED)


class StaffRefundViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.FINANCE_VIEW
    serializer_class = RefundSerializer
    queryset = Refund.objects.select_related("order", "payment", "processed_by", "requested_by").all()
    filterset_fields = ["status", "order"]
    search_fields = ["reference", "order__reference"]
    ordering = ["-created_at"]

    def _ensure_manage(self, request):
        from apps.core.permissions import user_has_permission
        if not user_has_permission(request.user, Perm.REFUNDS_MANAGE):
            raise ServiceError("You lack the refunds.manage permission.", code="permission_denied", status_code=403)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        self._ensure_manage(request)
        refund = self.get_object()
        serializer = RefundDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refund = RefundService.approve(refund, request.user,
                                       approved_amount=serializer.validated_data.get("approved_amount"),
                                       notes=serializer.validated_data.get("notes", ""))
        AuditService.log(request.user, "refund.approve", "Refund", refund.pk,
                         {"amount": str(refund.approved_amount), "status": refund.status}, request=request)
        return Response({"status": "success", "data": RefundSerializer(refund).data})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        self._ensure_manage(request)
        refund = self.get_object()
        serializer = RefundDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refund = RefundService.reject(refund, request.user, notes=serializer.validated_data.get("notes", ""))
        AuditService.log(request.user, "refund.reject", "Refund", refund.pk, {}, request=request)
        return Response({"status": "success", "data": RefundSerializer(refund).data})

    @action(detail=True, methods=["post"], url_path="check-status")
    def check_status(self, request, pk=None):
        self._ensure_manage(request)
        refund = RefundService.check_provider_status(self.get_object())
        return Response({"status": "success", "data": RefundSerializer(refund).data})
