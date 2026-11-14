from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


from drf_spectacular.utils import OpenApiTypes, extend_schema

@extend_schema(tags=["system"], responses=OpenApiTypes.OBJECT)
class HealthView(APIView):
    """GET /api/health/ — liveness/readiness for containers and monitoring."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            db_ok = False
        status = "ok" if db_ok else "degraded"
        return Response({"status": status, "database": "up" if db_ok else "down"},
                        status=200 if db_ok else 503)
