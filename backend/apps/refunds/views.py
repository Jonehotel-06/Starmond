"""Customer refund requests and staff refund processing."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from apps.core.exceptions import ValidationError
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import RequiresPermission
from apps.core.views import BaseAPIView
from apps.orders.services import OrderService
from apps.refunds.models import Refund
from apps.refunds.serializers import (
    RefundDecisionSerializer, RefundRequestSerializer, RefundSerializer,
)
from apps.refunds.services import RefundService


class CustomerRefundRequestView(BaseAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "user"

    def post(self, request):
        serializer = RefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        order = OrderService.get_customer_order(data["order_number"], request.user)
        refund = RefundService.request_refund(
            order=order,
            reason_category=data["reason_category"],
            customer_note=data.get("customer_note", ""),
            items=data.get("items"),
            amount=data.get("amount"),
            requested_by=request.user,
        )
        return self.created(RefundSerializer(refund).data,
                            message="Your refund request has been submitted for review.")


class CustomerRefundListView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Refund.objects.filter(order__customer=request.user).select_related("order")
        if request.query_params.get("order"):
            queryset = queryset.filter(order__order_number=request.query_params["order"])
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(RefundSerializer(page, many=True).data)


class RefundEligibilityView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_number: str):
        order = OrderService.get_customer_order(order_number, request.user)
        return self.ok(RefundService.refundable_summary(order))


class StaffRefundQueueView(BaseAPIView):
    permission_classes = [RequiresPermission.of("refunds.change_refund")]

    def get(self, request):
        queryset = Refund.objects.select_related("order").order_by("-created_at")
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(RefundSerializer(page, many=True).data)


class StaffRefundActionView(BaseAPIView):
    """approve | reject | submit | check — every action is audited."""

    permission_classes = [RequiresPermission.of("refunds.change_refund")]

    def post(self, request, refund_id: str, action: str):
        refund = Refund.objects.filter(pk=refund_id).first()
        if refund is None:
            from apps.core.exceptions import NotFound

            raise NotFound("Refund not found.")

        serializer = RefundDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if action == "approve":
            refund = RefundService.approve(
                refund, actor=request.user, amount=data.get("amount"),
                restock=data.get("restock", False), note=data.get("note", ""),
            )
            message = "Refund approved. Submit it to Paystack to return the money."
        elif action == "reject":
            if not data.get("reason"):
                raise ValidationError("A rejection reason is required.")
            refund = RefundService.reject(refund, actor=request.user, reason=data["reason"])
            message = "Refund rejected."
        elif action == "submit":
            refund = RefundService.submit_to_provider(refund, actor=request.user)
            message = "Refund submitted to Paystack. Awaiting provider confirmation."
        elif action == "check":
            refund = RefundService.check_provider_status(refund, actor=request.user)
            message = f"Provider status: {refund.provider_status or 'unknown'}."
        else:
            raise ValidationError("Unknown refund action.")

        return self.ok(RefundSerializer(refund).data, message=message)
