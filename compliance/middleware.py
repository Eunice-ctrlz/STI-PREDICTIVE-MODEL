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
        if 'predict' in path:
            return 'predict'
        if 'login' in path:
            return 'login'
        if 'logout' in path:
            return 'logout'
        if 'export' in path or 'report' in path:
            return 'export'
        if method == 'POST':
            return 'create'
        if method in ('PUT', 'PATCH'):
            return 'update'
        if method == 'DELETE':
            return 'delete'
        return 'read'
    
    def _get_resource_type(self, path):
        if 'patients' in path:
            return 'Patient'
        if 'predictions' in path:
            return 'Prediction'
        if 'clinicians' in path:
            return 'Clinician'
        if 'reports' in path:
            return 'Report'
        return 'Unknown'
    
    def _get_client_ip(self, request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')