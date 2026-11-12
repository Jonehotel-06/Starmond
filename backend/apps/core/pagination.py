"""Consistent pagination envelopes for the public API contract."""
from __future__ import annotations

from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("success", True),
                    ("count", self.page.paginator.count),
                    ("num_pages", self.page.paginator.num_pages),
                    ("current_page", self.page.number),
                    ("page_size", self.get_page_size(self.request)),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "count": {"type": "integer"},
                "num_pages": {"type": "integer"},
                "current_page": {"type": "integer"},
                "page_size": {"type": "integer"},
                "next": {"type": "string", "nullable": True},
                "previous": {"type": "string", "nullable": True},
                "results": schema,
            },
        }


class LargeResultsSetPagination(StandardResultsSetPagination):
    page_size = 100
    max_page_size = 500


class SmallResultsSetPagination(StandardResultsSetPagination):
    page_size = 10
    max_page_size = 50
