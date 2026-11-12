"""Staff order management: queue, detail, state transitions and notes."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import NotFound, ValidationError
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsStaff, RequiresPermission
from apps.core.views import BaseAPIView
from apps.orders.models import Order, OrderActivity
from apps.orders.serializers import StaffOrderSerializer
from apps.orders.services import ALLOWED_TRANSITIONS, OrderService


class StaffOrderListView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("orders.view_order")]

    def get(self, request):
        queryset = Order.objects.select_related("customer").order_by("-created_at")
        for param, field in (
            ("status", "status"), ("payment_status", "payment_status"),
            ("state", "shipping_state"), ("channel", "channel"),
        ):
            if request.query_params.get(param):
                queryset = queryset.filter(**{field: request.query_params[param]})
        if request.query_params.get("q"):
            term = request.query_params["q"]
            from django.db.models import Q

            queryset = queryset.filter(
                Q(order_number__icontains=term) | Q(guest_email__icontains=term)
                | Q(shipping_full_name__icontains=term) | Q(customer__email__icontains=term)
            )
        if request.query_params.get("from"):
            queryset = queryset.filter(created_at__date__gte=request.query_params["from"])
        if request.query_params.get("to"):
            queryset = queryset.filter(created_at__date__lte=request.query_params["to"])

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            StaffOrderSerializer(page, many=True).data
        )


class StaffOrderDetailView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("orders.view_order")]

    def get(self, request, order_number: str):
        order = Order.objects.filter(order_number=order_number).first()
        if order is None:
            raise NotFound("Order not found.")
        payload = StaffOrderSerializer(order).data
        payload["allowed_transitions"] = sorted(ALLOWED_TRANSITIONS.get(order.status, set()))
        return self.ok(payload)

    def post(self, request, order_number: str):
        """Adds an internal note, or flips the internal note field."""
        order = Order.objects.filter(order_number=order_number).first()
        if order is None:
            raise NotFound("Order not found.")
        note = (request.data.get("note") or "").strip()
        if not note:
            raise ValidationError("A note is required.")
        order.internal_note = f"{order.internal_note}\n{note}".strip()[:5000]
        order.save(update_fields=["internal_note", "updated_at"])
        OrderService.add_activity(
            order, event=OrderActivity.Event.NOTE, message=note,
            actor=request.user, is_customer_visible=False,
        )
        return self.ok(message="Note added.")


class StaffOrderTransitionView(BaseAPIView):
    """
    Moves an order through its lifecycle.

    The transition table lives in OrderService; the view only relays the intent,
    so an invalid jump is rejected identically everywhere.
    """

    permission_classes = [IsStaff, RequiresPermission.of("orders.change_order")]

    def post(self, request, order_number: str):
        order = Order.objects.filter(order_number=order_number).first()
        if order is None:
            raise NotFound("Order not found.")
        target = request.data.get("status")
        if not target:
            raise ValidationError("A target status is required.")

        if target == "cancelled":
            order = OrderService.cancel(
                order, actor=request.user, reason=request.data.get("note", ""), by_staff=True
            )
        elif target == "completed":
            order = OrderService.complete(order, actor=request.user)
        elif target == "delivered":
            order = OrderService.mark_delivered(order, actor=request.user,
                                                note=request.data.get("note", ""))
        else:
            order = OrderService.transition(order, target, actor=request.user,
                                            note=request.data.get("note", ""))

        return self.ok(
            {"order_number": order.order_number, "status": order.status,
             "allowed_transitions": sorted(ALLOWED_TRANSITIONS.get(order.status, set()))},
            message=f"Order moved to {order.get_status_display()}.",
        )
