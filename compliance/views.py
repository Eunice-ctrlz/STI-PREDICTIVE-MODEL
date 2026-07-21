from rest_framework import viewsets
from .models import AuditLog
from .serializers import AuditLogSerializer

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all().order_by('-created_at')
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        queryset = AuditLog.objects.all().order_by('-created_at')
        action = self.request.query_params.get('action', None)
        if action is not None:
            queryset = queryset.filter(action=action)
        return queryset
