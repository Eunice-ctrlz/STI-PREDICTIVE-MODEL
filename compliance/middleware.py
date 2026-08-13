"""
Audit log middleware - logs all API requests.
"""
import json
from .models import AuditLog


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip static/media
        if request.path.startswith(('/static/', '/media/', '/admin/jsi18n/')):
            return self.get_response(request)
        
        response = self.get_response(request)
        
        # Log the request
        try:
            user = request.user if request.user.is_authenticated else None
            user_name = user.get_full_name() or user.username if user else 'Anonymous'
            
            # Determine action type from method and path
            action = self._get_action(request.method, request.path)
            
            AuditLog.objects.create(
                user=user,
                user_name=user_name,
                action=action,
                resource_type=self._get_resource_type(request.path),
                description=f"{request.method} {request.path}",
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            )
        except Exception:
            pass  # Don't break requests if logging fails
        
        return response
    
    def _get_action(self, method, path):
        # Match the prediction-generating endpoints specifically. A bare
        # 'predict' substring also matches '/api/predictions/5', which is a
        # read, and would log every lookup as if a new score was generated.
        if '/predictions/predict' in path:
            return 'predict'
        if 'validate' in path:
            return 'update'
        if 'login' in path:
            return 'login'
        if 'logout' in path:
            return 'logout'
        # Only a genuine export counts as one. Matching 'report' here would
        # label every dashboard read as a data export.
        if 'export' in path or 'download' in path:
            return 'export'
        if method == 'POST':
            return 'create'
        if method in ('PUT', 'PATCH'):
            return 'update'
        if method == 'DELETE':
            return 'delete'
        return 'read'

    # Longest-prefix-first so '/api/predictions/' isn't caught by a broader rule.
    RESOURCE_MAP = (
        ('/patients', 'Patient'),
        ('/predictions', 'Prediction'),
        ('/clinicians', 'Clinician'),
        ('/reporting', 'Report'),
        ('/geospatial', 'Geospatial'),
        ('/compliance', 'Compliance'),
        ('/ingestion', 'DataIngestion'),
        ('/ml', 'MLModel'),
        ('/admin', 'Admin'),
    )

    def _get_resource_type(self, path):
        for prefix, label in self.RESOURCE_MAP:
            if prefix in path:
                return label
        return 'Unknown'
    
    def _get_client_ip(self, request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')